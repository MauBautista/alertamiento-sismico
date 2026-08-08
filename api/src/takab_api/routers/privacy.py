"""T-2.79 · ``/privacy``: el aviso vigente y el registro de quién aceptó qué.

Cuatro cosas que este router hace, y ninguna es opcional:

1. **El estado lo decide el SERVIDOR, comparando digests.** El cliente no
   recalcula si su consentimiento sigue valiendo: si lo hiciera habría dos
   verdades y la del cliente mentiría en cuanto el aviso cambiara entre dos
   peticiones. ``GET /privacy/consent`` devuelve el aviso vigente **y** el
   estado (``missing``/``current``/``stale``/``withdrawn``) en la misma
   respuesta, para que la UI no tenga que cruzarlos ella.

2. **El POST exige el digest que el cliente tenía en pantalla.** Sin eso, quien
   dejó la pantalla abierta mientras el aviso cambiaba acabaría firmando el
   texto NUEVO habiendo leído el VIEJO — la misma clase de mentira que la tarea
   entera existe para impedir. Si no coincide, 409 con el aviso nuevo: se vuelve
   a leer y se vuelve a decidir.

3. **No bloquea nada de emergencia, y lo dice en el contrato.** No hay ninguna
   dependencia de este módulo en el check-in de vida, el botón de ayuda, el
   reporte de daños ni la alerta. ``ConsentStatusOut.blocks_emergency_actions``
   es literalmente ``False`` en el tipo para que ninguna UI se invente lo
   contrario, y hay un test que hace el check-in con el consentimiento en
   ``missing`` y exige 201.

4. **Escribe, nunca actualiza.** Retirar es una fila nueva (``withdraw``);
   corregir el aviso es publicar otra versión. Las dos tablas son append-only
   por trigger y jamás se podan (regla de oro 11).

Lo que este router deliberadamente NO tiene: un ``PUT`` de aviso, un ``DELETE``
de consentimiento, y un endpoint para publicar el aviso de PLATAFORMA. Los dos
primeros serían un 500 contra el trigger; el tercero no existe porque el aviso
de plataforma es un artefacto de git que se sustituye con un despliegue.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.audit import audit_async
from takab_api.auth.claims import Claims
from takab_api.auth.deps import get_claims, get_session, require_roles
from takab_api.privacy import store
from takab_api.privacy.store import ResolvedNotice
from takab_api.routers._common import http_error, integrity_error
from takab_api.schemas.privacy import (
    ConsentHistoryOut,
    ConsentIn,
    ConsentOut,
    ConsentStatusOut,
    NoticeIn,
    NoticeOut,
    NoticePublishedOut,
    ThirdPartyConsentIn,
)

router = APIRouter(prefix="/privacy", tags=["privacy"])

# Publicar el aviso del tenant y registrar el consentimiento de un tercero sin
# sesión son el mismo círculo de confianza: el DUEÑO del cliente. Bajo la
# LFPDPPP el *responsable* de los datos de los ocupantes de un inmueble es la
# organización dueña del inmueble, así que publicar su aviso es un acto suyo —
# el mismo círculo que ``edit_thresholds``/``drill_start``.
#
# ``takab_support`` queda fuera a propósito: soporte lee la plataforma, no firma
# el aviso de privacidad de un cliente en su nombre.
#
# [DEUDA DECLARADA · T-2.79] Esta tupla PERTENECE a ``auth/matrix.py`` como una
# acción ``manage_privacy_notice``, igual que ``maintenance_window``, y el propio
# módulo de la matriz dice "ningún router vuelve a listar roles a mano". Está
# aquí porque ``auth/matrix.py`` lo está tocando otra tarea en paralelo (T-2.82)
# y dos ediciones simultáneas de la firma de ``_actions()`` chocan seguro.
# **Mover al integrar**: añadir la acción a ``ACTIONS`` + ``_actions()`` +
# ``ROLE_ACTION_MATRIX`` (superadmin y tenant_admin) y su línea en el `DENY_ALL`
# de ``tests/auth/test_matrix.py``, y sustituir esto por
# ``roles_with_action("manage_privacy_notice")``.
#
# Lo que NO depende de esta deuda: la frontera de seguridad real es la RLS
# ``pn_publish``, que exige ``app_role() IN ('tenant_admin','takab_superadmin')``
# **y** que la fila sea del propio tenant. Esta lista solo hace que el 403 llegue
# limpio y que la consola no pinte un botón que siempre fallaría (regla de oro 7).
NOTICE_ROLES: tuple[str, ...] = ("takab_superadmin", "tenant_admin")
_require_notice_admin = require_roles(*NOTICE_ROLES)


def _out(notice: ResolvedNotice) -> NoticeOut:
    return NoticeOut(
        purpose=notice.purpose,
        locale=notice.locale,
        version=notice.version,
        title=notice.title,
        body=notice.body,
        paragraphs=list(notice.paragraphs),
        digest=notice.digest,
        source=notice.source,
        notice_id=notice.notice_id,
        effective_at=notice.effective_at,
        provisional=notice.provisional,
        provisional_reason=notice.provisional_reason,
    )


async def _vigente(
    conn: AsyncConnection, claims: Claims, purpose: str, locale: str
) -> ResolvedNotice:
    notice = await store.current_notice(
        conn, tenant_id=claims.tenant_id, purpose=purpose, locale=locale
    )
    if notice is None:
        # 404 y no un texto de relleno: consentir un aviso inventado por el
        # servidor sería peor que no tener aviso. La UI lo pinta como `empty`.
        raise http_error(
            404,
            f"no hay aviso de privacidad para {purpose!r} en {locale!r}: ni publicado por "
            "este cliente ni disponible en la plataforma",
        )
    return notice


@router.get("/notice", response_model=NoticeOut)
async def get_notice(
    purpose: str = Query(default="privacy_notice"),
    locale: str = Query(default=store.DEFAULT_LOCALE),
    claims: Claims = Depends(get_claims),
    conn: AsyncConnection = Depends(get_session),
) -> NoticeOut:
    """El aviso vigente para el tenant del portador (el suyo si lo publicó)."""
    return _out(await _vigente(conn, claims, purpose, locale))


@router.get("/consent", response_model=ConsentStatusOut)
async def get_consent_status(
    purpose: str = Query(default="privacy_notice"),
    locale: str = Query(default=store.DEFAULT_LOCALE),
    claims: Claims = Depends(get_claims),
    conn: AsyncConnection = Depends(get_session),
) -> ConsentStatusOut:
    """Aviso vigente + estado del consentimiento del portador, en una respuesta.

    Van juntos a propósito: separarlos obligaría a la UI a comparar digests, y
    entre las dos peticiones el aviso puede cambiar — pintaría ``current`` sobre
    un texto que ya no es el vigente.
    """
    notice = await store.current_notice(
        conn, tenant_id=claims.tenant_id, purpose=purpose, locale=locale
    )
    consent = await store.latest_consent(
        conn, tenant_id=claims.tenant_id, purpose=purpose, subject_ref=claims.sub
    )
    return ConsentStatusOut(
        notice=_out(notice) if notice else None,
        state=store.consent_state(notice, consent),
        consent=ConsentOut(**dict(consent)) if consent else None,
    )


@router.get("/consent/history", response_model=ConsentHistoryOut)
async def get_consent_history(
    purpose: str = Query(default="privacy_notice"),
    limit: int = Query(default=20, ge=1, le=200),
    claims: Claims = Depends(get_claims),
    conn: AsyncConnection = Depends(get_session),
) -> ConsentHistoryOut:
    """El historial del portador. Un registro append-only que no se puede leer
    no prueba nada: "acepté la v1, la retiré, acepté la v2" es la respuesta a
    una reclamación."""
    filas = await store.consent_history(
        conn, tenant_id=claims.tenant_id, purpose=purpose, subject_ref=claims.sub, limit=limit
    )
    return ConsentHistoryOut(items=[ConsentOut(**dict(f)) for f in filas])


@router.post("/consent", response_model=ConsentOut, status_code=201)
async def record_consent(
    body: ConsentIn,
    claims: Claims = Depends(get_claims),
    conn: AsyncConnection = Depends(get_session),
) -> ConsentOut:
    """Acepta o RETIRA. Siempre una fila nueva; jamás un UPDATE.

    Cualquier sesión autenticada puede hacerlo sobre SU propia fila —es un
    derecho del titular del dato, no un permiso que se concede— y la RLS
    ``pc_self`` la acota. Por eso no lleva ``require_roles``.
    """
    notice = await _vigente(conn, claims, body.purpose, body.locale)
    if body.digest != notice.digest:
        raise http_error(
            409,
            "el aviso cambió mientras estaba en pantalla: vuelve a leerlo antes de "
            f"decidir (vigente {notice.version!r}, digest {notice.digest[:12]}…)",
        )
    estado_previo = store.consent_state(
        notice,
        await store.latest_consent(
            conn, tenant_id=claims.tenant_id, purpose=body.purpose, subject_ref=claims.sub
        ),
    )
    fila = await store.record_consent(
        conn,
        tenant_id=claims.tenant_id,
        purpose=body.purpose,
        notice=notice,
        decision=body.decision,
        via=body.via,
        actor_sub=claims.sub,
        user_sub=claims.sub,
    )
    await audit_async(
        conn,
        tenant_id=claims.tenant_id,
        actor=f"user:{claims.sub}",
        verb=f"privacy_consent_{body.decision}",
        obj=f"privacy_consent:{fila['consent_id']}",
        meta=_meta(notice, decision=body.decision, via=body.via, state_before=estado_previo),
    )
    return await _leer_consentimiento(conn, claims.tenant_id, body.purpose, claims.sub)


@router.post("/consents/third-party", response_model=ConsentOut, status_code=201)
async def record_third_party_consent(
    body: ThirdPartyConsentIn,
    claims: Claims = Depends(_require_notice_admin),
    conn: AsyncConnection = Depends(get_session),
) -> ConsentOut:
    """Constancia del consentimiento de un TERCERO sin sesión (un teléfono).

    Es el opt-in de WhatsApp (T-2.77): la guardia del SOC da su número y su
    autorización fuera de la app, y alguien tiene que dejar constancia de qué
    texto se le enseñó y cuándo. ``actor_sub`` guarda quién lo registró, separado
    del sujeto: confundirlos borraría la diferencia entre "la persona autorizó"
    y "un administrador lo dio por hecho".
    """
    notice = await _vigente(conn, claims, body.purpose, body.locale)
    if body.digest != notice.digest:
        raise http_error(
            409,
            "el texto cambió mientras estaba en pantalla: vuelve a leerlo antes de "
            f"registrar el consentimiento (vigente {notice.version!r})",
        )
    estado_previo = store.consent_state(
        notice,
        await store.latest_consent(
            conn, tenant_id=claims.tenant_id, purpose=body.purpose, subject_ref=body.msisdn
        ),
    )
    try:
        fila = await store.record_consent(
            conn,
            tenant_id=claims.tenant_id,
            purpose=body.purpose,
            notice=notice,
            decision=body.decision,
            via=body.via,
            actor_sub=claims.sub,
            msisdn=body.msisdn,
        )
    except IntegrityError as exc:
        raise integrity_error(exc) from exc
    await audit_async(
        conn,
        tenant_id=claims.tenant_id,
        actor=f"user:{claims.sub}",
        verb=f"privacy_consent_{body.decision}",
        obj=f"privacy_consent:{fila['consent_id']}",
        # El número NO va al `audit_log`: la bitácora no se poda jamás (regla de
        # oro 11) y meter un teléfono ahí es PII eterna sin necesidad. El sujeto
        # ya está en `privacy_consents`, que es donde toca y donde la RLS acota.
        meta=_meta(
            notice,
            decision=body.decision,
            via=body.via,
            state_before=estado_previo,
            subject_kind="msisdn",
        ),
    )
    return await _leer_consentimiento(conn, claims.tenant_id, body.purpose, body.msisdn)


@router.post("/notices", response_model=NoticePublishedOut, status_code=201)
async def publish_notice(
    body: NoticeIn,
    claims: Claims = Depends(_require_notice_admin),
    conn: AsyncConnection = Depends(get_session),
) -> NoticePublishedOut:
    """Publica el aviso del TENANT. No existe el equivalente para editar.

    Los dos 409 posibles dicen cosas distintas y las dos son útiles: el mismo
    texto con otra etiqueta (no es una versión nueva) y la misma etiqueta con
    otro texto (sería una versión que miente).
    """
    try:
        fila = await store.publish_notice(
            conn,
            tenant_id=claims.tenant_id,
            purpose=body.purpose,
            locale=body.locale,
            version=body.version,
            title=body.title,
            body=body.body,
            published_by=claims.sub,
            effective_at=body.effective_at,
        )
    except IntegrityError as exc:
        raise integrity_error(exc) from exc
    await audit_async(
        conn,
        tenant_id=claims.tenant_id,
        actor=f"user:{claims.sub}",
        verb="privacy_notice_publish",
        obj=f"privacy_notice:{fila['notice_id']}",
        # El CUERPO no va a la bitácora: el `audit_log` no se poda jamás y una
        # copia del aviso completo en cada publicación lo engorda sin añadir
        # nada — el digest identifica el texto y la fila lo conserva íntegro.
        meta={
            "purpose": body.purpose,
            "locale": body.locale,
            "version": body.version,
            "digest": fila["digest"],
            "effective_at": fila["effective_at"].isoformat(),
        },
    )
    return NoticePublishedOut(**dict(fila))


def _meta(
    notice: ResolvedNotice,
    *,
    decision: str,
    via: str,
    state_before: str,
    subject_kind: str = "user",
) -> dict:
    """`meta` de la auditoría: el SELLO, nunca el cuerpo del aviso."""
    return {
        "decision": decision,
        "via": via,
        "subject_kind": subject_kind,
        "state_before": state_before,
        "notice_source": notice.source,
        "notice_id": notice.notice_id,
        "notice_version": notice.version,
        "notice_locale": notice.locale,
        "notice_digest": notice.digest,
        "provisional": notice.provisional,
    }


async def _leer_consentimiento(
    conn: AsyncConnection, tenant_id: str, purpose: str, subject_ref: str
) -> ConsentOut:
    """Relee la fila recién escrita: `decided_at` lo pone la base, no el cliente."""
    fila = await store.latest_consent(
        conn, tenant_id=tenant_id, purpose=purpose, subject_ref=subject_ref
    )
    if fila is None:  # pragma: no cover - la fila se acaba de insertar
        raise http_error(500, "el consentimiento se escribió pero no se pudo releer")
    return ConsentOut(**dict(fila))
