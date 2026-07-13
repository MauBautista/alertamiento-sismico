"""Schemas de lectura del audit trail (T-1.57)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AuditRowOut(BaseModel):
    """Fila de ``audit_log`` tal cual (append-only; jamás se edita).

    ``tenant_id`` NULL = evento de plataforma (solo visible para roles internos,
    RLS ``audit_read``).
    """

    audit_id: int
    ts: datetime
    tenant_id: UUID | None
    actor: str
    verb: str
    object: str
    meta: dict


class AuditPage(BaseModel):
    items: list[AuditRowOut]
    next_cursor: str | None
