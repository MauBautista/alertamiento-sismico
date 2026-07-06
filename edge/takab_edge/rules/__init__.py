"""rules — motor de reglas determinista tierizado (blueprint §4.5).

**Sin IA** (regla de oro 1): la decisión de tier/severidad es 100% determinista.
Consume la señal de `gpio` (SASMEX) y las `Feature1s` de `signal`, decide el tier
y ordena la actuación NO-refleja (el reflejo SASMEX→sirena ya ocurrió en `gpio`).

Scaffold de T-1.2: tabla de verdad de los 5 tiers y mapeo tier→comandos. La
cobertura exhaustiva de casos borde (clipping, saturación, dropout y la
deduplicación "SASMEX + umbral local del mismo sismo = UN evento") y la latencia
cruce-de-umbral→decisión <200 ms medida son **T-1.8**.
"""

from __future__ import annotations

import logging

from takab_edge.config import ThresholdBand
from takab_edge.contracts import (
    ActuatorAction,
    ActuatorChannel,
    ActuatorCommand,
    AlertSource,
    Feature1s,
    SasmexSignal,
    Tier,
    TierDecision,
)
from takab_edge.module import EdgeModule

log = logging.getLogger("takab_edge.rules")

#: Secuencia de actuación por tier. `evacuate_or_hold` incluye la **sirena general**
#: (blueprint §4.5): en la ruta SASMEX es idempotente con el reflejo in-process de
#: `gpio`, pero en la ruta puramente instrumental (umbral local sin SASMEX — el caso
#: "Secundario A" del §4.5) es lo que ALERTA audiblemente a los ocupantes; sin ella,
#: un sismo local detectado por umbral cerraría gas y retornaría ascensores en
#: silencio. La matriz completa y la dedup "SASMEX + umbral = UN evento" son T-1.8.
TIER_ACTUATION: dict[Tier, tuple[ActuatorChannel, ...]] = {
    Tier.NORMAL: (),
    Tier.WATCH: (),
    Tier.RESTRICTED: (ActuatorChannel.ELEVATOR, ActuatorChannel.DOOR_RETAINER),
    Tier.EVACUATE_OR_HOLD: (
        ActuatorChannel.SIREN,
        ActuatorChannel.STROBE,
        ActuatorChannel.ELEVATOR,
        ActuatorChannel.DOOR_RETAINER,
        ActuatorChannel.GAS_VALVE,
    ),
    Tier.MANUAL_ONLY: (),
}


def tier_from_features(feature: Feature1s, thresholds: ThresholdBand) -> TierDecision:
    """Tabla de verdad determinista feature→tier (esqueleto; casos borde en T-1.8)."""
    reasons: list[str] = []

    # Sensores degradados o datos contradictorios → decide humano (nunca automatiza).
    if feature.clipping or feature.health_score < 0.5:
        reasons.append("sensor degradado (clipping/health_score bajo)")
        return TierDecision(tier=Tier.MANUAL_ONLY, source=AlertSource.THRESHOLD, reasons=reasons)

    trip = feature.pga >= thresholds.pga_trip_g or feature.pgv >= thresholds.pgv_trip_cms
    watch = feature.pga >= thresholds.pga_watch_g or feature.pgv >= thresholds.pgv_watch_cms

    if trip:
        reasons.append(f"disparo: PGA={feature.pga:.3f}g PGV={feature.pgv:.2f}cm/s")
        tier = Tier.EVACUATE_OR_HOLD
    elif watch:
        reasons.append(f"cautela: PGA={feature.pga:.3f}g PGV={feature.pgv:.2f}cm/s")
        tier = Tier.WATCH
    else:
        tier = Tier.NORMAL

    return TierDecision(
        tier=tier,
        source=AlertSource.THRESHOLD,
        severity=feature.pga,
        reasons=reasons,
    )


def tier_from_sasmex(signal: SasmexSignal) -> TierDecision:
    """SASMEX activo (no-prueba) → secuencia de protección inmediata (blueprint §4.5)."""
    return TierDecision(
        tier=Tier.EVACUATE_OR_HOLD,
        source=AlertSource.SASMEX,
        severity=1.0,
        reasons=["alerta SASMEX (WR-1) — canal primario"],
    )


def commands_for(decision: TierDecision) -> list[ActuatorCommand]:
    """Mapea la decisión de tier a comandos de actuador (secuencia no-refleja)."""
    channels = TIER_ACTUATION.get(decision.tier, ())
    return [
        ActuatorCommand(
            channel=channel,
            action=ActuatorAction.ACTIVATE,
            event_id=decision.event_id,
        )
        for channel in channels
    ]


class RuleEngine(EdgeModule):
    """Evalúa entradas y produce decisiones de tier + comandos de actuador."""

    name = "rules"
    depends_on = ("gpio", "signal")

    def __init__(self, thresholds: ThresholdBand) -> None:
        super().__init__()
        self.thresholds = thresholds
        self._last_decision: TierDecision | None = None

    @property
    def last_decision(self) -> TierDecision | None:
        return self._last_decision

    def evaluate_sasmex(self, signal: SasmexSignal) -> TierDecision | None:
        # El pulso de prueba de CIRES no genera decisión de actuación (SPOF-03).
        if not signal.active or signal.is_test:
            return None
        decision = tier_from_sasmex(signal)
        self._last_decision = decision
        log.warning("decisión SASMEX → %s", decision.tier.value)
        return decision

    def evaluate_features(self, feature: Feature1s) -> TierDecision:
        decision = tier_from_features(feature, self.thresholds)
        self._last_decision = decision
        return decision

    def _on_start(self) -> None:
        log.info("motor de reglas activo (umbral disparo PGA=%.3fg)", self.thresholds.pga_trip_g)
