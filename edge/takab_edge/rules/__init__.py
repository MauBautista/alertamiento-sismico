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
import threading
from collections import deque
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

#: Tope del ring de transiciones del panel LAN (T-1.53).
_TRANSITIONS_MAX = 32

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
    """Mapea la decisión de tier a comandos de actuador (secuencia no-refleja).

    [T-2.86.a · RO-4.e] Cada comando sale ya marcado con su CAUSA (derivada del
    `AlertSource` de la decisión) y su ACTOR. Aquí y no en el `ActuatorManager`
    porque es aquí donde se sabe por qué: aguas abajo sólo hay canales y acciones,
    y una bitácora que adivinara la causa sería peor que no tenerla.

    El actor de una secuencia de tier no es una persona y no se finge que lo sea:
    es el WR-1 (contacto seco) o el motor de reglas determinista de este gabinete.
    """
    from takab_edge.audit import ACTOR_RULES, ACTOR_WR1, cause_for_alert_source

    actor = ACTOR_WR1 if decision.source is AlertSource.SASMEX else ACTOR_RULES
    return [
        ActuatorCommand(
            channel=channel,
            action=ActuatorAction.ACTIVATE,
            event_id=decision.event_id,
            cause=cause_for_alert_source(decision.source),
            actor=actor,
        )
        for channel in TIER_ACTUATION.get(decision.tier, ())
    ]


class RuleEngine(EdgeModule):
    """Acumula features por canal, decide el tier y deduplica eventos por episodio."""

    name = "rules"
    depends_on = ("gpio", "signal")
    critical = True  # decisión de tier determinista (umbral→actuador); fail-fast

    def __init__(
        self,
        thresholds: ThresholdBand,
        staleness_s: float = 3.0,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        super().__init__()
        self.thresholds = thresholds
        self.staleness_s = staleness_s
        # Reloj ÚNICO de recepción del Pi para correlacionar episodios (no mezclar el
        # reloj de datos del Shake con el de pared del contacto SASMEX).
        self._clock = clock or utcnow
        self._features: dict[str, Feature1s] = {}
        self._last_tier: Tier | None = None
        self._last_decision: TierDecision | None = None
        self._last_latency_s: float | None = None
        self._event_id: str | None = None
        # [T-7.49] La identidad del episodio es UN campo, y su acceso es
        # read-modify-write desde DOS hilos (el de SeedLink por
        # `evaluate_features` y el callback del dueño de los pines por
        # `evaluate_sasmex`). Sin lock, el doble disparo SASMEX+umbral del mismo
        # sismo —que es el caso NORMAL de un sismo avisado— podía acuñar dos.
        #
        # Lock PROPIO y no `_transitions_lock`: aquél lo toman los hilos HTTP del
        # panel a 1 Hz (`recent_transitions`), y la identidad no debe ser
        # alcanzable desde un kiosco LAN. Medido en portátil: adquirir y soltar
        # son ~0.14 µs contra los ~6 µs de `evaluate_features` y los 200 ms de
        # presupuesto del blueprint §4.3. El reflejo SASMEX→sirena NO pasa por
        # aquí (vive entero en `gpio._dispatch_sasmex`): lo que queda aguas abajo
        # es la actuación secundaria.
        self._episode_lock = threading.Lock()
        # [T-1.53] Últimas transiciones de tier para el panel LAN. Dos hilos
        # escriben aquí (seedlink→evaluate_features y callback gpio→
        # evaluate_sasmex) y los hilos HTTP leen: lock obligatorio. En memoria
        # a propósito (la nube persiste los LocalEvent; el panel declara
        # "desde el arranque").
        self._transitions: deque[dict] = deque(maxlen=_TRANSITIONS_MAX)
        self._transitions_lock = threading.Lock()

    @property
    def last_decision(self) -> TierDecision | None:
        return self._last_decision

    @property
    def last_latency_s(self) -> float | None:
        """Latencia medida cruce-de-umbral→decisión (presupuesto §4.3 <200 ms)."""
        return self._last_latency_s

    def recent_transitions(self, limit: int = 10) -> list[dict]:
        """Últimas transiciones de tier (más recientes primero) para el panel LAN."""
        with self._transitions_lock:
            items = list(self._transitions)
        return list(reversed(items))[:limit]

    def apply_thresholds(self, thresholds: ThresholdBand) -> None:
        """Adopta EN VIVO una banda de umbral nueva (config por sitio, T-1.71).

        Rebind atómico (CPython) de un objeto ya validado por `ConfigStore`:
        `decide()` lee `self.thresholds` fresco en cada ventana, así que la
        siguiente evaluación usa la banda nueva sin reconstruir el motor. NO toca
        el camino SASMEX (`evaluate_sasmex` ignora umbrales) ni lanza a mitad de
        stream (módulo crítico): la banda llega ya validada.
        """
        self.thresholds = thresholds
        log.info(
            "umbrales aplicados en vivo (disparo PGA=%.3fg, PGV=%.1f cm/s)",
            thresholds.pga_trip_g,
            thresholds.pgv_trip_cms,
        )

    def reset(self) -> None:
        """Cierre manual de alerta por operador (LAN, T-2.26): re-arma a NORMAL.

        Contraparte de ``gpio.reset()`` para el ESTADO DE DECISIÓN: sin esto,
        ``last_decision`` queda congelado en el tier del episodio hasta que
        llegue una feature nueva (SeedLink caído ⇒ para siempre) y el panel
        nunca sale de alerta. Termina el episodio de dedup: un disparo
        posterior es un EVENTO NUEVO (``event_id`` distinto). Registra la
        transición (regla de oro 10) con fuente ``manual`` SOLO en el ring del
        panel — la nube no recibe nada por aquí (el reset no pasa por la
        publicación de eventos). Idempotente: llamable N veces sin lanzar.
        """
        old = self._last_tier
        closed_event = self._event_id
        # ⚠️ [T-7.49] REBIND y no `.clear()`: `decide()` puede estar iterando este
        # dict en el hilo de SeedLink, y vaciarlo bajo sus pies lanza
        # `RuntimeError: dictionary changed size during iteration` — que
        # `_run_transport` rotularía «SeedLink desconectado» y encendería la
        # alarma de sensor mudo con el sensor vivo. El rebind es atómico en
        # CPython y el ciclo en vuelo termina sobre el dict viejo, que es
        # correcto: ya estaba decidiendo con las features de antes del reset.
        self._features = {}
        self.end_episode()
        decision = TierDecision(
            tier=Tier.NORMAL,
            source=AlertSource.MANUAL,
            severity=0.0,
            reasons=["alerta cerrada por operador (LAN)"],
        )
        if old is not None and old is not Tier.NORMAL:
            log.warning(
                "transición de tier %s → %s (%s)",
                old.value,
                Tier.NORMAL.value,
                "; ".join(decision.reasons),
            )
            with self._transitions_lock:
                self._transitions.append(
                    {
                        "at": self._clock().isoformat(),
                        "from_tier": old.value,
                        "to_tier": Tier.NORMAL.value,
                        "source": AlertSource.MANUAL.value,
                        # El event_id del episodio CERRADO, para trazabilidad.
                        "event_id": closed_event or decision.event_id,
                        "pga": None,  # el cierre no es una medición
                        "reasons": list(decision.reasons),
                    }
                )
        self._last_tier = Tier.NORMAL
        self._last_decision = decision

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
            with self._transitions_lock:
                self._transitions.append(
                    {
                        "at": self._clock().isoformat(),
                        "from_tier": self._last_tier.value if self._last_tier else None,
                        "to_tier": tier.value,
                        "source": source.value,
                        "event_id": event_id,
                        # severidad = PGA pico SOLO si la fuente es instrumental;
                        # SASMEX es booleano y su 1.0 no es una medición.
                        "pga": severity if source is AlertSource.THRESHOLD else None,
                        "reasons": list(reasons),
                    }
                )
            self._last_tier = tier
        self._last_decision = decision
        return decision

    def _episode_event_id(self, when: datetime) -> str:
        """La identidad del episodio en curso. Se ACUÑA, no se consulta.

        ⚠️ **[T-7.49] Aquí vivía el segundo reloj del gabinete**, y por eso un
        solo sismo se partía en dos incidentes. Caducaba a los 30 s
        (`dedup_window_s`) mientras el `EpisodeTracker` exige 90 s de silencio
        para dar el episodio por terminado — y los dos no miden desde el mismo
        instante, así que **ningún valor los concilia**: con el enclavado SASMEX
        puesto (que no baja hasta que el operador re-arma) el reloj del silencio
        ni arranca, y éste caducaba siempre.

        El peor caso no era una calma rara: era **el sismo lejano avisado por
        SASMEX**, que es la razón de ser del producto. El aviso acuñaba un id, el
        suelo seguía quieto mientras la onda viajaba —y un `normal` no pasa por
        aquí, así que no extendía nada— y la sacudida de 50 s después acuñaba
        otro. El segundo incidente, instrumental y sin cuórum, **tapaba al
        primero** en el teléfono del ocupante (`T-2.105`).

        Ahora sólo hay un reloj, y es del seguidor: esto acuña una vez y retira
        cuando `end_episode()` lo dice.
        """
        with self._episode_lock:
            if self._event_id is None:
                self._event_id = new_event_id()
            return self._event_id

    def end_episode(self) -> None:
        """Jubila la identidad en curso. Lo llama quien SABE que el episodio acabó.

        Hoy es el `EpisodeTracker`, que es la única autoridad sobre el final de un
        episodio y lo decide por dos razones declaradas: silencio o cota. El motor
        no lo decide por su cuenta a propósito — tener un criterio propio aquí es
        exactamente lo que `T-7.49` vino a quitar.

        Idempotente y sin I/O: se puede llamar desde el hilo advisory sin que nada
        pueda propagar al camino de actuación.
        """
        with self._episode_lock:
            self._event_id = None

    def adopt_episode(self, event_id: str) -> None:
        """Hereda una identidad ya existente. Sólo para el arranque.

        El `EpisodeTracker` persiste su episodio para sobrevivir al corte de luz
        —la forma más probable de que un sismo real termine— y el motor no
        persiste nada. Sin esto, tras un reinicio a mitad de sismo el siguiente
        disparo acuñaría un id nuevo **con probabilidad 1**, que es el segundo
        camino de divergencia que `T-7.49` cerró.
        """
        with self._episode_lock:
            self._event_id = event_id

    def _on_start(self) -> None:
        log.info(
            "motor de reglas activo (disparo PGA=%.3fg; el episodio lo cierra el seguidor)",
            self.thresholds.pga_trip_g,
        )
