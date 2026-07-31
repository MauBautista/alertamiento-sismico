"""ShakeAggregator — agregado rodante de sacudida EN RAM para el panel (T-2.19).

El hueco que cierra: no existía agregación temporal en el edge — el panel no podía
decir "el máximo de hoy fue X" ni "el ruido de fondo va subiendo".

NO es logging por intervalo (regla de oro 10): es memoria pura, no se publica ni se
persiste, y se pierde al reiniciar A PROPÓSITO — el panel lo rotula DESDE EL
ARRANQUE (`since`) en vez de fingir una continuidad que el gabinete no tiene. La
nube ya tiene sus continuous aggregates (`site_metrics_1m`/`site_metrics_1h`).

Tres agregados (contrato §5.1 de la spec del panel):

- **Buckets horarios UTC-floor** por canal (PGA/PGV máximos), rodantes: se podan al
  escribir los que quedan fuera de la ventana de 24 h del dato más nuevo. `hourly[]`
  arranca corto y crece hasta 24.
- **`events_by_tier`**: cuenta TRANSICIONES de tier (no ticks — un `watch` sostenido
  10 s es UN evento). Lo alimenta un observador en el supervisor, no `RuleEngine`
  (módulo crítico intocable). Arranca en `normal`: un día tranquilo son puros ceros.
- **Piso de ruido**: MIN por minuto del rms→mg del MEMS (canales EN*; el geófono EH*
  no es aceleración), deque de 180 min; tendencia = mediana de los últimos 15 min
  contra los 15 anteriores (±20%). Baselines 0.6–1.1 mg MEDIDOS en el gabinete real
  (T-1.41), declarados para pintar el piso contra su rango conocido.
"""

from __future__ import annotations

import threading
from collections import deque
from datetime import datetime, timedelta
from statistics import median

from takab_edge.contracts import Feature1s, Tier, TierDecision, utcnow

#: Piso de ruido conocido del MEMS en el gabinete real (mg), medido en T-1.41.
_BASELINE_LOW_MG = 0.6
_BASELINE_HIGH_MG = 1.1

_G = 9.80665  # m/s² por g

#: Historia del piso de ruido: 180 minutos completados.
_NOISE_MINUTES = 180
#: Tendencia: mediana de los últimos N minutos vs los N anteriores, ±20%.
_TREND_WINDOW_MIN = 15
_TREND_RATIO = 1.2

#: Ventana rodante de los buckets horarios.
_WINDOW_HOURS = 24


def _hour_floor(ts: datetime) -> datetime:
    return ts.replace(minute=0, second=0, microsecond=0)


def _minute_floor(ts: datetime) -> datetime:
    return ts.replace(second=0, microsecond=0)


class ShakeAggregator:
    """Agregado de sacudida thread-safe: escribe el hilo de datos, lee el panel."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._since = utcnow()
        # Por canal: {hour_start: [pga_max, pgv_max]} — ≤24 buckets vivos.
        self._buckets: dict[str, dict[datetime, list[float]]] = {}
        self._events: dict[str, int] = {tier.value: 0 for tier in Tier}
        self._last_tier: Tier = Tier.NORMAL
        # Piso de ruido: minutos COMPLETADOS (mg) + minuto en curso.
        self._noise_done: deque[float] = deque(maxlen=_NOISE_MINUTES)
        self._noise_minute: datetime | None = None
        self._noise_min_mg: float | None = None

    # ------------------------------------------------------------ escritura

    def observe_feature(self, feature: Feature1s, accel_sens_ms2_per_count: float) -> None:
        """Acumula una feature 1 s (hilo de datos). O(1); jamás publica."""
        hour = _hour_floor(feature.window_start)
        with self._lock:
            buckets = self._buckets.setdefault(feature.channel, {})
            bucket = buckets.get(hour)
            if bucket is None:
                buckets[hour] = [feature.pga, feature.pgv]
            else:
                bucket[0] = max(bucket[0], feature.pga)
                bucket[1] = max(bucket[1], feature.pgv)
            # Poda por tiempo DEL DATO (no de pared): rodante y determinista.
            cutoff = hour - timedelta(hours=_WINDOW_HOURS - 1)
            for stale in [h for h in buckets if h < cutoff]:
                del buckets[stale]

            if feature.channel.startswith("EN"):
                mg = feature.rms * accel_sens_ms2_per_count / _G * 1000.0
                minute = _minute_floor(feature.window_start)
                if self._noise_minute is None or minute > self._noise_minute:
                    if self._noise_min_mg is not None:
                        self._noise_done.append(self._noise_min_mg)
                    self._noise_minute = minute
                    self._noise_min_mg = mg
                elif minute == self._noise_minute:
                    self._noise_min_mg = min(self._noise_min_mg, mg)
                # Un minuto MÁS VIEJO que el vigente (reordenamiento raro): se ignora.

    def observe_decision(self, decision: TierDecision) -> None:
        """Cuenta TRANSICIONES de tier (no ticks). La llama el supervisor."""
        with self._lock:
            if decision.tier is not self._last_tier:
                self._events[decision.tier.value] += 1
                self._last_tier = decision.tier

    # -------------------------------------------------------------- lectura

    def _trend(self) -> str:
        done = list(self._noise_done)
        if len(done) < 2:  # <2 minutos completados: sin base para tendencia
            return "stable"
        recent = done[-_TREND_WINDOW_MIN:]
        previous = done[-2 * _TREND_WINDOW_MIN : -_TREND_WINDOW_MIN]
        if not previous:
            previous = done[: max(1, len(done) - len(recent))]
        base = median(previous)
        if base <= 0.0:
            return "stable"
        ratio = median(recent) / base
        if ratio > _TREND_RATIO:
            return "rising"
        if ratio < 1.0 / _TREND_RATIO:
            return "falling"
        return "stable"

    def snapshot(self) -> dict:
        """Estado §5.1 listo para JSON. Lectura PURA: jamás muta ni publica."""
        with self._lock:
            by_channel: dict[str, dict] = {}
            for channel, buckets in sorted(self._buckets.items()):
                ordered = sorted(buckets.items())
                by_channel[channel] = {
                    "pga_g_max_24h": max(pga for _, (pga, _) in ordered),
                    "pgv_cms_max_24h": max(pgv for _, (_, pgv) in ordered),
                    "hourly": [
                        {
                            "hour_start": hour.isoformat(),
                            "pga_g_max": pga,
                            "pgv_cms_max": pgv,
                        }
                        for hour, (pga, pgv) in ordered
                    ],
                }
            current = self._noise_min_mg
            if current is None and self._noise_done:
                current = self._noise_done[-1]
            return {
                "since": self._since.isoformat(),
                "by_channel": by_channel,
                "events_by_tier": dict(self._events),
                "noise_floor": {
                    "current_mg": current,
                    "baseline_low_mg": _BASELINE_LOW_MG,
                    "baseline_high_mg": _BASELINE_HIGH_MG,
                    "trend": self._trend(),
                },
            }


__all__ = ["ShakeAggregator"]
