"""De detecciones a curva de aforo (T-3.12).

Convierte «cajas por fotograma» en «personas en la zona de reunión por instante», que es la
entrada del motor de métricas.

LA ZONA ES OPCIONAL, Y SU AUSENCIA CAMBIA LO QUE SIGNIFICA EL NÚMERO
────────────────────────────────────────────────────────────────────
Con polígono, el aforo es «gente EN el punto de reunión». Sin él, es «gente EN EL ENCUADRE»
— que incluye a quien pasa por la calle. Los dos son útiles, pero no son lo mismo, y el
reporte tiene que poder decir cuál está mirando. Por eso `Conteo` viaja con `con_zona`: sin
ese testigo, un aforo inflado por peatones se leería como una evacuación multitudinaria.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from takab_cctv.detector import Caja, DetectorBackend, filtrar
from takab_cctv.metricas import Muestra

#: Polígono en coordenadas NORMALIZADAS [0..1]. Normalizadas y no en píxeles porque la misma
#: zona tiene que valer para el substream y para el stream principal, que no comparten
#: resolución — y la cámara puede cambiar de perfil sin que nadie recalibre el polígono.
Poligono = list[tuple[float, float]]


@dataclass(frozen=True)
class Conteo:
    """Un instante de la curva, con lo que hace falta para saber qué está contando."""

    ts: datetime
    n: int
    con_zona: bool
    detector: str


def dentro(punto: tuple[float, float], poligono: Poligono) -> bool:
    """Point-in-polygon por cruce de rayos. Sin dependencias: son doce líneas.

    Traer Shapely (o NumPy) para esto metería una dependencia en el núcleo del paquete
    —que hoy no tiene ninguna— a cambio de nada: el polígono de una zona de reunión tiene
    cuatro o cinco vértices.
    """
    x, y = punto
    adentro = False
    n = len(poligono)
    for i in range(n):
        x1, y1 = poligono[i]
        x2, y2 = poligono[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            adentro = not adentro
    return adentro


def contar(
    cajas: list[Caja],
    *,
    ancho: int,
    alto: int,
    zona: Poligono | None = None,
) -> int:
    """Cuántas de estas detecciones están en la zona. Sin zona, todas."""
    if not zona:
        return len(cajas)
    total = 0
    for caja in cajas:
        px, py = caja.pies
        if dentro((px / ancho, py / alto), zona):
            total += 1
    return total


def serie_de(
    fotogramas: list[tuple[datetime, bytes]],
    detector: DetectorBackend,
    *,
    ancho: int,
    alto: int,
    zona: Poligono | None = None,
) -> list[Conteo]:
    """Recorre los fotogramas y devuelve la curva. **Un fotograma que falla no la corta.**

    Un JPEG truncado —el goteo se toma de una cámara por red— haría perder el incidente
    entero si tumbara la pasada. Se salta ese instante y la curva sigue: una muestra menos
    en una serie de cientos no mueve `t90`, y un análisis abortado sí.
    """
    curva: list[Conteo] = []
    for ts, imagen in fotogramas:
        try:
            cajas = filtrar(detector.detectar(imagen))
        except Exception:  # noqa: BLE001 — un fotograma roto no puede costar el incidente
            continue
        curva.append(
            Conteo(
                ts=ts,
                n=contar(cajas, ancho=ancho, alto=alto, zona=zona),
                con_zona=bool(zona),
                detector=detector.nombre,
            )
        )
    return curva


def a_muestras(curva: list[Conteo]) -> list[Muestra]:
    """Adapta la curva a lo que consume `metricas.calcular`."""
    return [Muestra(ts=c.ts, n=c.n) for c in curva]
