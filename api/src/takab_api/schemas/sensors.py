"""Modelos del catálogo de sensores (lectura T-1.22 · B1, escritura T-1.32)."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Espejo de los CHECK del DDL (db/schema.sql).
SENSOR_KINDS = ("structural", "ground")
SENSOR_MOUNTS = ("concrete_column", "steel", "floor", "buried")
SENSOR_STATUS = ("active", "retired")

SensorKind = Literal["structural", "ground"]
SensorMount = Literal["concrete_column", "steel", "floor", "buried"]
SensorStatus = Literal["active", "retired"]

# Canales reales del RS4D: EHZ (geófono) + ENZ/ENN/ENE (acelerómetro), 100 sps.
RS4D_CHANNELS = ["EHZ", "ENZ", "ENN", "ENE"]


class SensorOut(BaseModel):
    """Sensor de un sitio (RS4D estructural o de terreno)."""

    sensor_id: UUID
    site_id: UUID
    gateway_id: UUID | None = None
    zone_id: UUID | None = None
    kind: str
    model: str
    serial: str | None = None
    channels: list[str]
    sample_rate: int
    mount: str | None = None
    lat: float | None = None
    lon: float | None = None
    calibration_source: str | None = None
    #: Derivado en la DB: ``calibration_source IS NOT NULL``. Sin él, PGA/PGV son
    #: relativos (las sensibilidades del edge son placeholder) y la UI debe decirlo.
    calibrated: bool
    status: str
    row_version: str


class _SensorWrite(BaseModel):
    """Campos comunes de alta y edición. ``lat`` y ``lon`` van juntos o no van."""

    model_config = ConfigDict(extra="forbid")

    site_id: UUID
    gateway_id: UUID | None = None
    zone_id: UUID | None = None
    kind: SensorKind
    model: str = Field(min_length=1, max_length=64)
    serial: str | None = Field(default=None, max_length=64)
    channels: list[str] = Field(default_factory=lambda: list(RS4D_CHANNELS), min_length=1)
    sample_rate: int = Field(default=100, ge=1, le=1000)
    mount: SensorMount | None = None
    lat: float | None = Field(default=None, ge=-90.0, le=90.0)
    lon: float | None = Field(default=None, ge=-180.0, le=180.0)
    #: Procedencia de la respuesta instrumental, p. ej. ``stationxml:AM.R4F74``.
    #: Nombrarla es lo que convierte el PGA en una magnitud física declarable.
    calibration_source: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _coords_together(self) -> _SensorWrite:
        """Media coordenada no es una ubicación: o las dos, o ninguna."""
        if (self.lat is None) != (self.lon is None):
            raise ValueError("lat y lon deben venir juntos o ambos ausentes")
        return self


class SensorCreate(_SensorWrite):
    """Alta de sensor. El tenant lo hereda del sitio padre; ``serial`` es único GLOBAL."""


class SensorUpdate(_SensorWrite):
    """Edición de sensor: reemplaza el cuerpo entero, con bloqueo optimista."""

    status: SensorStatus = "active"
    base_row_version: str | None = None
