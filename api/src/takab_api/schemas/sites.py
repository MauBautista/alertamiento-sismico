"""Modelos del catálogo de sitios (lectura T-1.22 · B1, escritura T-1.32).

``row_version`` es el ``xmin`` de la fila (identificador de la transacción que la
escribió). El cliente lo devuelve como ``base_row_version`` al editar: si otro
operador guardó entre medias, el UPDATE no encuentra la fila y la API responde 409
en vez de revertir en silencio la ubicación de una estación.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# Espejo de los CHECK del DDL (db/schema.sql): la UI deriva sus opciones de aquí.
CRITICALITY = ("low", "medium", "high", "critical")
SITE_STATUS = ("active", "retired")

Criticality = Literal["low", "medium", "high", "critical"]
SiteStatus = Literal["active", "retired"]


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
    status: str
    row_version: str
    created_at: datetime


class SiteDetailOut(SiteOut):
    """Detalle de un sitio con sus zonas."""

    zones: list[ZoneOut]


class SiteCreate(BaseModel):
    """Alta de sitio. ``tenant_id`` SOLO lo aceptan los roles internos TAKAB."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=200)
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)
    timezone: str = "America/Mexico_City"
    criticality: Criticality = "medium"
    address: str | None = Field(default=None, max_length=500)
    building_type: str | None = Field(default=None, max_length=100)
    tenant_id: UUID | None = None


class SiteUpdate(BaseModel):
    """Edición de sitio: reemplaza el cuerpo entero (como ``PUT /rule-sets``).

    ``tenant_id`` no aparece a propósito: un sitio no se muda de tenant. Mover su
    ubicación sí es posible — y es exactamente por eso que la edición exige
    ``base_row_version``: la geometría reencuadra la ventana de quórum.
    """

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=200)
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)
    timezone: str = "America/Mexico_City"
    criticality: Criticality = "medium"
    address: str | None = Field(default=None, max_length=500)
    building_type: str | None = Field(default=None, max_length=100)
    status: SiteStatus = "active"
    base_row_version: str | None = None
