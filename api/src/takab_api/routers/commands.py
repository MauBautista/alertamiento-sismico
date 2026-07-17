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

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.audit import audit_async
from takab_api.auth.claims import Claims, scope_filter
from takab_api.auth.deps import get_session, require_roles
from takab_api.auth.matrix import ROLE_ACTION_MATRIX, allowed_actions, roles_with_action
from takab_api.commands.intent import (
    canonical_intent,
    intent_sha256,
    intent_signature_valid,
    mint_nonce,
    nonce_error,
)
from takab_api.commands.keys import (
    CommandKeyProvider,
    SecretsManagerKeyProvider,
    build_key_provider,
)
from takab_api.commands.publisher import CommandPublisher, IotDataPublisher
from takab_api.commands.service import issue_signed_command
from takab_api.queries import commands as q
from takab_api.queries import mobile as mobile_q
from takab_api.routers._common import http_error, integrity_error
from takab_api.schemas.commands import (
    ACTIONS,
    CHANNELS,
    CommandIn,
    CommandList,
    CommandNonceOut,
    CommandOut,
    PanicVoteIn,
    PanicVoteOut,
)
from takab_api.settings import Settings

# Fuente única: roles con ALGUNA acción de comando en la matriz (espejo de RBAC
# §2/§3). La guardia fina por-acción vive en el handler: siren_test para la
# consola, self_test para el autodiagnóstico y — desde T-2.09 — la ruta
# TÁCTICA móvil (manual_activate/siren_silence) con INTENCIÓN FIRMADA.
COMMAND_ROLES: tuple[str, ...] = tuple(
    sorted(
        r
        for r, actions in ROLE_ACTION_MATRIX.items()
        if actions["siren_test"]
        or actions.get("self_test")
        or actions.get("manual_activate")
        or actions.get("siren_silence")
    )
)

_require_command = require_roles(*COMMAND_ROLES)

# [T-2.09] Acción de matriz exigida por comando en la ruta táctica (RBAC §4):
# activar = deslizar-para-activar individual; desactivar = retirada de la
# demanda manual (silenciar). El occupant no está aquí: su camino es el
# quórum-de-2 (panic_vote, T-2.13).
_INTENT_ACTION_BY_COMMAND = {"activate": "manual_activate", "deactivate": "siren_silence"}

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

    acts = allowed_actions(claims.role)
    # [T-2.09] Ruta TÁCTICA (RBAC §4.3): quien no porta ``siren_test`` — o cuyo
    # token es de superficie MÓVIL (el teléfono comanda solo con intención) —
    # entra por las acciones de campo y DEBE traer la intención firmada.
    tactical = body.action != "self_test" and (
        not acts.get("siren_test") or claims.surface == "mobile"
    )
    if tactical:
        required_action = _INTENT_ACTION_BY_COMMAND[body.action]
        if not acts.get(required_action):
            raise http_error(403, f"rol sin la acción {required_action}")
        if body.channel != "siren":
            raise http_error(403, "el control táctico móvil solo opera la sirena (spec 2.2)")
    else:
        # Guardia POR-ACCIÓN (default-deny): siren_test cubre los actuadores
        # reales; self_test es acción propia (superadmin/tenant_admin/b_admin).
        required_action = "self_test" if body.action == "self_test" else "siren_test"
        if not acts.get(required_action):
            raise http_error(403, f"rol sin la acción {required_action}")
    scope = scope_filter(claims)
    if scope is not None and str(site_id) not in scope:
        raise http_error(403, "sitio fuera del alcance del usuario")

    site = (await conn.execute(q.SELECT_SITE, {"site_id": site_id})).first()
    if site is None:
        raise http_error(404, "sitio no encontrado")

    audit_meta = None
    nonce_override = None
    if tactical:
        intent = body.intent
        if intent is None:
            raise http_error(403, "se requiere intención firmada (RBAC §4.3)")
        if not settings.command_intent_secret:
            # FAIL-CLOSED: sin secreto configurado no hay ruta táctica.
            raise http_error(503, "intención firmada no configurada en el servidor")
        reason = nonce_error(
            settings.command_intent_secret,
            intent.nonce,
            sub=claims.sub,
            site_id=str(site_id),
            now=datetime.now(tz=UTC),
        )
        if reason is not None:
            raise http_error(403, f"nonce de intención rechazado: {reason}")
        if (await conn.execute(q.NONCE_EXISTS, {"nonce": intent.nonce})).first() is not None:
            raise http_error(409, "nonce de intención ya usado (replay rechazado)")
        key_row = (
            await conn.execute(q.DEVICE_KEY, {"key_id": str(intent.key_id), "sub": claims.sub})
        ).first()
        if key_row is None:
            raise http_error(403, "llave de dispositivo no registrada o revocada")
        message = canonical_intent(
            key_id=str(intent.key_id),
            site_id=str(site_id),
            channel=body.channel,
            action=body.action,
            nonce=intent.nonce,
        )
        if not intent_signature_valid(key_row.public_key, intent.signature, message):
            raise http_error(403, "firma de intención inválida")
        nonce_override = intent.nonce
        audit_meta = {
            "intent_key_id": str(intent.key_id),
            "intent_sha256": intent_sha256(intent.signature),
        }

    # [T-1.60] La emisión (rate-limit + clave por gateway + firma + insert +
    # publish + audit) vive en commands/service.py — compartida con /drills.
    try:
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
            nonce_override=nonce_override,
            audit_meta=audit_meta,
        )
    except IntegrityError as exc:
        # Backstop del UNIQUE de commands.nonce ante replays concurrentes.
        raise integrity_error(exc) from exc
    return CommandOut(**row)


@router.post("/sites/{site_id}/command-nonce", response_model=CommandNonceOut, status_code=201)
async def issue_command_nonce(
    site_id: UUID,
    claims: Claims = Depends(_require_command),
    conn: AsyncConnection = Depends(get_session),
) -> CommandNonceOut:
    """[T-2.09] Nonce de intención (TTL corto, atado a operador+sitio): el
    teléfono lo solicita JUSTO antes del deslizamiento (spec 2.2) y lo firma
    dentro de la intención. Solo roles con acciones tácticas de campo."""
    settings = Settings()
    acts = allowed_actions(claims.role)
    if not (acts.get("manual_activate") or acts.get("siren_silence")):
        raise http_error(403, "rol sin acciones de control táctico")
    scope = scope_filter(claims)
    if scope is not None and str(site_id) not in scope:
        raise http_error(403, "sitio fuera del alcance del usuario")
    if not settings.command_intent_secret:
        raise http_error(503, "intención firmada no configurada en el servidor")
    if (await conn.execute(q.SELECT_SITE, {"site_id": site_id})).first() is None:
        raise http_error(404, "sitio no encontrado")
    nonce, expires_at = mint_nonce(
        settings.command_intent_secret,
        sub=claims.sub,
        site_id=str(site_id),
        ttl_s=settings.command_intent_ttl_s,
        now=datetime.now(tz=UTC),
    )
    return CommandNonceOut(nonce=nonce, expires_at=expires_at, ttl_s=settings.command_intent_ttl_s)


@router.get("/sites/{site_id}/commands", response_model=CommandList)
async def list_commands(
    site_id: UUID,
    claims: Claims = Depends(_require_command),
    conn: AsyncConnection = Depends(get_session),
) -> CommandList:
    """Comandos recientes del sitio (RLS decide visibilidad; 404 si no visible).

    [T-2.09] Con ``site_scope`` acotado (táctico móvil que espera su ack) el
    sitio fuera de alcance es 403 — mismo default-deny que la emisión.
    """
    scope = scope_filter(claims)
    if scope is not None and str(site_id) not in scope:
        raise http_error(403, "sitio fuera del alcance del usuario")
    site = (await conn.execute(q.SELECT_SITE, {"site_id": site_id})).first()
    if site is None:
        raise http_error(404, "sitio no encontrado")
    now = datetime.now(tz=UTC)
    await conn.execute(q.EXPIRE_SITE, {"site_id": site_id, "now": now})
    rows = (
        (await conn.execute(q.LIST_COMMANDS, {"site_id": site_id, "limit": 100})).mappings().all()
    )
    return CommandList(items=[CommandOut(**dict(r)) for r in rows])


_PANIC_ROLES: tuple[str, ...] = roles_with_action("panic_vote")
_require_panic = require_roles(*_PANIC_ROLES)


@router.post("/sites/{site_id}/manual-activation-votes", response_model=PanicVoteOut)
async def panic_vote(
    site_id: UUID,
    body: PanicVoteIn,
    claims: Claims = Depends(_require_panic),
    conn: AsyncConnection = Depends(get_session),
    publisher: CommandPublisher = Depends(get_publisher),
    keys: CommandKeyProvider = Depends(get_key_provider),
) -> PanicVoteOut:
    """[T-2.13 · 1.9] Voto de pánico del occupant (emergencia NO sísmica del
    inmueble). Quórum = 2 votos de usuarios DISTINTOS en la ventana ⇒ sirena por
    el pipeline HMAC existente + votos ``consumed``. Un voto JAMÁS activa; dos
    del MISMO usuario JAMÁS activan. Geofence best-effort (GPS fuera de radio se
    descarta; sin GPS cuenta). Rate-limit por usuario; TODO voto audita."""
    settings = Settings()
    # R2: el occupant debe estar ENROLADO en el sitio (o 404, sin filtración).
    # El sitio ya trae su tenant ⇒ el audit del voto lo lleva REAL (visible para
    # el admin del tenant), no NULL.
    site = await mobile_q.assert_site_access(conn, claims, site_id)
    tenant_id = str(site.tenant_id)
    now = datetime.now(tz=UTC)
    window_start = now - timedelta(seconds=settings.panic_quorum_window_s)

    # Rate-limit por usuario (no martillear el quórum).
    recent = (
        await conn.execute(
            mobile_q.PANIC_USER_RATE,
            {"site": str(site_id), "sub": claims.sub, "since": now - timedelta(seconds=60)},
        )
    ).scalar_one()
    if recent >= settings.panic_vote_rate_per_min:
        raise http_error(429, "demasiados votos; espere un momento")

    lon, lat = body.location if body.location is not None else (None, None)
    # Geofence best-effort: True dentro, False fuera, None sin GPS (cuenta).
    in_radius = (
        await conn.execute(
            mobile_q.PANIC_IN_RADIUS,
            {
                "site": str(site_id),
                "lon": lon,
                "lat": lat,
                "radius": settings.panic_geofence_radius_m,
            },
        )
    ).scalar_one()

    await audit_async(
        conn,
        tenant_id=tenant_id,
        actor=f"user:{claims.sub}",
        verb="panic_vote",
        obj=f"site:{site_id}",
        meta={"with_gps": body.location is not None, "in_radius": in_radius},
    )

    if in_radius is False:
        # Voto CON GPS fuera del radio: se descarta (RBAC §4.3 geofence).
        return PanicVoteOut(
            status="discarded",
            distinct_voters=0,
            remaining=2,
            window_s=settings.panic_quorum_window_s,
        )

    await conn.execute(
        mobile_q.INSERT_PANIC_VOTE,
        {"tenant": tenant_id, "site": str(site_id), "sub": claims.sub},
    )

    voters = (
        await conn.execute(
            mobile_q.PANIC_DISTINCT_VOTERS, {"site": str(site_id), "since": window_start}
        )
    ).scalar_one()
    distinct = len(voters) if voters is not None else 0

    if distinct < 2:
        return PanicVoteOut(
            status="counted",
            distinct_voters=distinct,
            remaining=2 - distinct,
            window_s=settings.panic_quorum_window_s,
        )

    # Quórum alcanzado: dispara la sirena por el pipeline firmado y consume los
    # votos (un solo disparo). La nube firma el comando; el teléfono jamás.
    await issue_signed_command(
        conn,
        settings=settings,
        publisher=publisher,
        keys=keys,
        claims=claims,
        site_id=site_id,
        tenant_id=tenant_id,
        channel="siren",
        action="activate",
        event_id=None,
        payload_extra={"source": "panic_quorum"},
        audit_meta={"source": "panic_quorum", "voters": distinct},
    )
    await conn.execute(mobile_q.CONSUME_PANIC_VOTES, {"site": str(site_id), "since": window_start})
    return PanicVoteOut(
        status="activated",
        distinct_voters=distinct,
        remaining=0,
        window_s=settings.panic_quorum_window_s,
    )
