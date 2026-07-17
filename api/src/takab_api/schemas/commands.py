"""Modelos del command service (T-1.23 · B9)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

# Espejo de los enums del edge (shared/schemas/command_ack.schema.json v1.4.0).
# `system`/`self_test` (T-1.59) van SIEMPRE juntos: el router valida el cruce.
CHANNELS = frozenset({"siren", "strobe", "gas_valve", "elevator", "door_retainer", "system"})
ACTIONS = frozenset({"activate", "deactivate", "self_test"})


class CommandIntentIn(BaseModel):
    """[T-2.09] Intención firmada con la llave de hardware del operador
    (spec §2.1-B): el backend la valida contra ``device_keys`` y el nonce
    emitido por el servidor; el teléfono jamás firma el comando ejecutable."""

    key_id: UUID
    #: Nonce emitido por POST /sites/{id}/command-nonce (TTL corto).
    nonce: str = Field(min_length=16, max_length=256)
    #: Firma base64 sobre el string canónico ``takab-intent-v1:...``.
    signature: str = Field(min_length=16, max_length=4096)


class CommandIn(BaseModel):
    """Solicitud de comando remoto de actuador."""

    channel: str
    action: str
    event_id: str | None = None
    #: [T-2.09] OBLIGATORIA en la ruta táctica móvil (RBAC §4.3).
    intent: CommandIntentIn | None = None


class CommandNonceOut(BaseModel):
    """[T-2.09] Nonce de intención: se solicita justo antes del deslizamiento."""

    nonce: str
    expires_at: datetime
    ttl_s: float


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
