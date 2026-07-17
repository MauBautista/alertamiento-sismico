"""Modelos del catálogo de tenants: lectura (T-1.22 · B1) y alta (T-1.72)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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


class TenantCreate(BaseModel):
    """Alta de un cliente (T-1.72). Solo ``takab_superadmin`` (acción ``manage_tenants``).

    ``visibility`` y ``status`` NO se aceptan aquí: nacen con los defaults del schema
    (``private``/``active``). Compartir con gobierno (``gov_shared``) es una decisión
    aparte; la visibilidad configurable entre clientes vive en T-1.73.
    """

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    vertical: str | None = Field(default=None, max_length=64)
    plan_code: str = Field(default="mvp", min_length=1, max_length=32)
    isolation_mode: Literal["logical", "dedicated"] = "logical"
