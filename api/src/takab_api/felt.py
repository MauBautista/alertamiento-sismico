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

from collections.abc import Iterable, Mapping
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


#: De quién son los umbrales contra los que se clasificó la sacudida.
#:
#: [T-7.35] La distinción es la ficha entera: el papel decía «el umbral de
#: actuación del inmueble» clasificando con la banda de fábrica. Ahora el origen
#: viaja con los números y el documento lo imprime.
ORIGEN_INMUEBLE = "inmueble"
ORIGEN_REFERENCIA = "referencia"


@dataclass(frozen=True)
class UmbralComparacion:
    """Los umbrales usados, de quién son y de qué versión salieron.

    `rule_set_version` solo tiene sentido con `origen == ORIGEN_INMUEBLE`: es la
    versión del `rule_set` que regía **en la apertura del incidente**, no la de
    hoy. Un dictamen es un documento histórico; describirlo con la configuración
    actual es el mismo defecto que la auditoría del 2026-09-13 encontró en la
    calibración («se decide con el inventario de HOY»).
    """

    thresholds: Thresholds
    origen: str
    rule_set_version: int | None = None

    def as_dict(self) -> dict:
        """Forma plana para el `ReportModel`, que se serializa a JSON al firmar
        su huella de contenido. La conversión vive AQUÍ, en un solo sitio."""
        return {
            "pga_watch_g": self.thresholds.pga_watch_g,
            "pga_trip_g": self.thresholds.pga_trip_g,
            "pgv_watch_cms": self.thresholds.pgv_watch_cms,
            "pgv_trip_cms": self.thresholds.pgv_trip_cms,
            "origen": self.origen,
            "rule_set_version": self.rule_set_version,
        }


#: [T-7.37] Clave del `basis` donde se CONGELAN los umbrales al emitir el dictamen.
CLAVE_UMBRAL_CONGELADO = "felt_thresholds"


def umbral_de_fila(fila: Mapping | None) -> UmbralComparacion:
    """De la fila de `rule_sets` en vigor a la comparación, con su procedencia.

    Toma un mapa y no una fila de driver a propósito: la misma resolución la
    necesitan el camino de LECTURA (SQLAlchemy async, al exportar) y el de
    ESCRITURA (psycopg sync, al emitir el dictamen). Con dos conversiones, las
    dos superficies acabarían clasificando el mismo pico contra números
    distintos — que es el defecto `A` de la auditoría del 2026-09-13.
    """
    if not fila:
        # Sin `rule_set` con umbrales anterior al incidente: banda de referencia
        # DECLARADA como tal. Nunca se finge que son los del edificio.
        return UmbralComparacion(DEFAULT_THRESHOLDS, ORIGEN_REFERENCIA)
    return UmbralComparacion(
        thresholds_from_row(
            fila.get("pga_watch_g"),
            fila.get("pga_trip_g"),
            fila.get("pgv_watch_cms"),
            fila.get("pgv_trip_cms"),
        ),
        ORIGEN_INMUEBLE,
        rule_set_version=fila.get("version"),
    )


def umbral_congelado(bases: Iterable[Mapping | None]) -> dict | None:
    """[T-7.37] El primer umbral congelado de la CADENA, de la cabeza hacia atrás.

    No basta con mirar la cabeza: **al firmar, el `basis` de la fila nueva es
    `{}` o `{"notes": …}`** (`routers/dictamens.sign_dictamen`), así que la
    cabeza de una cadena firmada no lo lleva aunque el preliminar sí lo llevara.
    Buscar solo ahí perdería la congelación justo en el documento que más pesa.
    """
    for basis in bases:
        d = (basis or {}).get(CLAVE_UMBRAL_CONGELADO)
        if isinstance(d, dict) and d:
            return d
    return None


def umbral_desde_dict(d: dict | None) -> UmbralComparacion:
    """El camino de vuelta. Sin dato (documentos anteriores a `T-7.35`) se
    devuelve la banda de referencia DECLARADA, nunca umbrales inventados."""
    if not d:
        return UmbralComparacion(DEFAULT_THRESHOLDS, ORIGEN_REFERENCIA)
    return UmbralComparacion(
        thresholds_from_row(
            d.get("pga_watch_g"),
            d.get("pga_trip_g"),
            d.get("pgv_watch_cms"),
            d.get("pgv_trip_cms"),
        ),
        d.get("origen", ORIGEN_REFERENCIA),
        rule_set_version=d.get("rule_set_version"),
    )


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
