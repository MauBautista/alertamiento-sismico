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
    """Alta de una NUEVA versión de rule_set para un alcance dado.

    ``base_version``: versión activa sobre la que el cliente construyó ``config``.
    Como el PUT reemplaza el blob ENTERO, sin esto un segundo escritor con una copia
    vieja revierte en silencio claves que su pantalla ni muestra (``relays``,
    ``quorum``…). Si no coincide con la activa ⇒ 409. Omitirla = escritura a ciegas
    (se acepta por compatibilidad con clientes que no la envían).
    """

    scope_type: str
    scope_id: UUID
    config: dict[str, Any]
    base_version: int | None = None


# Claves cuyo valor JAMÁS sale del servidor dentro de ``config``.
SECRET_KEYS: frozenset[str] = frozenset({"secret"})


def redact_config(config: dict[str, Any]) -> dict[str, Any]:
    """Copia de ``config`` sin los secretos de ``notifications.<canal>``.

    El ``secret`` del webhook firma el HMAC hacia el cliente (``notify/providers``).
    Devolverlo en ``GET /rule-sets`` lo metía en el navegador, en la caché de
    react-query y en el DevTools de cualquier superadmin — que además ve TODOS los
    tenants. El worker lo re-resuelve del rule_set al despachar; nadie más lo necesita.
    """
    notifications = config.get("notifications")
    if not isinstance(notifications, dict):
        return config
    clean_channels: dict[str, Any] = {}
    for channel, dest in notifications.items():
        if isinstance(dest, dict):
            clean_channels[channel] = {k: v for k, v in dest.items() if k not in SECRET_KEYS}
        else:
            clean_channels[channel] = dest
    return {**config, "notifications": clean_channels}


def merge_secrets(incoming: dict[str, Any], current: dict[str, Any] | None) -> dict[str, Any]:
    """Reinyecta en ``incoming`` los secretos vigentes que el cliente no pudo ver.

    Un canal que el operador ELIMINA se lleva su secret (intención explícita). Un canal
    que sigue presente sin ``secret`` conserva el guardado: de otro modo, guardar un
    umbral rompería en silencio la firma del webhook del cliente.
    """
    cur_notifications = (current or {}).get("notifications")
    new_notifications = incoming.get("notifications")
    if not isinstance(cur_notifications, dict) or not isinstance(new_notifications, dict):
        return incoming

    merged: dict[str, Any] = {}
    for channel, dest in new_notifications.items():
        old = cur_notifications.get(channel)
        if isinstance(dest, dict) and isinstance(old, dict):
            carried = {k: v for k, v in old.items() if k in SECRET_KEYS and k not in dest}
            merged[channel] = {**dest, **carried}
        else:
            merged[channel] = dest
    return {**incoming, "notifications": merged}


class RuleSetPublishOut(BaseModel):
    """Respuesta 202 de publish: intención de sync al edge (real en T-1.23)."""

    rule_set_id: UUID
    version: int
    status: str = "pending_sync"
