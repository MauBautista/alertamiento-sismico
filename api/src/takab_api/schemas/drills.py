"""Modelos del simulacro institucional (T-1.60 · cierra M-1)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class DrillCreateIn(BaseModel):
    """Inicio de simulacro. Sin ``site_ids`` = todos los sitios del tenant con
    gateway comandable. La duración acota el banner (30 s..1 h, CHECK de DB).

    [T-2.03·D4c] Con ``scheduled_at`` (futuro) la fila es AGENDA informativa
    ("próximo simulacro" de la app): sin comandos y jamás ``active`` — ejecutar
    a esa hora sigue siendo un acto del operador.
    """

    site_ids: list[UUID] | None = None
    duration_s: int = Field(default=300, ge=30, le=3600)
    note: str | None = Field(default=None, max_length=500)
    scheduled_at: datetime | None = None


class DrillSiteOut(BaseModel):
    """Participación de UN sitio: el acuse se DERIVA del comando firmado."""

    site_id: UUID
    site_name: str | None
    command_id: UUID | None
    command_status: str | None
    ack: dict[str, Any] | None


class DrillOut(BaseModel):
    drill_id: UUID
    tenant_id: UUID
    initiated_by: UUID
    note: str | None
    duration_s: int
    started_at: datetime
    stopped_at: datetime | None
    stop_reason: str | None
    #: [T-2.03·D4c] No-NULL = fila de AGENDA (anuncio); jamás deriva active.
    scheduled_at: datetime | None
    #: DERIVADO por el servidor: sin fin manual y dentro de la ventana.
    active: bool
    sites: list[DrillSiteOut]


class DrillList(BaseModel):
    items: list[DrillOut]


class ActiveDrillOut(BaseModel):
    """El drill vivo del tenant (o null): la consola pinta el banner NO-real."""

    drill: DrillOut | None
