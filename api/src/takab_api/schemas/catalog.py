"""Catálogo de referencia de sismos relevantes (T-1.48).

Datos REALES de catálogos oficiales (SSN/USGS), transcritos del catálogo
ratificado en T-1.46 (``db/seeds/reference_earthquakes.sql``). La magnitud aquí
es dato histórico oficial, NO "magnitud preliminar" en vivo (blueprint §14).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


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


class CatalogEarthquakeList(BaseModel):
    """Lista completa (13 sismos ratificados; sin paginación)."""

    items: list[CatalogEarthquakeOut]
