"""Command service: comandos remotos de actuador firmados (T-1.23 · B9).

Superficie MÁS sensible del sistema (regla de oro 8 / RBAC §4.3). No negociable:
1. **Firmado**: HMAC byte-idéntico al framing del edge (vectores compartidos).
2. **MFA**: exigido POR PROCEDENCIA — ``require_mfa`` (``auth/mfa.py``, T-2.84.b)
   rechaza todo token que no venga de un pool con ``mfa_configuration = "ON"``.
   Hasta T-2.84.b esto era una nota que decía «garantizado a nivel de pool… todo
   ID token de rol web implica TOTP superado», y era falso por dos motivos: el ID
   token de Cognito **no lleva ``amr`` ni ``acr``**, así que nadie lo comprobaba; y
   AWS documenta que el PRIMER inicio de sesión de un usuario nuevo emite tokens
   aunque el pool exija MFA. Ver ``auth/mfa.py`` §1-§4 para lo que se cubre y lo
   que no.
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

from fastapi import APIRouter, Depends
from sqlalchemy import text as sql_text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.audit import audit_async
from takab_api.auth.claims import Claims, scope_filter
from takab_api.auth.deps import get_claims, get_session, require_roles
from takab_api.auth.matrix import ROLE_ACTION_MATRIX, allowed_actions, roles_with_action
from takab_api.auth.mfa import require_mfa
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
from takab_api.commands.publisher import CommandPublisher, IotDataPublisher, PublishError
from takab_api.commands.rejection_audit import (
    PROOF_SESSION,
    PROOF_SESSION_DEVICE,
    audit_command_rejection,
    fingerprint,
)
from takab_api.commands.service import issue_signed_command
from takab_api.commands.signing import canonical_payload as _canonical_catalog
from takab_api.commands.signing import sign_catalog
from takab_api.queries import commands as q
from takab_api.queries import mobile as mobile_q
from takab_api.routers._common import http_error, integrity_error
from takab_api.schemas.commands import (
    ACTIONS,
    CHANNELS,
    CatalogPushIn,
    CatalogPushOut,
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

#: Guarda de LECTURA: sólo el rol. Listar los comandos de un sitio no mueve nada,
#: y la regla de oro 8 habla de la superficie de ACTUACIÓN — extenderle el MFA a
#: una consulta sería prohibir de más sin ganar nada.
_require_command_role = require_roles(*COMMAND_ROLES)

#: Guarda de EMISIÓN: constancia de MFA **y luego** rol (regla de oro 8, `RO-8.c`).
#: El orden es la mitad del control: si el rol se mirara primero, un rol sin
#: acciones de comando se caería ahí y la guarda de MFA no llegaría a correr nunca
#: — el rechazo seguiría siendo un accidente del catálogo de roles, que es el
#: defecto que `RO-8.c` describe. Ver `auth/mfa.py`.
_require_command = require_roles(*COMMAND_ROLES, inner=require_mfa(get_claims))

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

    # [T-2.86.b · RO-8.g/RO-8.k] A partir de AQUÍ se conoce el tenant TOCADO, así
    # que todo rechazo puede archivarse en la bitácora de su dueño (no en la del
    # operador — T-2.71). Los rechazos de más arriba (matriz de rol, alcance,
    # sitio invisible) no llegan a saber a quién se le intentó tocar el gabinete;
    # ver §4 del docstring de commands/rejection_audit.py.
    tenant_id = str(site.tenant_id)

    async def rejected(reason: str, status: int, **extra: object) -> None:
        await audit_command_rejection(
            claims=claims,
            tenant_id=tenant_id,
            site_id=site_id,
            reason=reason,
            status=status,
            channel=body.channel,
            action=body.action,
            extra=extra or None,
        )

    audit_meta = None
    nonce_override = None
    # Prueba de identidad detrás del intento: la sesión SIEMPRE (el JWT ya validó
    # contra Cognito y `require_mfa` ya exigió que venga de un pool con MFA ON —
    # T-2.84.b); el DISPOSITIVO solo tras verificar la firma de la intención, más
    # abajo.
    actor_proof = PROOF_SESSION
    if tactical:
        intent = body.intent
        if intent is None:
            await rejected("intent_missing", 403)
            raise http_error(403, "se requiere intención firmada (RBAC §4.3)")
        if not settings.command_intent_secret:
            # FAIL-CLOSED: sin secreto configurado no hay ruta táctica.
            await rejected("intent_secret_unconfigured", 503)
            raise http_error(503, "intención firmada no configurada en el servidor")
        # Lo que la intención DICE ser, mientras no esté probado. Ni la firma ni
        # el nonce se archivan en claro: son credenciales, y `audit_log` no se
        # poda jamás (regla de oro 11). Van sus huellas, que bastan para
        # correlacionar sondeos repetidos.
        claimed = {
            "claimed_intent_key_id": str(intent.key_id),
            "nonce_sha256": fingerprint(intent.nonce),
            "intent_sha256": intent_sha256(intent.signature),
        }
        reason = nonce_error(
            settings.command_intent_secret,
            intent.nonce,
            sub=claims.sub,
            site_id=str(site_id),
            now=datetime.now(tz=UTC),
        )
        if reason is not None:
            await rejected("intent_nonce_rejected", 403, detail=reason, **claimed)
            raise http_error(403, f"nonce de intención rechazado: {reason}")
        if (await conn.execute(q.NONCE_EXISTS, {"nonce": intent.nonce})).first() is not None:
            # El replay se corta ANTES de verificar la firma: así un nonce ya
            # quemado no es un oráculo para quien tiene sesión pero no el
            # teléfono. Corolario honesto para la bitácora: en este punto el
            # dispositivo NO está probado y el key_id queda como reclamado.
            await rejected("nonce_replay", 409, **claimed)
            raise http_error(409, "nonce de intención ya usado (replay rechazado)")
        key_row = (
            await conn.execute(q.DEVICE_KEY, {"key_id": str(intent.key_id), "sub": claims.sub})
        ).first()
        if key_row is None:
            await rejected("device_key_unknown", 403, **claimed)
            raise http_error(403, "llave de dispositivo no registrada o revocada")
        message = canonical_intent(
            key_id=str(intent.key_id),
            site_id=str(site_id),
            channel=body.channel,
            action=body.action,
            nonce=intent.nonce,
        )
        if not intent_signature_valid(key_row.public_key, intent.signature, message):
            await rejected("intent_signature_invalid", 403, **claimed)
            raise http_error(403, "firma de intención inválida")
        # Dispositivo PROBADO: solo ahora el key_id deja de ser "reclamado".
        actor_proof = PROOF_SESSION_DEVICE
        nonce_override = intent.nonce
        audit_meta = {
            "intent_key_id": str(intent.key_id),
            "intent_sha256": intent_sha256(intent.signature),
        }

    # [T-1.60] La emisión (rate-limit + clave por gateway + firma + insert +
    # publish + audit, incluida la de sus rechazos) vive en commands/service.py
    # — compartida con /drills.
    try:
        row = await issue_signed_command(
            conn,
            settings=settings,
            publisher=publisher,
            keys=keys,
            claims=claims,
            site_id=site_id,
            tenant_id=tenant_id,
            channel=body.channel,
            action=body.action,
            event_id=body.event_id,
            nonce_override=nonce_override,
            audit_meta=audit_meta,
            actor_proof=actor_proof,
        )
    except IntegrityError as exc:
        # Backstop del UNIQUE de commands.nonce ante replays concurrentes. Aquí
        # la intención YA verificó, así que —a diferencia del 409 temprano— este
        # replay sí llega con el dispositivo probado.
        if getattr(getattr(exc, "orig", None), "sqlstate", None) == "23505":
            await audit_command_rejection(
                claims=claims,
                tenant_id=tenant_id,
                site_id=site_id,
                reason="nonce_replay_race",
                status=409,
                channel=body.channel,
                action=body.action,
                actor_proof=actor_proof,
            )
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
    claims: Claims = Depends(_require_command_role),
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

# [T-2.84.b · `RO-8.c`] La ÚNICA excepción declarada al MFA en esta superficie, y
# va sin `require_mfa` a propósito: el votante es un `occupant` del pool con
# `mfa_configuration = "OPTIONAL"` (decisión #7), o sea que puede legítimamente no
# tener TOTP. Exigirle segundo factor a quien pide auxilio con el edificio
# temblando invertiría el sentido de la regla de oro 8. Queda ACOTADA por otros
# tres controles —quórum de 2 votantes DISTINTOS en ventana, geofence y
# rate-limit por usuario— y por el hecho de que el comando emitido es siempre
# `siren/activate`, cableado abajo: este camino no puede tocar gas ni ascensores.
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

    # [T-2.147.a · D-11] EL INCIDENTE, ANTES DEL COMANDO. Un pánico ES un
    # incidente operativo —algo pasó en el edificio, alguien debe responder, y
    # tiene que quedar registro—; lo que no es, es un sismo, y de eso responde
    # `trigger='manual'`. Va primero porque el push cuelga de él: sin incidente,
    # `notification_jobs` no admite la fila (`incident_id` NOT NULL).
    await conn.execute(
        mobile_q.INSERT_PANIC_INCIDENT,
        {
            "event_uuid": str(uuid4()),
            "tenant": tenant_id,
            "site": str(site_id),
            "opened_at": now,
            "summary": json.dumps({"source": "panic_quorum", "voters": distinct}),
        },
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
    # [T-2.147.a · D-05] EL PUSH A LOS TÁCTICOS NO SE ENCOLA AQUÍ, y no es un
    # olvido: `notification_jobs` tiene RLS que solo admite escrituras de los
    # roles internos de TAKAB —los jobs los crea el worker, que corre como
    # `takab_ingest`—, y una petición de occupant no lo es. Debilitar esa
    # política para que el teléfono de un ocupante pudiera encolar
    # notificaciones sería exactamente la frontera que no hay que mover.
    #
    # Lo que este router deja es el HECHO: un incidente `manual` recién abierto.
    # El worker lo recoge en su siguiente pasada (`_enqueue_panic_push`) y de
    # paso hereda gratis lo que ya sabe hacer: idempotencia, reintento con
    # backoff, evidencia y cuarentena de canal caído.
    return PanicVoteOut(
        status="activated",
        distinct_voters=distinct,
        remaining=0,
        window_s=settings.panic_quorum_window_s,
    )


# ---------------------------------------------------------------- catálogo SSN

# [T-2.24] Push del catálogo SSN firmado al gabinete. Interno-only: es contenido
# informativo de plataforma (no toca actuación), pero viaja FIRMADO con la clave
# del gabinete — mismo régimen fail-closed por gateway que los comandos (T-1.38).
_require_catalog_push = require_roles("takab_superadmin", "takab_support")

_CATALOG_GATEWAY_SQL = sql_text(
    "SELECT gateway_id, tenant_id, iot_thing FROM gateways WHERE gateway_id = :gw"
)
_CATALOG_STATE_SQL = sql_text("SELECT version FROM gateway_catalog_state WHERE gateway_id = :gw")
_CATALOG_UPSERT_SQL = sql_text(
    "INSERT INTO gateway_catalog_state "
    "  (gateway_id, tenant_id, version, payload, sig, published_at) "
    "VALUES (:gw, :tenant, :version, CAST(:payload AS jsonb), :sig, now()) "
    "ON CONFLICT (gateway_id) DO UPDATE "
    "SET version = EXCLUDED.version, payload = EXCLUDED.payload, "
    "    sig = EXCLUDED.sig, published_at = EXCLUDED.published_at"
)


@router.post("/gateways/{gateway_id}/catalog", response_model=CatalogPushOut, status_code=202)
async def push_catalog(
    gateway_id: UUID,
    body: CatalogPushIn,
    claims: Claims = Depends(_require_catalog_push),
    conn: AsyncConnection = Depends(get_session),
    publisher: CommandPublisher = Depends(get_publisher),
    keys: CommandKeyProvider = Depends(get_key_provider),
) -> CatalogPushOut:
    """Firma y publica la instantánea SSN a ``takab/catalog/<thing>`` (T-2.24).

    Versión MONÓTONA por gateway (``gateway_catalog_state``); el edge rechaza
    toda versión ya vista y persiste ATÓMICO. Sin clave HMAC resoluble ⇒ 503
    (fail-closed, jamás se firma con una compartida). La periodicidad es una
    llamada programada a este endpoint; el contrato de ``GET /api/catalog`` en
    el panel no cambia.
    """
    catalog = body.catalog
    if not isinstance(catalog.get("eventos"), list) or not catalog.get("capturado"):
        raise http_error(400, "catálogo inválido: exige 'eventos' (lista) y 'capturado'")
    row = (await conn.execute(_CATALOG_GATEWAY_SQL, {"gw": gateway_id})).first()
    if row is None:
        raise http_error(404, "gateway inexistente")
    if row.iot_thing is None:
        raise http_error(409, "gateway sin iot_thing: no es alcanzable por IoT")
    key = keys.key_for(row.iot_thing)
    if key is None:
        raise http_error(503, "sin clave HMAC resoluble para el gateway (fail-closed)")

    state = (await conn.execute(_CATALOG_STATE_SQL, {"gw": gateway_id})).first()
    version = (state.version if state else 0) + 1
    signature = sign_catalog(key, _canonical_catalog(catalog), version)
    envelope = {
        "kind": "catalog_update",
        "version": version,
        "payload": catalog,
        "sig": signature,
    }
    topic = f"takab/catalog/{row.iot_thing}"
    try:
        publisher.publish(topic, json.dumps(envelope).encode())
    except PublishError as exc:
        # Sin upsert: la versión no se quema si no salió al aire.
        raise http_error(502, f"publish IoT falló: {exc}") from exc
    await conn.execute(
        _CATALOG_UPSERT_SQL,
        {
            "gw": gateway_id,
            "tenant": str(row.tenant_id),
            "version": version,
            "payload": json.dumps(catalog),
            "sig": signature,
        },
    )
    await audit_async(
        conn,
        tenant_id=str(row.tenant_id),
        actor=f"user:{claims.sub}",
        verb="catalog_published",
        obj=f"gateway:{gateway_id}",
        meta={"version": version, "sig": signature[:16], "capturado": catalog.get("capturado")},
    )
    await conn.commit()
    return CatalogPushOut(gateway_id=str(gateway_id), version=version, topic=topic)
