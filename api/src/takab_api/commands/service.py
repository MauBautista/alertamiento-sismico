"""Emisión de comandos firmados — el corazón de la regla de oro 8, UNA sola vez.

[T-1.60] Extraído de ``routers/commands.py`` para que el router de drills
emita `drill_start`/`drill_stop` SIN duplicar la superficie sensible:
rate-limit por usuario+sitio y por sitio, clave HMAC POR GATEWAY (fail-closed),
nonce UNIQUE, TTL, publish al topic del thing y auditoría. Cualquier endpoint
nuevo que comande un gabinete pasa por aquí.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import anyio
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.audit import audit_async
from takab_api.auth.claims import Claims
from takab_api.commands.keys import CommandKeyProvider
from takab_api.commands.publisher import CommandPublisher, PublishError
from takab_api.commands.signing import canonical_payload, sign_command
from takab_api.queries import commands as q
from takab_api.routers._common import http_error
from takab_api.settings import Settings

_RATE_WINDOW_S = 60.0


async def issue_signed_command(
    conn: AsyncConnection,
    *,
    settings: Settings,
    publisher: CommandPublisher,
    keys: CommandKeyProvider,
    claims: Claims,
    site_id: UUID,
    tenant_id: str,
    channel: str,
    action: str,
    event_id: str | None,
    payload_extra: dict[str, Any] | None = None,
    now: datetime | None = None,
    nonce_override: str | None = None,
    audit_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Firma, registra ``pending``, publica y audita UN comando. Devuelve la fila.

    El llamador ya validó visibilidad del sitio (RLS/404), alcance y matriz de
    acciones. ``payload_extra`` viaja DENTRO del payload canónico firmado (p.ej.
    ``duration_s`` del drill): el edge re-canonicaliza el dict recibido tal
    cual, así que la firma cubre cada clave extra.
    """
    now = now or datetime.now(tz=UTC)
    await conn.execute(q.EXPIRE_SITE, {"site_id": site_id, "now": now})

    since = now - timedelta(seconds=_RATE_WINDOW_S)
    per_user = (
        await conn.execute(
            q.COUNT_USER_SITE, {"user_id": claims.sub, "site_id": site_id, "since": since}
        )
    ).scalar_one()
    if per_user >= settings.command_rate_user_site_per_min:
        raise http_error(429, "rate-limit de comandos por usuario+sitio excedido")
    per_site = (await conn.execute(q.COUNT_SITE, {"site_id": site_id, "since": since})).scalar_one()
    if per_site >= settings.command_rate_site_per_min:
        raise http_error(429, "rate-limit de comandos del sitio excedido")

    gateway = (await conn.execute(q.SELECT_GATEWAY, {"site_id": site_id})).first()
    if gateway is None:
        raise http_error(409, "el sitio no tiene gateway comandable (iot_thing)")

    # Fail-closed POR GATEWAY (T-1.38): sin clave resoluble no se firma nada.
    # key_for puede tocar Secrets Manager (bloqueante) ⇒ thread pool.
    key = await anyio.to_thread.run_sync(keys.key_for, gateway.iot_thing)
    if key is None:
        raise http_error(503, f"sin clave HMAC para el gateway {gateway.iot_thing}")

    # [T-2.09] La intención firmada aporta SU nonce (emitido por el servidor):
    # commands.nonce UNIQUE convierte cualquier replay en violación de insert.
    nonce = nonce_override or uuid4().hex
    ts_iso = now.isoformat()
    payload: dict[str, Any] = {"channel": channel, "action": action, "event_id": event_id}
    if payload_extra:
        payload.update(payload_extra)
    signature = sign_command(key, canonical_payload(payload), nonce, ts_iso)
    stmt, params = q.insert_command(
        tenant_id=tenant_id,
        site_id=str(site_id),
        gateway_id=str(gateway.gateway_id),
        issued_by=claims.sub,
        channel=channel,
        action=action,
        event_id=event_id,
        nonce=nonce,
        issued_at=now,
        expires_at=now + timedelta(seconds=settings.command_ttl_s),
    )
    row = (await conn.execute(stmt, params)).mappings().one()

    envelope = {
        "kind": "command",
        "command_id": str(row["command_id"]),
        "nonce": nonce,
        "ts": ts_iso,
        "payload": payload,
        "sig": signature,
    }
    try:
        publisher.publish(f"takab/cmd/{gateway.iot_thing}", json.dumps(envelope).encode())
    except PublishError as exc:
        # Se revierte la fila (rollback de la sesión): no queda un pending
        # fantasma de un comando que jamás salió.
        raise http_error(502, "no se pudo publicar el comando al gateway") from exc

    await audit_async(
        conn,
        tenant_id=tenant_id,
        actor=f"user:{claims.sub}",
        verb="command_issued",
        obj=f"command:{row['command_id']}",
        meta=audit_meta,
    )
    return dict(row)
