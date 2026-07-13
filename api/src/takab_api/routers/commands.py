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

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.auth.claims import Claims, scope_filter
from takab_api.auth.deps import get_session, require_roles
from takab_api.auth.matrix import ROLE_ACTION_MATRIX, allowed_actions
from takab_api.commands.keys import (
    CommandKeyProvider,
    SecretsManagerKeyProvider,
    build_key_provider,
)
from takab_api.commands.publisher import CommandPublisher, IotDataPublisher
from takab_api.commands.service import issue_signed_command
from takab_api.queries import commands as q
from takab_api.routers._common import http_error
from takab_api.schemas.commands import ACTIONS, CHANNELS, CommandIn, CommandList, CommandOut
from takab_api.settings import Settings

# Fuente única: roles con ALGUNA acción de comando en la matriz (espejo de RBAC
# §2). La guardia fina por-acción vive en el handler ([T-1.59]): siren_test para
# activate/deactivate, self_test para el autodiagnóstico.
COMMAND_ROLES: tuple[str, ...] = tuple(
    sorted(
        r
        for r, actions in ROLE_ACTION_MATRIX.items()
        if actions["siren_test"] or actions.get("self_test")
    )
)

_require_command = require_roles(*COMMAND_ROLES)

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
    # [T-1.59] Cruce canal/acción: self_test ⇔ system, sin excepciones — un
    # self_test sobre un actuador real (o un activate sobre `system`) es 400.
    if (body.action == "self_test") != (body.channel == "system"):
        raise http_error(400, "self_test exige canal system (y solo self_test usa system)")
    # Guardia POR-ACCIÓN (default-deny): siren_test cubre los actuadores reales;
    # self_test es acción propia (superadmin/tenant_admin/building_admin).
    required_action = "self_test" if body.action == "self_test" else "siren_test"
    if not allowed_actions(claims.role).get(required_action):
        raise http_error(403, f"rol sin la acción {required_action}")
    scope = scope_filter(claims)
    if scope is not None and str(site_id) not in scope:
        raise http_error(403, "sitio fuera del alcance del usuario")

    site = (await conn.execute(q.SELECT_SITE, {"site_id": site_id})).first()
    if site is None:
        raise http_error(404, "sitio no encontrado")

    # [T-1.60] La emisión (rate-limit + clave por gateway + firma + insert +
    # publish + audit) vive en commands/service.py — compartida con /drills.
    row = await issue_signed_command(
        conn,
        settings=settings,
        publisher=publisher,
        keys=keys,
        claims=claims,
        site_id=site_id,
        tenant_id=str(site.tenant_id),
        channel=body.channel,
        action=body.action,
        event_id=body.event_id,
    )
    return CommandOut(**row)


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
