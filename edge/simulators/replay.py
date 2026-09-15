"""[T-7.14] El plan de arribos, ESPEJO del de la nube.

Copia deliberada de `api/src/takab_api/replay/plan.py`. No se importa porque el
simulador corre en un portátil o en el Pi 4, con el entorno de `edge/` y sin el
paquete de la nube instalado — el mismo motivo por el que el panel del gabinete
lleva su propio ATTEN-LAW.

**Los dos no pueden divergir en silencio**: `edge/tests/test_replay_plan.py` carga
el módulo de la nube por ruta y compara las dos salidas sobre una rejilla. Si
alguien toca una fórmula aquí y no allí (o al revés), sale rojo. Esa prueba es la
razón por la que este fichero puede existir sin ser una bomba de relojería.

Los tiempos se cuentan desde el ORIGEN del sismo, no desde el pulso del WR-1:
quien reproduce ancla el origen a `t0` y suma.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

EARTH_RADIUS_KM = 6371.0

#: Razón v_p/v_s de un sólido de Poisson. `v_p` no es un número aparte.
RAZON_VP_VS = math.sqrt(3.0)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia de gran círculo en km. Espejo de `takab_api.geo`."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def hypo_km(epi_km: float, depth_km: float | None) -> float:
    """Distancia hipocentral. Sin profundidad reportada degrada a la epicentral."""
    if depth_km is None:
        return epi_km
    return math.hypot(epi_km, depth_km)


def pga_law_g(magnitude: float, hypo_km_: float) -> float:
    """ATTEN-LAW v1: `log10(PGA_g) = 0.5*M - 2.8 - log10(max(R_hipo_km, 1))`."""
    return 10 ** (0.5 * magnitude - 2.8) / max(hypo_km_, 1.0)


@dataclass(frozen=True)
class Sismo:
    catalog_key: str
    magnitude: float
    lat: float
    lon: float
    depth_km: float | None
    v_s_km_s: float
    v_p_km_s: float


@dataclass(frozen=True)
class Estacion:
    site_id: str
    site_code: str
    lat: float
    lon: float


@dataclass(frozen=True)
class Arribo:
    site_id: str
    site_code: str
    epi_km: float
    hypo_km: float
    t_p_s: float
    t_s_s: float
    pga_g: float


def velocidades(v_s_km_s: float) -> tuple[float, float]:
    """``(v_p, v_s)`` a partir de la de corte."""
    if v_s_km_s <= 0:
        raise ValueError(f"v_s tiene que ser positiva: {v_s_km_s!r}")
    return v_s_km_s * RAZON_VP_VS, v_s_km_s


def arribo(sismo: Sismo, estacion: Estacion) -> Arribo:
    epi = haversine_km(sismo.lat, sismo.lon, estacion.lat, estacion.lon)
    hipo = hypo_km(epi, sismo.depth_km)
    return Arribo(
        site_id=estacion.site_id,
        site_code=estacion.site_code,
        epi_km=epi,
        hypo_km=hipo,
        t_p_s=hipo / sismo.v_p_km_s,
        t_s_s=hipo / sismo.v_s_km_s,
        pga_g=pga_law_g(sismo.magnitude, hipo),
    )


def plan_de_arribos(sismo: Sismo, estaciones: list[Estacion]) -> list[Arribo]:
    """El plan entero, ordenado por cuándo llega. Es el orden de la coreografía."""
    return sorted((arribo(sismo, e) for e in estaciones), key=lambda a: (a.t_p_s, a.site_code))
