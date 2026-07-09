"""Command service: comandos remotos de actuador firmados (T-1.23 · B9).

Superficie MÁS sensible del sistema (regla de oro 8 / RBAC §4.3). No negociable:
1. **Firmado**: HMAC byte-idéntico al framing del edge (vectores compartidos).
2. **MFA**: garantizado a nivel de pool Cognito (``mfa=ON`` solo-TOTP, gate #7
   ratificado en T-1.18) — todo ID token de rol web implica TOTP superado.
3. **Rate-limit** por usuario+sitio Y por sitio (ventana deslizante en DB).
4. **Nonce** UNIQUE en emisión (+ nonce un-solo-uso en el edge, T-1.12).
5. **ACK de ejecución obligatorio**: el edge responde ``command_ack`` (la
   ingesta transiciona pending→acked/rejected); sin ack ⇒ expired por TTL.

Roles: acción ``siren_test`` de la matriz RBAC ([DECISION]: proxy Fase 1 de
"puede comandar actuadores"; §2 no define acción más fina — el pánico móvil de
``occupant`` con quórum/geofence es de T-1.31). Fail-closed POR GATEWAY: la
firma usa la clave de ESE gabinete (T-1.38); sin clave resoluble ⇒ 503.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import anyio
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.audit import audit_async
from takab_api.auth.claims import Claims, scope_filter
from takab_api.auth.deps import get_session, require_roles
from takab_api.auth.matrix import ROLE_ACTION_MATRIX
from takab_api.commands.keys import (
    CommandKeyProvider,
    SecretsManagerKeyProvider,
    build_key_provider,
)
from takab_api.commands.publisher import CommandPublisher, IotDataPublisher, PublishError
from takab_api.commands.signing import canonical_payload, sign_command
from takab_api.queries import commands as q
from takab_api.routers._common import http_error
from takab_api.schemas.commands import ACTIONS, CHANNELS, CommandIn, CommandList, CommandOut
from takab_api.settings import Settings

# Fuente única: roles con acción de actuador en la matriz (espejo de RBAC §2).
COMMAND_ROLES: tuple[str, ...] = tuple(
    sorted(r for r, actions in ROLE_ACTION_MATRIX.items() if actions["siren_test"])
)

_require_command = require_roles(*COMMAND_ROLES)

_RATE_WINDOW_S = 60.0

router = APIRouter()


def get_publisher() -> CommandPublisher:
    """Publicador IoT real; los tests lo sustituyen vía dependency override."""
    return IotDataPublisher(Settings())


# Provider de Secrets Manager process-wide: el TTL del cache de claves solo
# sirve si el provider sobrevive al request. El Static (dev/tests) se
# construye por request: es barato y respeta monkeypatch.setenv.
_sm_provider: SecretsManagerKeyProvider | None = None


def get_key_provider() -> CommandKeyProvider:
    """Resuelve claves HMAC por gateway (T-1.38); overrideable en tests."""
    settings = Settings()
    if not settings.command_hmac_keys_json and settings.command_hmac_secret_prefix:
        global _sm_provider
        prefix = settings.command_hmac_secret_prefix.rstrip("/")
        if _sm_provider is None or _sm_provider.prefix != prefix:
            _sm_provider = SecretsManagerKeyProvider(settings)
        return _sm_provider
    return build_key_provider(settings)


@router.post("/sites/{site_id}/commands", response_model=CommandOut, status_code=201)
async def issue_command(
    site_id: UUID,
    body: CommandIn,
    claims: Claims = Depends(_require_command),
    conn: AsyncConnection = Depends(get_session),
    publisher: CommandPublisher = Depends(get_publisher),
    keys: CommandKeyProvider = Depends(get_key_provider),
) -> CommandOut:
    """Emite un comando firmado al gateway del sitio y lo registra ``pending``."""
    settings = Settings()
    if body.channel not in CHANNELS or body.action not in ACTIONS:
        raise http_error(400, "channel/action inválidos")
    scope = scope_filter(claims)
    if scope is not None and str(site_id) not in scope:
        raise http_error(403, "sitio fuera del alcance del usuario")

    site = (await conn.execute(q.SELECT_SITE, {"site_id": site_id})).first()
    if site is None:
        raise http_error(404, "sitio no encontrado")

    now = datetime.now(tz=UTC)
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

    # Fail-closed POR GATEWAY (T-1.38): la firma usa la clave de ESTE gabinete;
    # sin clave resoluble no se firma nada — jamás se degrada a una compartida.
    # key_for puede tocar Secrets Manager (bloqueante) ⇒ thread pool.
    key = await anyio.to_thread.run_sync(keys.key_for, gateway.iot_thing)
    if key is None:
        raise http_error(503, f"sin clave HMAC para el gateway {gateway.iot_thing}")

    nonce = uuid4().hex
    ts_iso = now.isoformat()
    payload = {"channel": body.channel, "action": body.action, "event_id": body.event_id}
    signature = sign_command(key, canonical_payload(payload), nonce, ts_iso)
    stmt, params = q.insert_command(
        tenant_id=str(site.tenant_id),
        site_id=str(site_id),
        gateway_id=str(gateway.gateway_id),
        issued_by=claims.sub,
        channel=body.channel,
        action=body.action,
        event_id=body.event_id,
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
        # Se revierte la fila (rollback del get_session): no queda un pending
        # fantasma de un comando que jamás salió.
        raise http_error(502, "no se pudo publicar el comando al gateway") from exc

    await audit_async(
        conn,
        tenant_id=site.tenant_id,
        actor=f"user:{claims.sub}",
        verb="command_issued",
        obj=f"command:{row['command_id']}",
    )
    return CommandOut(**dict(row))


@router.get(
    "/sites/{site_id}/commands",
    response_model=CommandList,
    dependencies=[Depends(_require_command)],
)
async def list_commands(
    site_id: UUID,
    conn: AsyncConnection = Depends(get_session),
) -> CommandList:
    """Comandos recientes del sitio (RLS decide visibilidad; 404 si no visible)."""
    site = (await conn.execute(q.SELECT_SITE, {"site_id": site_id})).first()
    if site is None:
        raise http_error(404, "sitio no encontrado")
    now = datetime.now(tz=UTC)
    await conn.execute(q.EXPIRE_SITE, {"site_id": site_id, "now": now})
    rows = (
        (await conn.execute(q.LIST_COMMANDS, {"site_id": site_id, "limit": 100})).mappings().all()
    )
    return CommandList(items=[CommandOut(**dict(r)) for r in rows])
