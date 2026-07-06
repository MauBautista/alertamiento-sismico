"""health — autodiagnóstico del gabinete (snapshots por transición + heartbeat).

T-1.10: compone un `HealthSnapshot` con NTP offset, lag SeedLink, packet loss, estado
UPS (`RED ELÉCTRICA %` / `RESPALDO Xh Ym` / `EN BATERÍA`), temperatura, `cert_days_
remaining` y estado de relés. **Logging por transición** de estado discreto (nunca por
intervalo continuo, regla de oro 10) + **heartbeat periódico** como beacon de vida.

Las fuentes del SO/hardware se leen por `HealthProbes` (inyectables): la temperatura
del Pi sale de `/sys/class/thermal` con degradación graceful; NTP (chrony), UPS (NUT) y
el vencimiento del cert mTLS tienen impl real con hardware (gate #3) y aquí van por
defecto seguro. Los tests inyectan probes deterministas.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from takab_edge.config import EdgeSettings
from takab_edge.contracts import HealthSnapshot, RelayState, UpsStatus
from takab_edge.gpio import GpioController
from takab_edge.module import EdgeModule

log = logging.getLogger("takab_edge.health")

#: Umbrales de transición discreta (evitan logging por drift de valores continuos).
CERT_WARN_DAYS = 30
TEMP_WARN_C = 80.0
LAG_WARN_S = 2.0

_THERMAL = Path("/sys/class/thermal/thermal_zone0/temp")


@dataclass(frozen=True)
class UpsReading:
    status: UpsStatus = UpsStatus.LINE
    battery_pct: float = 100.0
    runtime_s: float | None = None  # autonomía restante (None = desconocida / en red)


def ups_label(reading: UpsReading) -> str:
    """Etiqueta de UI del UPS: `RED ELÉCTRICA %` / `RESPALDO Xh Ym` / `EN BATERÍA`."""
    if reading.status is UpsStatus.LINE:
        return f"RED ELÉCTRICA {reading.battery_pct:.0f}%"
    if reading.status is UpsStatus.BATTERY:
        if reading.runtime_s is not None:
            hours, minutes = divmod(int(reading.runtime_s) // 60, 60)
            return f"EN BATERÍA · RESPALDO {hours}h {minutes}m"
        return "EN BATERÍA"
    return "UPS DESCONOCIDO"


class HealthProbes(Protocol):
    """Fuentes de métricas del host (impl real = hardware; mock en tests)."""

    def temperature_c(self) -> float: ...
    def ntp_offset_s(self) -> float: ...
    def ups(self) -> UpsReading: ...
    def cert_days_remaining(self) -> int: ...


class HostProbes:
    """Impl real con degradación graceful; NTP/UPS/cert reales son gate hardware."""

    def __init__(self, settings: EdgeSettings) -> None:
        self._settings = settings

    def temperature_c(self) -> float:
        try:
            return int(_THERMAL.read_text()) / 1000.0
        except (OSError, ValueError):
            return 0.0  # no es un Pi (dev/CI) o el sysfs no está disponible

    def ntp_offset_s(self) -> float:
        return 0.0  # real: `chronyc tracking` (gate hardware)

    def ups(self) -> UpsReading:
        return UpsReading()  # real: NUT/apcupsd o señal GPIO del UPS (gate hardware)

    def cert_days_remaining(self) -> int:
        return 365  # real: vencimiento del cert mTLS (T-1.11, con `cryptography`)


class HealthMonitor(EdgeModule):
    """Produce snapshots de salud del gabinete (por transición + heartbeat)."""

    name = "health"
    depends_on = ("gpio", "seedlink")

    def __init__(
        self,
        settings: EdgeSettings,
        gpio: GpioController | None = None,
        seedlink: object | None = None,
        probes: HealthProbes | None = None,
        heartbeat_s: float = 60.0,
    ) -> None:
        super().__init__()
        self.settings = settings
        self._gpio = gpio
        self._seedlink = seedlink
        self._probes = probes or HostProbes(settings)
        self._heartbeat_s = heartbeat_s
        self._callbacks: list[Callable[[HealthSnapshot], None]] = []
        self._last_key: tuple | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def on_snapshot(self, callback: Callable[[HealthSnapshot], None]) -> None:
        """Registra un consumidor de snapshots (p.ej. publicar a la nube, T-1.11)."""
        self._callbacks.append(callback)

    def _relay_states(self) -> list[RelayState]:
        if self._gpio is not None and self._gpio.running:
            return self._gpio.relay_states()
        return []

    def _packet_loss_pct(self) -> float:
        if self._seedlink is None:
            return 0.0
        seen = getattr(self._seedlink, "packets_seen", 0)
        gaps = getattr(self._seedlink, "gaps", 0)
        total = seen + gaps
        return (gaps / total * 100.0) if total else 0.0

    def _seedlink_lag_s(self) -> float:
        lag = getattr(self._seedlink, "last_lag_s", None) if self._seedlink else None
        return lag or 0.0

    def snapshot(self, transition_reason: str = "heartbeat") -> HealthSnapshot:
        relays = self._relay_states()
        ups = self._probes.ups()
        snap = HealthSnapshot(
            gateway_id=self.settings.gateway_id,
            ntp_offset_s=self._probes.ntp_offset_s(),
            seedlink_lag_s=self._seedlink_lag_s(),
            packet_loss_pct=self._packet_loss_pct(),
            ups_status=ups.status,
            battery_pct=ups.battery_pct,
            temperature_c=self._probes.temperature_c(),
            cert_days_remaining=self._probes.cert_days_remaining(),
            relays=relays,
            transition_reason=transition_reason,
        )
        self._log_transition(snap, transition_reason)
        for callback in self._callbacks:
            callback(snap)
        return snap

    def _log_transition(self, snap: HealthSnapshot, reason: str) -> None:
        # Clave de estado DISCRETO: relés + UPS + banderas de umbral. Nunca el drift de
        # valores continuos (temp/lag) → sin logging por intervalo (regla de oro 10).
        key = (
            tuple((r.channel, r.energized) for r in snap.relays),
            snap.ups_status,
            snap.cert_days_remaining < CERT_WARN_DAYS,
            snap.temperature_c > TEMP_WARN_C,
            snap.seedlink_lag_s > LAG_WARN_S,
        )
        if key != self._last_key:
            log.info(
                "transición de salud (%s): %s · temp=%.1f°C · lag=%.2fs · cert=%dd · loss=%.1f%%",
                reason,
                ups_label(UpsReading(snap.ups_status, snap.battery_pct)),
                snap.temperature_c,
                snap.seedlink_lag_s,
                snap.cert_days_remaining,
                snap.packet_loss_pct,
            )
            self._last_key = key

    def _heartbeat_loop(self) -> None:
        while not self._stop.wait(self._heartbeat_s):
            self.snapshot("heartbeat")

    def _on_start(self) -> None:
        self._stop.clear()
        self.snapshot("startup")  # baseline inmediato
        self._thread = threading.Thread(
            target=self._heartbeat_loop, name="health-heartbeat", daemon=True
        )
        self._thread.start()
        log.info("autodiagnóstico de salud activo (heartbeat %.0fs)", self._heartbeat_s)

    def _on_stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
