"""Modelos de dictámenes: cadena de versiones + firma del inspector (T-1.22 · B2)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

# Estados válidos del CHECK de dictamens.status (db/schema.sql).
DICTAMEN_STATUS = frozenset(
    {"normal_operation", "inhabit_monitor", "restricted", "no_inhabit_inspect"}
)


class DictamenOut(BaseModel):
    """Fila de ``dictamens``: ``signed_by`` NULL = preliminar; cadena vía supersedes."""

    dictamen_id: UUID
    tenant_id: UUID
    incident_id: UUID
    status: str
    basis: dict[str, Any]
    signed_by: UUID | None
    supersedes_dictamen_id: UUID | None
    created_at: datetime


class DictamenList(BaseModel):
    """Cadena de dictámenes de un incidente (más reciente primero)."""

    items: list[DictamenOut]


class DictamenSignIn(BaseModel):
    """Firma manual del inspector: estado del dictamen + notas mínimas (basis)."""

    status: str
    notes: str | None = None
