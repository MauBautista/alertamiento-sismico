"""Geodesia mínima compartida (T-2.40).

Espejo de ``web/src/features/fleet/geo.ts``: mismas fórmulas y mismos redondeos, para
que la distancia que ve el operador en la consola y la que imprime el dictamen no
difieran en el último kilómetro.

Distancia de gran círculo sobre una esfera de radio medio. No es un geoide: a las
escalas de este sistema (decenas a cientos de km) el error es de metros y no cambia
ninguna decisión.
"""

from __future__ import annotations

import math

EARTH_RADIUS_KM = 6371.0

# 16 rumbos: es lo que un operador lee de un vistazo. "NNE" comunica; "23.4°" no.
_COMPASS = (
    "N",
    "NNE",
    "NE",
    "ENE",
    "E",
    "ESE",
    "SE",
    "SSE",
    "S",
    "SSO",
    "SO",
    "OSO",
    "O",
    "ONO",
    "NO",
    "NNO",
)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia de gran círculo en km."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def bearing16(lat1: float, lon1: float, lat2: float, lon2: float) -> str:
    """Rumbo inicial de 1→2 como uno de los 16 rumbos de la rosa (en español)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)
    y = math.sin(dlambda) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dlambda)
    deg = (math.degrees(math.atan2(y, x)) + 360.0) % 360.0
    return _COMPASS[int((deg / 22.5) + 0.5) % 16]


# --- ATTEN-LAW v1 -----------------------------------------------------------
#
# `log10(PGA_g) = 0.5*M - 2.8 - log10(max(R_hipo_km, 1))`
#
# [T-5.11] La ley VIVE AQUÍ desde esta ficha. Estaba en `api/tools/
# quorum_ssn_validation.py` —una herramienta— y el paquete no podía importarla,
# así que un tercer consumidor habría escrito un tercer espejo. Ahora la
# herramienta la importa de aquí y quedan DOS: éste (fuente) y el de web
# (`features/console/attenuation.ts`, con su ancla en el docstring). El panel del
# gabinete lleva el suyo porque no puede importar nada.
#
# Ley ILUSTRATIVA y determinista. Alimenta comparativas informativas y —desde
# T-5.11— el criterio de IDENTIDAD entre un evento del catálogo y el nuestro.
# Jamás decisiones de actuación, jamás IA (regla de oro 1), y NO es el
# mini-ShakeMap del blueprint §14: cero interpolación espacial.


def hypo_km(epi_km: float, depth_km: float | None) -> float:
    """Distancia hipocentral. Sin profundidad reportada degrada a la epicentral."""
    if depth_km is None:
        return epi_km
    return math.hypot(epi_km, depth_km)


def pga_law_g(magnitude: float, hypo_km_: float) -> float:
    """PGA estimada (g) a esa distancia hipocentral. Piso de 1 km: sin singularidad."""
    return 10 ** (0.5 * magnitude - 2.8) / max(hypo_km_, 1.0)
