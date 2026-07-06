"""rules — motor de reglas determinista tierizado (blueprint §4.5).

**Sin IA** (regla de oro 1): la decisión de tier/severidad es 100% determinista.
Consume la señal de `gpio` (SASMEX) y las `Feature1s` de `signal`, decide el tier y
ordena la actuación NO-refleja (el reflejo SASMEX→sirena ya ocurrió en `gpio`).

T-1.8: tabla de verdad **multi-canal** con corroboración (≥2 sensores en disparo →
`evacuate_or_hold`; 1 → `restricted`; degradados → `manual_only`), **dedup de doble
disparo** (SASMEX + umbral local del mismo sismo dentro de una ventana = UN evento,
no dos), **staleness** (un canal que deja de emitir cae de la decisión — dropout),
latencia umbral→decisión **<200 ms** (medida) y **logging por transición de tier**
(regla de oro 10; contrato de `rule_evaluations`). Umbrales por edificio (config,
firmada en T-1.12).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from time import perf_counter

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
    new_event_id,
    utcnow,
)
from takab_edge.module import EdgeModule

log = logging.getLogger("takab_edge.rules")

#: Secuencia de actuación por tier. `evacuate_or_hold` incluye la **sirena general**
#: (blueprint §4.5): en la ruta SASMEX es idempotente con el reflejo in-process de
#: `gpio`, pero en la ruta puramente instrumental (umbral local sin SASMEX — el caso
#: "Secundario A" del §4.5) es lo que ALERTA audiblemente a los ocupantes.
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


def _is_degraded(feature: Feature1s) -> bool:
    # SÓLO dropout/ruido (health bajo, p.ej. canal muerto rms=0 → health 0) es no-fiable
    # y se excluye. El CLIPPING (saturación del ADC de 24 bits) NO es degradación: es
    # evidencia MONÓTONA de sacudida ≥ fondo de escala → cuenta como DISPARO (fail-loud).
    return feature.health_score < 0.5


def _is_trip(feature: Feature1s, thresholds: ThresholdBand) -> bool:
    # La saturación cuenta como disparo (vio ≥ fondo de escala, supera cualquier umbral).
    return (
        feature.clipping
        or feature.pga >= thresholds.pga_trip_g
        or feature.pgv >= thresholds.pgv_trip_cms
    )


def decide(features: dict[str, Feature1s], thresholds: ThresholdBand) -> tuple[Tier, list[str]]:
    """Tabla de verdad multi-canal (blueprint §4.5). Fuente ÚNICA de la decisión.

    - Ningún canal confiable (todos degradados) → `manual_only` (decide humano).
    - ≥2 canales confiables en disparo → `evacuate_or_hold` (corroboración).
    - 1 canal confiable en disparo → `restricted`.
    - ≥1 canal confiable en cautela → `watch`.
    - Ninguna excedencia → `normal`.

    Un canal degradado (clipping/health bajo) se EXCLUYE del conteo (magnitud no
    confiable) pero no bloquea a los canales limpios que sí disparan: un evento fuerte
    que satura un sensor debe seguir evacuando por los sensores sanos (dirección segura).
    """
    if not features:
        return Tier.NORMAL, []
    reliable = {ch: f for ch, f in features.items() if not _is_degraded(f)}
    if not reliable:
        degraded = sorted(features)
        return Tier.MANUAL_ONLY, [f"todos los canales degradados ({', '.join(degraded)})"]

    trip = sorted(ch for ch, f in reliable.items() if _is_trip(f, thresholds))
    watch = sorted(
        ch
        for ch, f in reliable.items()
        if f.pga >= thresholds.pga_watch_g or f.pgv >= thresholds.pgv_watch_cms
    )

    if len(trip) >= 2:
        return Tier.EVACUATE_OR_HOLD, [f"disparo confirmado por {len(trip)} sensores: {trip}"]
    if len(trip) == 1:
        return Tier.RESTRICTED, [f"disparo en un sensor: {trip[0]}"]
    if watch:
        return Tier.WATCH, [f"cautela en {len(watch)} sensor(es): {watch}"]
    return Tier.NORMAL, []


def tier_from_features(feature: Feature1s, thresholds: ThresholdBand) -> TierDecision:
    """Decisión de un solo canal (envuelve `decide` con un único canal)."""
    tier, reasons = decide({feature.channel: feature}, thresholds)
    return TierDecision(
        tier=tier, source=AlertSource.THRESHOLD, severity=feature.pga, reasons=reasons
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
    return [
        ActuatorCommand(channel=channel, action=ActuatorAction.ACTIVATE, event_id=decision.event_id)
        for channel in TIER_ACTUATION.get(decision.tier, ())
    ]


class RuleEngine(EdgeModule):
    """Acumula features por canal, decide el tier y deduplica eventos por episodio."""

    name = "rules"
    depends_on = ("gpio", "signal")

    def __init__(
        self,
        thresholds: ThresholdBand,
        dedup_window_s: float = 30.0,
        staleness_s: float = 3.0,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        super().__init__()
        self.thresholds = thresholds
        self.dedup_window_s = dedup_window_s
        self.staleness_s = staleness_s
        # Reloj ÚNICO de recepción del Pi para correlacionar episodios (no mezclar el
        # reloj de datos del Shake con el de pared del contacto SASMEX).
        self._clock = clock or utcnow
        self._features: dict[str, Feature1s] = {}
        self._last_tier: Tier | None = None
        self._last_decision: TierDecision | None = None
        self._last_latency_s: float | None = None
        self._event_id: str | None = None
        self._episode_end: datetime | None = None

    @property
    def last_decision(self) -> TierDecision | None:
        return self._last_decision

    @property
    def last_latency_s(self) -> float | None:
        """Latencia medida cruce-de-umbral→decisión (presupuesto §4.3 <200 ms)."""
        return self._last_latency_s

    def evaluate_features(self, feature: Feature1s) -> TierDecision:
        started = perf_counter()
        self._features[feature.channel] = feature
        self._drop_stale(feature.window_start)
        tier, reasons = decide(self._features, self.thresholds)
        severity = max((f.pga for f in self._features.values()), default=feature.pga)
        decision = self._emit(tier, AlertSource.THRESHOLD, reasons, severity)
        self._last_latency_s = perf_counter() - started
        return decision

    def evaluate_sasmex(self, signal: SasmexSignal) -> TierDecision | None:
        # El pulso de prueba de CIRES no genera decisión de actuación (SPOF-03).
        if not signal.active or signal.is_test:
            return None
        return self._emit(
            Tier.EVACUATE_OR_HOLD,
            AlertSource.SASMEX,
            ["alerta SASMEX (WR-1) — canal primario"],
            severity=1.0,
        )

    def _drop_stale(self, now: datetime) -> None:
        """Un canal que dejó de emitir (dropout) cae de la decisión tras `staleness_s`."""
        cutoff = now - timedelta(seconds=self.staleness_s)
        for channel in [ch for ch, f in self._features.items() if f.window_start < cutoff]:
            del self._features[channel]

    def _emit(
        self,
        tier: Tier,
        source: AlertSource,
        reasons: list[str],
        severity: float,
    ) -> TierDecision:
        # Dedup de episodio: alertas dentro de la ventana (reloj ÚNICO de recepción)
        # comparten event_id (UN evento). Escalación de tier → distinto (event_id, tier),
        # que el CloudConnector NO deduplica (la nube hace upsert al tier mayor, T-1.17).
        event_id = new_event_id() if tier is Tier.NORMAL else self._episode_event_id(self._clock())
        decision = TierDecision(
            event_id=event_id, tier=tier, source=source, severity=severity, reasons=reasons
        )
        # Logging POR TRANSICIÓN de tier (regla de oro 10; contrato de rule_evaluations).
        if tier != self._last_tier:
            log.warning(
                "transición de tier %s → %s (%s)",
                self._last_tier.value if self._last_tier else "—",
                tier.value,
                "; ".join(reasons) or "-",
            )
            self._last_tier = tier
        self._last_decision = decision
        return decision

    def _episode_event_id(self, when: datetime) -> str:
        if self._event_id is None or self._episode_end is None or when > self._episode_end:
            self._event_id = new_event_id()
        self._episode_end = when + timedelta(seconds=self.dedup_window_s)
        return self._event_id

    def _on_start(self) -> None:
        log.info(
            "motor de reglas activo (disparo PGA=%.3fg, dedup %.0fs)",
            self.thresholds.pga_trip_g,
            self.dedup_window_s,
        )
