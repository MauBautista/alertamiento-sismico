"""health — autodiagnóstico del gabinete (snapshots por transición + heartbeat).

T-1.10/T-1.40: compone un `HealthSnapshot` con NTP offset, lag SeedLink, packet loss,
RTT MQTT, estado UPS, temperatura, `cert_days_remaining` y estado de relés. **Logging
por transición** de estado discreto (nunca por intervalo continuo, regla de oro 10) +
**heartbeat periódico** como beacon de vida.

Las fuentes del SO/hardware se leen por `HealthProbes` (inyectables). Desde T-1.40 los
probes son REALES con degradación honesta: NTP sale de chrony o systemd-timesyncd, el
vencimiento del cert mTLS de `openssl x509`, y la UPS de NUT o sysfs. **Cuando una
fuente no existe, el campo es `None` («sin dato») — jamás un número optimista inventado
(regla de oro 7).** Ninguna sonda lanza: el hilo del heartbeat no muere por I/O.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, TypeVar

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
_POWER_SUPPLY = Path("/sys/class/power_supply")

#: Tope de espera de una sonda externa: una herramienta colgada no congela el heartbeat.
_RUN_TIMEOUT_S = 2.0

_T = TypeVar("_T")


def _no_disk() -> float | None:
    """Sonda de disco ausente (probes pre-T-1.53): «sin dato»."""
    return None


@dataclass(frozen=True)
class UpsReading:
    """Lectura de UPS. Los defaults son la verdad sin hardware: estado DESCONOCIDO
    y batería `None` («sin dato») — el 100% optimista de antes era una mentira."""

    status: UpsStatus = UpsStatus.UNKNOWN
    battery_pct: float | None = None
    runtime_s: float | None = None  # autonomía restante (None = desconocida / en red)


def ups_label(reading: UpsReading) -> str:
    """Etiqueta de UI del UPS: `RED ELÉCTRICA [%]` / `RESPALDO Xh Ym` / `EN BATERÍA`."""
    if reading.status is UpsStatus.LINE:
        if reading.battery_pct is None:
            return "RED ELÉCTRICA"
        return f"RED ELÉCTRICA {reading.battery_pct:.0f}%"
    if reading.status is UpsStatus.BATTERY:
        if reading.runtime_s is not None:
            hours, minutes = divmod(int(reading.runtime_s) // 60, 60)
            return f"EN BATERÍA · RESPALDO {hours}h {minutes}m"
        return "EN BATERÍA"
    return "UPS DESCONOCIDO"


class HealthProbes(Protocol):
    """Fuentes de métricas del host (impl real = SO/hardware; fake en tests).

    ``None`` significa «sin dato»: la fuente no existe o no respondió. La nube
    lo presenta como S/D; nunca se sustituye por un default optimista.
    """

    def temperature_c(self) -> float: ...
    def ntp_offset_s(self) -> float | None: ...
    def ups(self) -> UpsReading: ...
    def cert_days_remaining(self) -> int | None: ...
    def disk_used_pct(self) -> float | None: ...


def _run_cmd(cmd: list[str]) -> str | None:
    """stdout del comando, o ``None`` si no existe/falla/expira. Jamás lanza."""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_RUN_TIMEOUT_S,
            env={**os.environ, "LC_ALL": "C"},  # parsers dependen del formato inglés
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def _parse_chrony_offset(csv_text: str) -> float | None:
    """Offset (s) del `chronyc -c tracking` (CSV): campo 5 = offset actual del sistema."""
    try:
        return float(csv_text.split(",")[4])
    except (IndexError, ValueError):
        return None


_TIMESYNC_OFFSET = re.compile(r"^\s*Offset:\s*([+-]?[0-9.]+)(us|ms|s)\s*$", re.MULTILINE)
_UNIT_S = {"us": 1e-6, "ms": 1e-3, "s": 1.0}


def _parse_timesync_offset(text: str) -> float | None:
    """Offset (s) de `timedatectl timesync-status` — línea `Offset: +800us`.

    `timedatectl show-timesync` (machine-readable) NO expone el offset, así que
    se parsea la salida humana con LC_ALL=C (verificado en el Pi 5 real).
    """
    match = _TIMESYNC_OFFSET.search(text)
    if match is None:
        return None
    try:
        return float(match.group(1)) * _UNIT_S[match.group(2)]
    except ValueError:
        return None


def _parse_cert_days(enddate: str, *, now: datetime | None = None) -> int | None:
    """Días restantes del `openssl x509 -enddate -noout`: `notAfter=Dec 31 23:59:59 2049 GMT`."""
    value = enddate.strip().split("=", 1)[-1].strip()
    try:
        not_after = datetime.strptime(value, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=UTC)
    except ValueError:
        return None
    now = now or datetime.now(UTC)
    return (not_after - now).days


def _to_float(raw: str | None) -> float | None:
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text().strip()
    except (OSError, ValueError):
        return None


class HostProbes:
    """Sondas reales del host (T-1.40), con degradación honesta a ``None``.

    El ejecutor de comandos es inyectable (``run``) para tests deterministas.
    Contrato: ninguna sonda lanza — toda falla degrada a «sin dato».
    """

    def __init__(
        self,
        settings: EdgeSettings,
        run: Callable[[list[str]], str | None] = _run_cmd,
    ) -> None:
        self._settings = settings
        self._run = run

    def temperature_c(self) -> float:
        try:
            return int(_THERMAL.read_text()) / 1000.0
        except (OSError, ValueError):
            return 0.0  # no es un Pi (dev/CI) o el sysfs no está disponible

    def ntp_offset_s(self) -> float | None:
        """Offset del reloj vs NTP: chrony si está activo; si no, systemd-timesyncd."""
        out = self._run(["chronyc", "-c", "tracking"])
        if out:
            offset = _parse_chrony_offset(out)
            if offset is not None:
                return offset
        out = self._run(["timedatectl", "timesync-status"])
        if out:
            return _parse_timesync_offset(out)
        return None

    def ups(self) -> UpsReading:
        """UPS por NUT (`upsc`) o sysfs; sin hardware ⇒ DESCONOCIDO + batería None."""
        reading = self._ups_nut()
        if reading is not None:
            return reading
        reading = self._ups_sysfs()
        if reading is not None:
            return reading
        return UpsReading()  # sin UPS visible: se dice «sin dato», no se inventa 100%

    def cert_days_remaining(self) -> int | None:
        """Vencimiento real del cert mTLS del gateway (el de AWS IoT vence en 2049)."""
        path = self._settings.mqtt_cert_path
        if not path:
            return None
        out = self._run(["openssl", "x509", "-enddate", "-noout", "-in", path])
        if not out:
            return None
        return _parse_cert_days(out)

    def disk_used_pct(self) -> float | None:
        """Uso del disco donde vive el buffer/evidencia ([T-1.53], panel LAN).

        ``shutil.disk_usage`` sobre ``health_disk_path`` (default ``/``: en el
        Pi real cubre el NVMe de /var/lib/takab). Ruta inexistente ⇒ ``None``
        («sin dato»), jamás lanza. El disco lleno ya se maneja defensivo en el
        supervisor (ENOSPC no ciega la detección); esto es solo visibilidad.
        """
        try:
            usage = shutil.disk_usage(self._settings.health_disk_path)
        except (OSError, ValueError):
            return None
        if usage.total <= 0:
            return None
        return usage.used / usage.total * 100.0

    def _ups_nut(self) -> UpsReading | None:
        names = self._run(["upsc", "-l"])
        if not names or not names.strip():
            return None
        name = names.strip().splitlines()[0].strip()
        out = self._run(["upsc", name])
        if not out:
            return None
        kv: dict[str, str] = {}
        for line in out.splitlines():
            key, _, value = line.partition(":")
            kv[key.strip()] = value.strip()
        raw_status = kv.get("ups.status", "")
        if raw_status.startswith("OL"):
            status = UpsStatus.LINE
        elif raw_status.startswith("OB"):
            status = UpsStatus.BATTERY
        else:
            status = UpsStatus.UNKNOWN
        return UpsReading(
            status, _to_float(kv.get("battery.charge")), _to_float(kv.get("battery.runtime"))
        )

    def _ups_sysfs(self) -> UpsReading | None:
        try:
            supplies = sorted(_POWER_SUPPLY.iterdir())
        except OSError:
            return None
        battery: float | None = None
        online: str | None = None
        for supply in supplies:
            kind = _read_text(supply / "type")
            if kind == "Battery" and battery is None:
                battery = _to_float(_read_text(supply / "capacity"))
            elif kind in ("Mains", "UPS") and online is None:
                online = _read_text(supply / "online")
        if battery is None and online is None:
            return None  # el Pi 5 pelón no expone nada aquí (verificado)
        if online is not None:
            status = UpsStatus.LINE if online == "1" else UpsStatus.BATTERY
        else:
            status = UpsStatus.UNKNOWN
        return UpsReading(status, battery, None)


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
        cloud: object | None = None,
        heartbeat_s: float = 60.0,
    ) -> None:
        super().__init__()
        self.settings = settings
        self._gpio = gpio
        self._seedlink = seedlink
        self._probes = probes or HostProbes(settings)
        self._cloud = cloud
        self._heartbeat_s = heartbeat_s
        self._callbacks: list[Callable[[HealthSnapshot], None]] = []
        self._last_snapshot: HealthSnapshot | None = None
        self._last_key: tuple | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def on_snapshot(self, callback: Callable[[HealthSnapshot], None]) -> None:
        """Registra un consumidor de snapshots (p.ej. publicar a la nube, T-1.11)."""
        self._callbacks.append(callback)

    @property
    def last_snapshot(self) -> HealthSnapshot | None:
        """Último snapshot MEDIDO (heartbeat/transición), SIN side effects.

        [T-1.53] El panel LAN lee de aquí: llamar ``snapshot()`` por request
        ejecutaba las sondas (subprocesos con timeout de 2 s) Y disparaba los
        callbacks — cada GET del panel publicaba un health a la nube (~30/min
        con el poll de 2 s en vez del heartbeat de 60 s). La edad del dato la
        declara la UI ("salud medida hace Ns"), jamás se finge frescura.
        """
        return self._last_snapshot

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

    def _mqtt_rtt_ms(self) -> float | None:
        """RTT del último PUBACK QoS1 medido por el conector cloud (None sin dato)."""
        if self._cloud is None:
            return None
        rtt = getattr(self._cloud, "mqtt_rtt_ms", None)
        return float(rtt) if rtt is not None else None

    @staticmethod
    def _safe(probe: Callable[[], _T], default: _T) -> _T:
        """Una sonda rota degrada a su default — jamás mata el hilo del heartbeat."""
        try:
            return probe()
        except Exception:  # noqa: BLE001 — contrato: el latido sobrevive a cualquier sonda
            log.warning("sonda de salud falló; se reporta sin dato", exc_info=True)
            return default

    def snapshot(self, transition_reason: str = "heartbeat") -> HealthSnapshot:
        relays = self._relay_states()
        ups = self._safe(self._probes.ups, UpsReading())
        snap = HealthSnapshot(
            gateway_id=self.settings.gateway_id,
            ntp_offset_s=self._safe(self._probes.ntp_offset_s, None),
            seedlink_lag_s=self._seedlink_lag_s(),
            packet_loss_pct=self._packet_loss_pct(),
            mqtt_rtt_ms=self._safe(self._mqtt_rtt_ms, None),
            ups_status=ups.status,
            battery_pct=ups.battery_pct,
            temperature_c=self._safe(self._probes.temperature_c, 0.0),
            cert_days_remaining=self._safe(self._probes.cert_days_remaining, None),
            # getattr: sondas previas a T-1.53 (fakes/impl externas) pueden no
            # traer disk_used_pct — ausencia = «sin dato», no un crash.
            disk_used_pct=self._safe(getattr(self._probes, "disk_used_pct", _no_disk), None),
            relays=relays,
            transition_reason=transition_reason,
        )
        self._last_snapshot = snap
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
            snap.cert_days_remaining is not None and snap.cert_days_remaining < CERT_WARN_DAYS,
            snap.temperature_c > TEMP_WARN_C,
            snap.seedlink_lag_s > LAG_WARN_S,
        )
        if key != self._last_key:
            cert_txt = (
                f"{snap.cert_days_remaining}d" if snap.cert_days_remaining is not None else "s/d"
            )
            log.info(
                "transición de salud (%s): %s · temp=%.1f°C · lag=%.2fs · cert=%s · loss=%.1f%%",
                reason,
                ups_label(UpsReading(snap.ups_status, snap.battery_pct)),
                snap.temperature_c,
                snap.seedlink_lag_s,
                cert_txt,
                snap.packet_loss_pct,
            )
            self._last_key = key

    def _heartbeat_loop(self) -> None:
        while not self._stop.wait(self._heartbeat_s):
            try:
                self.snapshot("heartbeat")
            except Exception:  # noqa: BLE001 — el latido jamás muere (backlog #28)
                log.exception("heartbeat de salud falló; se reintenta el próximo ciclo")

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
