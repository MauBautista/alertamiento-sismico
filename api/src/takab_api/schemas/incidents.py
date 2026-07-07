"""Modelos de respuesta de incidentes (T-1.22 · B2)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class IncidentOut(BaseModel):
    """Fila de ``incidents`` visible por RLS (resumen para lista y detalle)."""

    incident_id: UUID
    event_uuid: UUID
    tenant_id: UUID
    site_id: UUID
    event_id: str | None
    opened_at: datetime
    closed_at: datetime | None
    severity: str
    state: str
    trigger: str
    max_pga_g: float | None
    max_pgv_cms: float | None
    summary: dict[str, Any]


class IncidentPage(BaseModel):
    """Página keyset de incidentes: ``items`` + cursor opaco de continuación."""

    items: list[IncidentOut]
    next_cursor: str | None = None


class IncidentActionOut(BaseModel):
    """Fila de ``incident_actions`` (timeline append-only del incidente)."""

    action_id: UUID
    incident_id: UUID
    tenant_id: UUID
    ts: datetime
    kind: str
    actor: str
    payload: dict[str, Any]
