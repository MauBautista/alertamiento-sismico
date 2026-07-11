"""Sacudida MEDIDA en un edificio (no la severidad de la alerta).

El mapa del SOC pinta lo que cada inmueble **sintió**, que es un hecho medido por
su propio sensor — no el nivel de alerta del incidente. No son lo mismo: una
alerta SASMEX abre el incidente como ``critical`` aunque el edificio no llegue a
moverse (el WR-1 es un booleano: avisa de que viene un sismo, no mide nada de lo
que pasa AQUÍ). Pintar el edificio de rojo por eso diría algo falso sobre él.

La banda sale de los MISMOS umbrales del ``rule_set`` que arman los actuadores
(``config.edge.thresholds``), así que el color del mapa y la decisión de disparo
hablan el mismo idioma. Sin umbrales configurados se cae al default del edge.

Ojo con ``calibrated``: si el sitio no declara de dónde salió su respuesta
instrumental, su PGA/PGV es RELATIVO y no una unidad física — la UI no puede
presentarlo como una intensidad real (db/schema.sql §sensors).
"""

from __future__ import annotations

from dataclasses import dataclass

#: Banda de sacudida medida. `unknown` = el sitio no ha reportado nada: es
#: ausencia de dato, JAMÁS "no se movió" (regla de oro 7).
FELT_UNKNOWN = "unknown"
FELT_NORMAL = "normal"
FELT_WATCH = "watch"
FELT_TRIP = "trip"


@dataclass(frozen=True)
class Thresholds:
    """Espejo de ``edge/takab_edge/config/settings.py::ThresholdBand``.

    Los defaults son los del edge (banda hospital). Si cambian allí, cambian aquí:
    el edge decide el disparo real y el mapa debe contar la misma historia.
    """

    pga_watch_g: float = 0.040
    pga_trip_g: float = 0.060
    pgv_watch_cms: float = 2.0
    pgv_trip_cms: float = 4.0


DEFAULT_THRESHOLDS = Thresholds()


def thresholds_from_row(
    pga_watch_g: float | None,
    pga_trip_g: float | None,
    pgv_watch_cms: float | None,
    pgv_trip_cms: float | None,
) -> Thresholds:
    """Umbrales del rule_set activo, campo a campo, con default del edge si faltan."""
    d = DEFAULT_THRESHOLDS
    return Thresholds(
        pga_watch_g=pga_watch_g if pga_watch_g is not None else d.pga_watch_g,
        pga_trip_g=pga_trip_g if pga_trip_g is not None else d.pga_trip_g,
        pgv_watch_cms=pgv_watch_cms if pgv_watch_cms is not None else d.pgv_watch_cms,
        pgv_trip_cms=pgv_trip_cms if pgv_trip_cms is not None else d.pgv_trip_cms,
    )


def felt_band(
    pga_g: float | None,
    pgv_cms: float | None,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
) -> str:
    """Banda de la sacudida medida, misma tabla de verdad que el edge (rules.decide).

    Sin NINGUNA medida ⇒ `unknown`. Con una sola, esa manda: PGA y PGV se comparan
    por separado y cualquiera de las dos que exceda basta (el edge hace lo mismo —
    un canal puede saturar en aceleración y no en velocidad).
    """
    if pga_g is None and pgv_cms is None:
        return FELT_UNKNOWN
    pga = pga_g if pga_g is not None else 0.0
    pgv = pgv_cms if pgv_cms is not None else 0.0
    if pga >= thresholds.pga_trip_g or pgv >= thresholds.pgv_trip_cms:
        return FELT_TRIP
    if pga >= thresholds.pga_watch_g or pgv >= thresholds.pgv_watch_cms:
        return FELT_WATCH
    return FELT_NORMAL
