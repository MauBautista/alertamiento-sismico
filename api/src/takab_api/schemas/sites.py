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

from pydantic import BaseModel, ConfigDict, Field, field_validator

from takab_api.sites.tipologia import TIPOS

# Espejo de los CHECK del DDL (db/schema.sql): la UI deriva sus opciones de aquí.
CRITICALITY = ("low", "medium", "high", "critical")
SITE_STATUS = ("active", "retired")

Criticality = Literal["low", "medium", "high", "critical"]
SiteStatus = Literal["active", "retired"]

# [T-5.16 · D-28] La tipología NO se enumera aquí: sale de
# `shared/schemas/tipologia_umbral.json`, que es el mismo fichero del que salen el
# CHECK de la base y el desplegable de la consola. Un `Literal` habría sido una
# cuarta copia a mano — y el espejo de la matriz RBAC (`T-5.28`) ya enseñó cómo
# acaba eso. Se valida con un validador porque un `Literal` necesita las cadenas
# en tiempo de definición y estas se leen de un fichero.
BUILDING_TYPES: tuple[str, ...] = TIPOS


def _valida_tipologia(v: str | None) -> str | None:
    """Rechaza lo que no esté en el catálogo. `None` sigue valiendo: un sitio
    puede no estar clasificado todavía, y meterlo en `otro` afirmaría que
    alguien lo miró."""
    if v is not None and v not in BUILDING_TYPES:
        raise ValueError(f"building_type fuera del catálogo (D-28): {sorted(BUILDING_TYPES)}")
    return v


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
    building_type: str | None = None
    tenant_id: UUID | None = None

    _tipologia = field_validator("building_type")(_valida_tipologia)


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
    building_type: str | None = None
    status: SiteStatus = "active"
    base_row_version: str | None = None

    _tipologia = field_validator("building_type")(_valida_tipologia)
