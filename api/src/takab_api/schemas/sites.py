"""Modelos de respuesta del catálogo de sitios (T-1.22 · B1)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ZoneOut(BaseModel):
    """Zona (planta/área) de un sitio; el polígono no se expone en el catálogo."""

    zone_id: UUID
    name: str
    level_code: str | None = None


class SiteOut(BaseModel):
    """Sitio del tenant. ``geom`` se proyecta a ``lat``/``lon`` (ST_Y/ST_X)."""

    site_id: UUID
    tenant_id: UUID
    code: str
    name: str
    timezone: str
    criticality: str
    lat: float
    lon: float
    address: str | None = None
    building_type: str | None = None
    created_at: datetime


class SiteDetailOut(SiteOut):
    """Detalle de un sitio con sus zonas."""

    zones: list[ZoneOut]
