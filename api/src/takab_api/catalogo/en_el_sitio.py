"""[T-9.61 · T-9.66 · D-46] Lo que un sismo del catálogo habría hecho EN un inmueble.

Módulo puro. Es una ESTIMACIÓN, y quien la pinte tiene que decirlo: la PGA sale de
la ley ilustrativa `geo.pga_law_g` con la distancia HIPOCENTRAL, y la MMI de la
relación de Wald (`shakemap/gmice`). No es lo que midió el gabinete —eso es la PGA
del incidente—, y por eso los dos tipos del historial nunca se mezclan en un campo.

Una sola función para la app (`/sites/{id}/sismos`) y para el historial
(`/sites/{id}/historial-sismico`): dos aritméticas acabarían dando dos MMI
distintas para el mismo sismo en el mismo edificio.
"""

from __future__ import annotations

from dataclasses import dataclass

from takab_api import geo
from takab_api.shakemap import gmice

#: Cómo se estimó. Viaja con cada cifra: una estimación sin su método es una
#: afirmación que nadie puede revisar.
METODO = f"estimada: ley de atenuación ATTEN-LAW v1 (distancia hipocentral) + {gmice.CITA}"


@dataclass(frozen=True)
class EstimacionEnElSitio:
    dist_km: float
    pga_estimada_g: float
    mmi_estimada: float | None
    mmi_romano: str | None


def estima(
    *,
    sitio_lat: float,
    sitio_lon: float,
    lat: float,
    lon: float,
    magnitud: float,
    depth_km: float | None,
) -> EstimacionEnElSitio:
    dist = geo.haversine_km(sitio_lat, sitio_lon, lat, lon)
    pga = geo.pga_law_g(magnitud, geo.hypo_km(dist, depth_km))
    mmi = gmice.mmi_de_pga(pga)
    # El romano y el umbral del historial se sacan de la cifra REDONDEADA, la que se
    # enseña: que la app dijera «2.99 · III» sería una contradicción visible.
    mmi = None if mmi is None else round(mmi, 2)
    return EstimacionEnElSitio(
        dist_km=round(dist, 1),
        pga_estimada_g=pga,
        mmi_estimada=mmi,
        mmi_romano=None if mmi is None else gmice.romano(mmi),
    )
