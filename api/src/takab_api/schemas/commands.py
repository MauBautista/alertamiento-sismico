"""Modelos del command service (T-1.23 · B9)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

# Espejo de los enums del edge (shared/schemas/command.schema.json).
CHANNELS = frozenset({"siren", "strobe", "gas_valve", "elevator", "door_retainer"})
ACTIONS = frozenset({"activate", "deactivate"})


class CommandIn(BaseModel):
    """Solicitud de comando remoto de actuador."""

    channel: str
    action: str
    event_id: str | None = None


class CommandOut(BaseModel):
    """Fila de ``commands``: nonce anti-replay + ciclo pending→acked/rejected/expired."""

    command_id: UUID
    tenant_id: UUID
    site_id: UUID
    gateway_id: UUID
    issued_by: UUID
    channel: str
    action: str
    event_id: str | None
    nonce: str
    issued_at: datetime
    expires_at: datetime
    status: str
    ack: dict[str, Any] | None
    error: str | None


class CommandList(BaseModel):
    """Comandos recientes de un sitio (más reciente primero)."""

    items: list[CommandOut]
