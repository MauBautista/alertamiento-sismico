"""Modelos de respuesta del catálogo de tenants (T-1.22 · B1)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class TenantOut(BaseModel):
    """Fila de tenant. RLS decide qué filas ve cada rol (ver router/tenants)."""

    tenant_id: UUID
    code: str
    name: str
    isolation_mode: str
    vertical: str | None = None
    visibility: str
    status: str
    plan_code: str
    created_at: datetime
