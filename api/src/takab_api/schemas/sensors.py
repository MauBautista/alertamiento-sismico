"""Modelos de respuesta del catálogo de sensores (T-1.22 · B1)."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


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
    status: str
