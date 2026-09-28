"""Catálogo de referencia de sismos relevantes (T-1.48).

Datos REALES de catálogos oficiales (SSN/USGS), transcritos del catálogo
ratificado en T-1.46 (``db/seeds/reference_earthquakes.sql``). La magnitud aquí
es dato histórico oficial, NO "magnitud preliminar" en vivo (blueprint §14).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class CatalogEarthquakeOut(BaseModel):
    """Sismo del catálogo de referencia (global, solo lectura)."""

    ref_id: UUID
    catalog_key: str
    origin_time: datetime
    magnitude: float
    place: str
    lat: float
    lon: float
    depth_km: float | None
    source: str
    source_ref: str
    notes: str | None
    #: [T-9.61 · D-46] La página del evento en USGS (NULL en las sembradas sin ella).
    usgs_url: str | None = None
    #: Quién escribió la fila: ``seed``, ``catalogo`` (consulta por incidente) o
    #: ``catalog_sync`` (el worker que mantiene el catálogo de México al día).
    origen: str = "seed"


class CatalogEarthquakeList(BaseModel):
    """[T-9.61] Una página, más reciente primero.

    Hasta T-9.61 era la lista completa (13 sismos ratificados). Con el worker
    `catalog-sync` son cientos, así que se pagina: ``siguiente`` es el cursor
    (``origin_time`` ISO del último) para pedir la página siguiente con
    ``antes_de``; ``None`` = no hay más.
    """

    items: list[CatalogEarthquakeOut]
    siguiente: str | None = None


# --- [T-9.61 · T-9.66 · D-46] Sismos del catálogo EN un inmueble -------------------

#: La atribución que exige citar a USGS. Viaja en cada respuesta: la app no la
#: tiene que recordar.
ATRIBUCION_USGS = "Fuente: USGS (dominio público)"


class SismoEnTuInmuebleEstimado(BaseModel):
    """Lo que el sismo habría hecho EN el inmueble. ESTIMADO, nunca medido."""

    dist_km: float = Field(description="Distancia epicentral al inmueble, km.")
    pga_estimada_g: float = Field(
        description="PGA ESTIMADA en el inmueble (ley ATTEN-LAW v1, distancia hipocentral), g."
    )
    mmi_estimada: float | None = Field(
        description="Intensidad Mercalli ESTIMADA en el inmueble (Wald et al. 1999)."
    )
    mmi_romano: str | None = Field(
        description="La MMI ESTIMADA en números romanos. Es una estimación, no una observación."
    )
    metodo: str = Field(description="Cómo se estimó; la app lo muestra junto a la cifra.")


class SismoCercanoOut(BaseModel):
    origin_time: datetime
    magnitude: float
    place: str
    lat: float
    lon: float
    depth_km: float | None
    usgs_url: str | None
    review_status: str | None
    en_tu_inmueble: SismoEnTuInmuebleEstimado


class SismosDelSitioOut(BaseModel):
    """[T-9.61 · D-46] Sismos publicados cerca de un inmueble. Posteriores al evento:
    sin cuenta regresiva ni magnitud preliminar en vivo."""

    items: list[SismoCercanoOut]
    atribucion: str = ATRIBUCION_USGS
    #: El ``ultimo_ok`` de la sincronización; ``None`` = nunca se sincronizó. Con
    #: ``sync_estado`` la app puede decir «sin actualizar desde…» (regla de oro 7).
    actualizado: datetime | None
    sync_estado: Literal["nunca", "ok", "fallido", "apagado"]


class HistorialIncidente(BaseModel):
    """Lo que MIDIÓ el gabinete del inmueble."""

    tipo: Literal["incidente"] = "incidente"
    incident_id: UUID
    opened_at: datetime
    severity: str
    trigger: str
    estado: str
    clasificacion: str | None
    #: La PGA MEDIDA en el sitio (``incidents.max_pga_g``, la del detalle móvil).
    pga_medida_g: float | None


class HistorialSismo(BaseModel):
    """Un sismo del catálogo que en el inmueble se habría sentido (MMI ESTIMADA ≥ III)."""

    tipo: Literal["sismo"] = "sismo"
    origin_time: datetime
    magnitude: float
    place: str
    dist_km: float
    mmi_estimada: float = Field(description="MMI ESTIMADA en el inmueble (Wald et al. 1999).")
    mmi_romano: str = Field(description="La MMI ESTIMADA en números romanos.")
    usgs_url: str | None


class HistorialSismicoOut(BaseModel):
    """[T-9.66 · D-46] Una sola lista, por fecha descendente."""

    eventos: list[Annotated[HistorialIncidente | HistorialSismo, Field(discriminator="tipo")]]
    atribucion: str = ATRIBUCION_USGS
