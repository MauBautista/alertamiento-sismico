"""health — autodiagnóstico del gabinete (snapshots por transición + heartbeat).

Scaffold de T-1.2: compone un `HealthSnapshot` con el estado de relés (de `gpio`)
y emite log SOLO en transición (regla de oro 10: nunca logging por intervalo
continuo). Los medidores reales —NTP offset, lag SeedLink, packet loss, UPS
(`RED ELÉCTRICA %`/`EN BATERÍA`), temperatura, `cert_days_remaining`— son **T-1.10**.
"""

from __future__ import annotations

import logging

from takab_edge.config import EdgeSettings
from takab_edge.contracts import HealthSnapshot, RelayState
from takab_edge.gpio import GpioController
from takab_edge.module import EdgeModule

log = logging.getLogger("takab_edge.health")


class HealthMonitor(EdgeModule):
    """Produce snapshots de salud del gabinete."""

    name = "health"

    def __init__(self, settings: EdgeSettings, gpio: GpioController | None = None) -> None:
        super().__init__()
        self.settings = settings
        self._gpio = gpio
        self._last_key: tuple | None = None

    def _relay_states(self) -> list[RelayState]:
        if self._gpio is not None and self._gpio.running:
            return self._gpio.relay_states()
        return []

    def snapshot(self, transition_reason: str = "heartbeat") -> HealthSnapshot:
        relays = self._relay_states()
        snap = HealthSnapshot(
            gateway_id=self.settings.gateway_id,
            relays=relays,
            transition_reason=transition_reason,
        )
        # Log por transición: sólo si cambió el estado observable (relés/UPS).
        key = (tuple((r.channel, r.energized) for r in relays), snap.ups_status)
        if key != self._last_key:
            log.info("transición de salud: %s", transition_reason)
            self._last_key = key
        return snap

    def _on_start(self) -> None:
        log.info("autodiagnóstico de salud activo")
