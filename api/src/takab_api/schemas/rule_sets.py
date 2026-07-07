"""Modelos de rule_sets: versionado + intención de publicación (T-1.22 · B2)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

# Alcances válidos del CHECK de rule_sets.scope_type (db/schema.sql).
SCOPE_TYPES = frozenset({"tenant", "site", "sensor"})


class RuleSetOut(BaseModel):
    """Fila de ``rule_sets`` visible por RLS (una versión concreta)."""

    rule_set_id: UUID
    tenant_id: UUID
    scope_type: str
    scope_id: UUID
    version: int
    is_active: bool
    config: dict[str, Any]
    created_by: UUID | None
    created_at: datetime


class RuleSetList(BaseModel):
    """rule_sets del tenant (activos primero, luego por versión descendente)."""

    items: list[RuleSetOut]


class RuleSetPutIn(BaseModel):
    """Alta de una NUEVA versión de rule_set para un alcance dado."""

    scope_type: str
    scope_id: UUID
    config: dict[str, Any]


class RuleSetPublishOut(BaseModel):
    """Respuesta 202 de publish: intención de sync al edge (real en T-1.23)."""

    rule_set_id: UUID
    version: int
    status: str = "pending_sync"
