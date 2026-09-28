"""Modelos de respuesta de incidentes (T-1.22 · B2)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


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


class LonLat(BaseModel):
    """Punto geográfico plano (lon/lat WGS84)."""

    lon: float
    lat: float


class EpicenterRelocateIn(BaseModel):
    """Cuerpo de POST /incidents/{id}/epicenter (T-1.48). Bounds duros aquí;
    la función SECURITY DEFINER los re-valida (defensa en profundidad)."""

    lon: float = Field(ge=-180.0, le=180.0)
    lat: float = Field(ge=-90.0, le=90.0)
    note: str | None = Field(default=None, max_length=500)


class EpicenterRelocateOut(BaseModel):
    """Resultado de la reubicación: evento afectado/creado + punto previo."""

    incident_id: UUID
    event_id: str
    created_event: bool
    epicenter: LonLat
    previous: LonLat | None


class DictamenRequestIn(BaseModel):
    """Cuerpo de POST /incidents/{id}/dictamen-request (T-1.48)."""

    note: str | None = Field(default=None, max_length=500)


class IncidentCloseIn(BaseModel):
    """Cuerpo de POST /incidents/{id}/close [T-9.40 · D-43].

    ``motivo`` sólo es OBLIGATORIO (≥ 20 caracteres tras ``strip()``) cuando la
    clasificación vigente es ``real``/``indeterminado`` y la cabeza de la cadena no
    está firmada: es la razón por escrito de cerrar SIN dictamen. El tope evita que
    la auditoría se convierta en un vertedero.
    """

    motivo: str | None = Field(default=None, max_length=1000)


class IncidentCloseOut(BaseModel):
    """Resultado del cierre explícito [T-9.40 · D-43].

    ``sin_dictamen`` = se cerró un ``real``/``indeterminado`` con la cabeza SIN
    firmar, por motivo escrito (deja además el audit ``cierre_sin_dictamen``).
    """

    incident_id: UUID
    state: str = "closed"
    closed_at: datetime
    reason: str = "explicit"
    classification: str
    signature_kind: str | None
    sin_dictamen: bool
