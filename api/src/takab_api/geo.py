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
