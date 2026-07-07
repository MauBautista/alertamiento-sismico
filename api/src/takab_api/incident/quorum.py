"""Matemática PURA del quórum distance-aware (blueprint §4.5). Sin DB.

La correlación de red vive en la NUBE y NUNCA bloquea la actuación local del
edge; aquí sólo está el álgebra determinista: la ventana de asociación
consciente de la distancia entre sitios. La distancia real la inyecta el engine
con PostGIS (``ST_Distance(sites.geom)``) vía ``dist_fn``; esta capa es agnóstica
de la geometría y se testea sin Postgres.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

logger = logging.getLogger(__name__)

# Tope físico DURO de la ventana de asociación. Un rule_set de un tenant NO puede
# ampliar la ventana (y con ella el alcance del fail-open cross-tenant, §4.5)
# arbitrariamente: el spread real de arribos inter-ciudad es ~17 s a 110 km, así
# que 60 s es holgado. Valores mayores se recortan a este tope (no suprimen).
_MAX_WINDOW_CEILING_S = 60.0


class _QuorumDefaults(Protocol):
    """Proveedor de defaults del quórum (``Settings`` u otro stand-in)."""

    quorum_min_nodes: int
    quorum_v_p_km_s: float
    quorum_margin_s: float
    quorum_max_window_s: float


@dataclass(frozen=True)
class QuorumParams:
    """Parámetros de asociación resueltos (rule_set → tenant → defaults)."""

    min_nodes: int
    v_p_km_s: float
    margin_s: float
    max_window_s: float


@dataclass(frozen=True)
class Detection:
    """Dato mínimo de una detección de sitio (una fila de incidente no corroborado)."""

    site_id: str
    sensor_id: str
    detected_at: datetime
    pga_g: float
    lon: float
    lat: float


@dataclass(frozen=True)
class Vote:
    """Voto de un miembro del cúmulo: su detección y su desfase vs la ancla."""

    detection: Detection
    delta_s: float


@dataclass(frozen=True)
class ClusterResult:
    """Cúmulo asociado a la ancla cuando alcanza el quórum (≥ min_nodes)."""

    anchor: Detection
    members: list[Detection]
    votes: list[Vote]


def resolve_params(config: dict | None, settings: _QuorumDefaults) -> QuorumParams:
    """Resuelve los parámetros: usa ``config['quorum']`` si viene, si no los
    defaults de ``settings``. Cada campo se valida por separado; un valor
    inválido cae al default de ese campo (degradación grácil + log)."""
    defaults = QuorumParams(
        min_nodes=settings.quorum_min_nodes,
        v_p_km_s=settings.quorum_v_p_km_s,
        margin_s=settings.quorum_margin_s,
        max_window_s=settings.quorum_max_window_s,
    )
    raw = config.get("quorum") if isinstance(config, dict) else None
    if not isinstance(raw, dict):
        return defaults
    window = _field_num(raw, "max_window_s", defaults.max_window_s, valid=lambda v: v > 0)
    capped = min(window, _MAX_WINDOW_CEILING_S)
    if capped < window:
        logger.warning(
            "quorum config: max_window_s %r excede el tope físico %.0fs → %.0fs",
            window,
            _MAX_WINDOW_CEILING_S,
            capped,
        )
    return QuorumParams(
        min_nodes=_field_int(raw, "min_nodes", defaults.min_nodes, valid=lambda v: v >= 2),
        v_p_km_s=_field_num(raw, "v_p_km_s", defaults.v_p_km_s, valid=lambda v: v > 0),
        margin_s=_field_num(raw, "margin_s", defaults.margin_s, valid=lambda v: v >= 0),
        max_window_s=capped,
    )


def associates(anchor: Detection, other: Detection, dist_km: float, p: QuorumParams) -> bool:
    """¿``other`` asocia con ``anchor``? |Δt| ≤ dist/v_P + margin, con tope duro
    |Δt| ≤ max_window_s. Δt en segundos."""
    dt = abs((other.detected_at - anchor.detected_at).total_seconds())
    if dt > p.max_window_s:
        return False
    return dt <= dist_km / p.v_p_km_s + p.margin_s


def correlate(
    detections: list[Detection],
    dist_fn: Callable[[Detection, Detection], float],
    p: QuorumParams,
) -> ClusterResult | None:
    """Ancla = detección más temprana; cuenta las que asocian con ella (incluida).
    Si el conteo ≥ min_nodes devuelve el cúmulo con ``delta_s`` por miembro
    (detected_at − ancla; 0 para la ancla). Determinista y orden-independiente:
    ordena internamente y desempata por (detected_at, site_id, sensor_id).
    ``dist_fn`` sólo se invoca sobre pares (ancla, otro)."""
    if len(detections) < p.min_nodes:
        return None
    ordered = sorted(detections, key=lambda d: (d.detected_at, d.site_id, d.sensor_id))
    anchor = ordered[0]
    members = [d for d in ordered if d is anchor or associates(anchor, d, dist_fn(anchor, d), p)]
    if len(members) < p.min_nodes:
        return None
    votes = [
        Vote(detection=d, delta_s=(d.detected_at - anchor.detected_at).total_seconds())
        for d in members
    ]
    return ClusterResult(anchor=anchor, members=members, votes=votes)


def _field_num(raw: dict, key: str, default: float, *, valid: Callable[[float], bool]) -> float:
    if key not in raw:
        return default
    try:
        val = float(raw[key])
    except (TypeError, ValueError):
        logger.warning("quorum config: %s no numérico (%r) → default %r", key, raw[key], default)
        return default
    if not valid(val):
        logger.warning("quorum config: %s fuera de rango (%r) → default %r", key, val, default)
        return default
    return val


def _field_int(raw: dict, key: str, default: int, *, valid: Callable[[int], bool]) -> int:
    if key not in raw:
        return default
    try:
        val = int(raw[key])
    except (TypeError, ValueError):
        logger.warning("quorum config: %s no entero (%r) → default %r", key, raw[key], default)
        return default
    if not valid(val):
        logger.warning("quorum config: %s fuera de rango (%r) → default %r", key, val, default)
        return default
    return val
