"""Qué cuatro fotogramas van al reporte (T-3.12).

Mauricio las pidió por nombre: **antes de la señal, la gente saliendo, el aforo máximo, y el
reingreso.** Este módulo decide en qué INSTANTE cae cada una; extraer el fotograma es de
quien tiene el vídeo.

LAS ELIGE LA NUBE, HACIA ATRÁS
──────────────────────────────
El gabinete graba y gotea sin decidir nada: no sabe cuál es el momento en que más gente hay
fuera hasta que la evacuación termina. La nube sí, porque para cuando elige ya tiene la
curva entera. Poner esta heurística en el borde habría exigido que adivinara el futuro —o
que guardara todo por si acaso, que es justo lo que la regla de oro 9 prohíbe.

`egress` NO ES «A MITAD DE CAMINO»
──────────────────────────────────
Es el instante de **mayor flujo**: donde la curva sube más rápido, o sea donde más puertas
se están vaciando a la vez. Es la foto que muestra la evacuación ocurriendo. El punto medio
entre la señal y el pico caería a menudo en un momento sin nadie moviéndose.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from takab_cctv.metricas import Evacuacion, Muestra

#: Cuánto antes de la señal se toma la foto del «antes». 30 s es suficiente para ver la zona
#: en su estado normal y sigue dentro del pre-roll de 60 s que graba el gabinete.
ANTES_S = 30.0

#: Los cuatro papeles, en el orden en que el reporte los cuenta.
PAPELES = ("pre", "egress", "peak", "reentry")


@dataclass(frozen=True)
class Eleccion:
    """Un papel del reporte y el instante que le toca. `ts=None` = no hay foto para ése."""

    papel: str
    ts: datetime | None
    razon: str


def _mayor_flujo(serie: list[Muestra], hasta: datetime) -> datetime | None:
    """Instante de mayor subida por segundo, antes del pico."""
    tramos = [
        (
            (b.n - a.n) / max((b.ts - a.ts).total_seconds(), 1e-6),
            b.ts,
        )
        for a, b in zip(serie, serie[1:], strict=False)
        if b.ts <= hasta
    ]
    subidas = [(pendiente, ts) for pendiente, ts in tramos if pendiente > 0]
    return max(subidas)[1] if subidas else None


def elegir(serie: list[Muestra], evac: Evacuacion, *, t0: datetime) -> list[Eleccion]:
    """Los cuatro instantes, cada uno con su razón —o con por qué no hay."""
    orden = sorted(serie, key=lambda m: m.ts)
    inicio = orden[0].ts if orden else None

    antes = t0 - timedelta(seconds=ANTES_S)
    if inicio is not None and antes >= inicio:
        pre = Eleccion("pre", antes, f"{ANTES_S:.0f} s antes de la señal")
    else:
        pre = Eleccion(
            "pre", None, "el clip no cubre los segundos previos: no hay foto del «antes»"
        )

    if evac.peak_at is None:
        vacias = "sin curva de aforo: no se pudo elegir"
        return [
            pre,
            Eleccion("egress", None, vacias),
            Eleccion("peak", None, vacias),
            Eleccion("reentry", None, vacias),
        ]

    flujo = _mayor_flujo(orden, evac.peak_at)
    egress = (
        Eleccion("egress", flujo, "máximo flujo de salida (mayor subida del aforo)")
        if flujo
        else Eleccion("egress", None, "el aforo nunca subió: no hay salida que fotografiar")
    )
    peak = Eleccion("peak", evac.peak_at, f"aforo máximo ({evac.peak_n} personas)")
    reentry = (
        Eleccion("reentry", evac.reentry_start_at, "inicio del reingreso")
        if evac.reentry_start_at
        else Eleccion("reentry", None, "no se observó el inicio del reingreso dentro de la serie")
    )
    return [pre, egress, peak, reentry]
