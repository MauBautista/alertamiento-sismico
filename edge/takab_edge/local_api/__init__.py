"""local_api — dashboard/control local del edificio (LAN, sin internet).

Scaffold de T-1.2: lógica de estado y de comando de silencio, desacoplada del
transporte. El **servidor HTTP en LAN** accesible sin internet (estado, último
evento, prueba de sirena, silencio por LAN) es **T-1.13** (RBAC §4.2: fallback
cuando la WAN está caída).
"""

from __future__ import annotations

import logging

from takab_edge.gpio import GpioController
from takab_edge.health import HealthMonitor
from takab_edge.module import EdgeModule
from takab_edge.rules import RuleEngine

log = logging.getLogger("takab_edge.local_api")


class LocalDashboard(EdgeModule):
    """Expone estado del gabinete y acepta el comando de silencio por LAN."""

    name = "local_api"
    depends_on = ("gpio", "rules", "health")

    def __init__(
        self,
        gpio: GpioController,
        rules: RuleEngine,
        health: HealthMonitor,
    ) -> None:
        super().__init__()
        self._gpio = gpio
        self._rules = rules
        self._health = health

    def status(self) -> dict:
        """Snapshot para el dashboard LAN (loading/error/empty/stale los maneja la UI)."""
        decision = self._rules.last_decision
        snap = self._health.snapshot()
        return {
            "gateway_id": snap.gateway_id,
            "sasmex_active": self._gpio.sasmex_active,
            "last_tier": decision.tier.value if decision else None,
            "relays": [r.model_dump(mode="json") for r in self._gpio.relay_states()],
            "captured_at": snap.captured_at.isoformat(),
        }

    def silence(self) -> None:
        """Comando de silencio por LAN: inhibe el reflejo a sirena (T-1.3 lo endurece)."""
        self._gpio.set_reflex_enabled(False)
        log.warning("silencio solicitado por LAN")

    def _on_start(self) -> None:
        log.info("dashboard LAN activo (transporte HTTP: T-1.13)")
