"""Modelos de respuesta de eventos sísmicos y votos de quórum (T-1.22 · B2)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class SeismicEventOut(BaseModel):
    """Fila de ``seismic_events`` (dato de red; epicentro aplanado a lon/lat)."""

    event_id: str
    source: str
    magnitude: float | None
    epicenter_lon: float | None
    epicenter_lat: float | None
    depth_km: float | None
    detected_at: datetime
    meta: dict[str, Any]


class EventPage(BaseModel):
    """Página keyset de eventos sísmicos."""

    items: list[SeismicEventOut]
    next_cursor: str | None = None


class QuorumVoteOut(BaseModel):
    """Voto de ``quorum_votes``: arribo por sensor/estación con ``delta_s``."""

    event_id: str
    sensor_id: UUID
    detected_at: datetime
    pga_g: float
    delta_s: float | None
    counted: bool


class EventDetailOut(SeismicEventOut):
    """Detalle de evento: campos del evento + sus votos de quórum."""

    quorum_votes: list[QuorumVoteOut]
