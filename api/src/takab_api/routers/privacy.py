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

Y desde T-2.80.b tampoco tiene —ni tendrá por aquí— un endpoint que **borre la
cuenta en Cognito**. Anonimizar es destruir el mapeo ``sub → persona`` en esta
base; dar de baja la identidad es otro acto, en otro sistema, con otra
consecuencia (quien pierde la cuenta pierde el acceso a la app de emergencia del
edificio) y necesita su propia ficha. El razonamiento completo está en
``takab_api.privacy.erasure``, sección "LO QUE ESTA TAREA NO HACE".
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Response
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.audit import audit_async, audit_out_of_band_async
from takab_api.auth.claims import Claims
from takab_api.auth.deps import get_claims, get_session, require_roles
from takab_api.auth.matrix import roles_with_action
from takab_api.db.session import SessionCtx
from takab_api.privacy import crypto, erasure, store
from takab_api.privacy.store import ResolvedNotice
from takab_api.routers._common import http_error, integrity_error
from takab_api.schemas.privacy import (
    ConsentHistoryOut,
    ConsentIn,
    ConsentOut,
    ConsentStatusOut,
    ErasureIn,
    ErasureOnBehalfIn,
    ErasureOut,
    ErasureProofOut,
    ErasureRequestIn,
    ErasureRequestOut,
    NoticeIn,
    NoticeOut,
    NoticePublishedOut,
    ThirdPartyConsentIn,
)
from takab_api.settings import Settings

router = APIRouter(prefix="/privacy", tags=["privacy"])

# [T-2.79.e] Publicar el aviso del tenant y registrar el consentimiento de un
# tercero sin sesión son el mismo círculo de confianza —el DUEÑO del cliente— y
# por eso son UNA acción de la matriz, no dos listas. El razonamiento (por qué
# ``takab_support`` queda fuera, por qué es el círculo de ``drill_start``) vive
# junto a la acción en ``auth/matrix.py``, que es donde alguien va a buscarlo.
#
# Lo que esta línea NO es: la frontera de seguridad. Esa la impone la RLS
# ``pn_publish``, que exige ``app_role() IN ('tenant_admin','takab_superadmin')``
# **y** que la fila sea del propio tenant — una condición que ninguna matriz de
# roles sabe expresar. Derivar de la matriz solo hace que el 403 llegue limpio y
# que la consola no pinte un botón que siempre fallaría (regla de oro 7).
NOTICE_ROLES: tuple[str, ...] = roles_with_action("manage_privacy_notice")
_require_notice_admin = require_roles(*NOTICE_ROLES)

# [T-2.80.b] Registrar y ejecutar una solicitud ARCO recibida por escrito. Acción
# APARTE de la de arriba aunque hoy comparta roles: publicar un aviso se deshace
# publicando otra versión, anonimizar a una persona no se deshace.
#
# Y esta línea es todavía menos la frontera que la anterior. Lo que impide que un
# responsable anonimice a quien le apetezca es la CONSTANCIA: sin fila en
# `privacy_erasure_requests`, `app_can_erase_subject` es falso y las cinco
# políticas RLS que cuelgan de él no dejan tocar un solo dato de esa persona. Y a
# quién puede nombrar una constancia lo decide un FK compuesto contra el padrón
# del propio cliente, no un rol.
ERASURE_ROLES: tuple[str, ...] = roles_with_action("manage_privacy_erasure")
_require_erasure_admin = require_roles(*ERASURE_ROLES)


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
    # [T-2.150 · D-07] SIN LOS SECRETOS DEL SUJETO NO SE REGISTRA NADA.
    #
    # Se comprueba ANTES de resolver el aviso para no reventar a mitad de una
    # transacción que ya escribió. 503 y no 400: la configuración que falta es
    # del despliegue, no del llamador, y culparle a él manda a la persona
    # equivocada a buscar el problema.
    #
    # No hay degradación a texto en claro: escribiría el defecto que esta ficha
    # cierra en una tabla append-only, en silencio y para siempre.
    if not crypto.disponible(Settings()):
        raise http_error(
            503,
            "el registro de consentimientos por teléfono no está disponible: faltan "
            "los secretos del sujeto en el despliegue (fail-closed; el número JAMÁS "
            "se guarda en claro)",
        )
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


# ---------------------------------------------------------------------------
# T-2.80 · ARCO por anonimización con tombstone
# ---------------------------------------------------------------------------


@router.post("/erasure", response_model=ErasureOut, status_code=201)
async def exercise_erasure(
    body: ErasureIn,
    response: Response,
    claims: Claims = Depends(get_claims),
    conn: AsyncConnection = Depends(get_session),
) -> ErasureOut:
    """Ejerce cancelación u oposición SOBRE UNO MISMO. Anonimiza; jamás borra.

    Sin ``require_roles``, igual que ``POST /consent``: es un derecho del titular
    del dato, no un permiso que se concede. Y sin sujeto en el cuerpo: la función
    de base de datos opera sobre ``app_user_id()``, así que ejercer ARCO sobre un
    tercero —o cruzar tenants— no está prohibido, es **inexpresable**.

    Tres respuestas y ninguna ambigua:

    * **201** — se ejerció ahora. ``affected`` dice cuántas filas se anonimizaron
      por tabla; ninguna se borró.
    * **200** — ya se había ejercido. Es idempotencia (regla de oro 3), no un
      fallo: se devuelve la MISMA lápida, testigo sellado del primer acto.
    * **409** — hay un incidente ABIERTO en un sitio del titular y la
      anonimización se DIFIERE. Ver ``privacy_erase_subject`` en el schema: la
      ubicación de un check-in es dato de rescate en vivo y anularla a mitad de
      una búsqueda es un fallo de seguridad. El derecho no se niega, se aplaza —
      y la petición queda auditada FUERA DE BANDA para que el plazo legal corra
      igual (el 409 hace rollback y se llevaría la fila por delante).
    """
    try:
        fila = await erasure.erase_self(conn, right=body.right, via=body.via)
    except DBAPIError as exc:
        await _traducir_fallo_de_arco(
            exc,
            claims,
            deferred_obj=f"privacy_erasure:{claims.sub}",
            deferred_meta={"right": body.right, "via": body.via, "reason": "incidente_abierto"},
        )
        raise

    if not fila["created"]:
        # 200 y no 409: pedir dos veces lo mismo no es un conflicto, y devolver un
        # error haría creer que el borrado no ocurrió.
        response.status_code = 200
    else:
        await audit_async(
            conn,
            tenant_id=claims.tenant_id,
            actor=f"user:{claims.sub}",
            verb="privacy_erasure",
            obj=f"privacy_erasure:{fila['erasure_id']}",
            # Conteos y sello, NUNCA el dato anonimizado: el `audit_log` no se
            # poda jamás (regla de oro 11), así que una copia del nombre aquí
            # sería PII eterna — y además desharía la anonimización.
            meta=_meta_de_lapida(fila),
        )
    return ErasureOut(**fila)


def _meta_de_lapida(fila) -> dict:
    """Conteos y sello. Nunca el dato anonimizado (regla de oro 11)."""
    return {
        "right": fila["right_exercised"],
        "via": fila["via"],
        "affected": fila["affected"],
        "audit_watermark": fila["audit_watermark"],
        "audit_digest": fila["audit_digest"],
    }


async def _traducir_fallo_de_arco(
    exc: DBAPIError,
    claims: Claims,
    *,
    deferred_obj: str,
    deferred_meta: dict,
) -> None:
    """Los tres fallos que decide la BASE, traducidos a HTTP. Vuelve sin lanzar si
    no es ninguno de ellos, para que quien llame re-lance el error original — un
    500 honesto es mejor que un 4xx inventado.

    Vive fuera de los handlers porque las dos puertas de ARCO —el titular y el
    responsable— fallan por lo mismo y tienen que fallar igual. Duplicarlo era el
    camino corto a que una de las dos dejara de auditar el diferimiento.
    """
    estado = getattr(exc.orig, "sqlstate", None)
    if estado == erasure.SQLSTATE_DEFERRED:
        # El 409 hace rollback y se llevaría la fila por delante: la petición se
        # audita FUERA DE BANDA para que el plazo legal corra igual.
        await audit_out_of_band_async(
            SessionCtx.from_claims(claims),
            tenant_id=claims.tenant_id,
            actor=f"user:{claims.sub}",
            verb="privacy_erasure_deferred",
            obj=deferred_obj,
            meta=deferred_meta,
        )
        raise http_error(
            409,
            "hay un incidente abierto en un sitio asociado a ese titular: la "
            "anonimización se difiere hasta que cierre, porque la ubicación de un "
            "check-in de vida es dato de rescate en vivo. La solicitud queda "
            "registrada; vuelve a intentarlo cuando el incidente se cierre",
        ) from exc
    if estado == erasure.SQLSTATE_FORBIDDEN:
        raise http_error(
            403, "el token no identifica a un portador: ARCO exige una sesión con sujeto"
        ) from exc
    if estado == erasure.SQLSTATE_NO_CONSTANCIA:
        # 404 y no 403: una constancia de otro cliente no está prohibida, es que
        # NO EXISTE para esta sesión. Distinguirlas filtraría la existencia de una
        # solicitud ajena (regla de oro 5).
        raise http_error(
            404,
            "no hay constancia de esa solicitud: ejercer ARCO por cuenta de otro exige "
            "registrarla antes en POST /privacy/erasure-requests",
        ) from exc


@router.get("/erasure", response_model=ErasureProofOut)
async def get_erasure_proof(
    claims: Claims = Depends(get_claims),
    conn: AsyncConnection = Depends(get_session),
) -> ErasureProofOut:
    """La lápida propia MÁS la comprobación de que la bitácora sigue cuadrando.

    No devuelve solo lo que se selló el día del borrado: **recalcula** el digest
    en esta misma petición y responde si coincide. Un sello guardado que nadie
    recomputa no prueba nada; esto convierte "el ``audit_log`` sigue íntegro y
    verificable" en una medición que cualquiera puede pedir, y no en una
    afirmación del día del despliegue.
    """
    fila = await erasure.tombstone(conn, tenant_id=claims.tenant_id, user_sub=claims.sub)
    if fila is None:
        raise http_error(404, "no hay constancia de ARCO para este titular")
    ahora = await erasure.audit_digest_now(
        conn, tenant_id=claims.tenant_id, watermark=fila["audit_watermark"]
    )
    return ErasureProofOut(
        erasure=ErasureOut(**dict(fila)),
        audit_digest_now=ahora,
        audit_intact=(ahora == fila["audit_digest"]),
    )


# ---------------------------------------------------------------------------
# T-2.80.b · El responsable ejecuta un ARCO recibido POR ESCRITO
#
# Dos endpoints y no uno, y la separación es la tarea. Recibir la solicitud y
# ejecutarla son dos actos con dos fechas distintas —de la primera corre el plazo
# legal— y con dos auditorías. Fundirlos habría convertido la constancia en un
# campo del cuerpo del borrado: algo que se teclea al vuelo para que el POST pase,
# en vez de el registro de un escrito que llegó.
# ---------------------------------------------------------------------------


@router.post("/erasure-requests", response_model=ErasureRequestOut, status_code=201)
async def record_erasure_request(
    body: ErasureRequestIn,
    claims: Claims = Depends(_require_erasure_admin),
    conn: AsyncConnection = Depends(get_session),
) -> ErasureRequestOut:
    """Deja constancia de una solicitud ARCO recibida fuera de la app.

    No anonimiza nada: registra que llegó un escrito, de quién, cuándo, por qué
    canal y con qué prueba. La ejecución es el endpoint de abajo, a propósito.

    El ``user_sub`` viaja en el cuerpo y **no abre el ARCO cruzado**: la fila lleva
    un FK compuesto ``(tenant_id, user_sub) → user_profiles`` y el ``tenant_id`` no
    es un parámetro (lo pone ``app_tenant_id()``), así que nombrar a un titular de
    otro cliente no se rechaza por una comprobación — viola integridad
    referencial, y se responde 404 igual que si no existiera. Que las dos
    situaciones sean indistinguibles es deliberado (regla de oro 5).
    """
    try:
        fila = await erasure.record_request(
            conn,
            user_sub=str(body.user_sub),
            right=body.right,
            channel=body.channel,
            received_at=body.received_at,
            proof_ref=body.proof_ref,
            proof_digest=body.proof_digest,
            actor_sub=claims.sub,
        )
    except IntegrityError as exc:
        estado = getattr(exc.orig, "sqlstate", None)
        if estado == "23503":  # foreign_key_violation → no está en el padrón
            raise http_error(
                404,
                "ese titular no está en el padrón de este cliente: una constancia solo "
                "puede nombrar a alguien de tu propio tenant",
            ) from exc
        if estado == "23514":  # check_violation → created_by = user_sub
            raise http_error(
                400,
                "quien registra la constancia no puede ser el propio titular: para "
                "ejercer tu propio ARCO está POST /privacy/erasure",
            ) from exc
        raise integrity_error(exc) from exc

    await audit_async(
        conn,
        tenant_id=claims.tenant_id,
        actor=f"user:{claims.sub}",
        verb="privacy_erasure_request",
        obj=f"privacy_erasure_request:{fila['request_id']}",
        # `proof_ref` NO va a la bitácora: es texto libre que un operador puede
        # llenar con un correo o un nombre, y el `audit_log` no se poda jamás
        # (regla de oro 11). El `proof_digest` identifica el documento sin
        # copiarlo, que es exactamente lo que hace falta para probarlo.
        meta={
            "subject_sub": str(fila["user_sub"]),
            "right": fila["right_requested"],
            "channel": fila["channel"],
            "received_at": fila["received_at"].isoformat(),
            "proof_digest": fila["proof_digest"],
        },
    )
    return ErasureRequestOut(**dict(fila))


@router.post("/erasure-requests/{request_id}/erasure", response_model=ErasureOut, status_code=201)
async def exercise_erasure_on_behalf(
    body: ErasureOnBehalfIn,
    response: Response,
    request_id: UUID = Path(...),
    claims: Claims = Depends(_require_erasure_admin),
    conn: AsyncConnection = Depends(get_session),
) -> ErasureOut:
    """Ejecuta la constancia. **El cuerpo no lleva sujeto, y la ruta tampoco.**

    Lo que la ruta lleva es el ``request_id`` de una solicitud ya registrada; el
    sujeto y el derecho salen de ella, resueltos DENTRO de la base contra el padrón
    del tenant de la sesión. Por eso ejercer ARCO sobre un titular ajeno sigue sin
    poder formularse: no hay parámetro que lo nombre en ninguna capa.

    Mismas tres respuestas que el autoservicio (201 / 200 idempotente / 409
    diferido por incidente abierto), más un **404** cuando no hay constancia — que
    es también la respuesta a una constancia de otro cliente, porque para esta
    sesión no existe.
    """
    constancia = await erasure.request(conn, request_id=str(request_id))
    if constancia is None:
        raise http_error(
            404,
            "no hay constancia de esa solicitud: ejercer ARCO por cuenta de otro exige "
            "registrarla antes en POST /privacy/erasure-requests",
        )
    try:
        fila = await erasure.erase_on_behalf(conn, via=body.via, request_id=str(request_id))
    except DBAPIError as exc:
        await _traducir_fallo_de_arco(
            exc,
            claims,
            deferred_obj=f"privacy_erasure_request:{request_id}",
            deferred_meta={
                "subject_sub": str(constancia["user_sub"]),
                "right": constancia["right_requested"],
                "via": body.via,
                "request_id": str(request_id),
                "reason": "incidente_abierto",
            },
        )
        raise

    if not fila["created"]:
        # Ya se había ejercido (por el titular o por otra constancia). 200, no 409.
        response.status_code = 200
    else:
        await audit_async(
            conn,
            tenant_id=claims.tenant_id,
            # `actor` = quién lo EJECUTÓ. Es el campo canónico de la bitácora.
            actor=f"user:{claims.sub}",
            verb="privacy_erasure_on_behalf",
            obj=f"privacy_erasure:{fila['erasure_id']}",
            meta={
                **_meta_de_lapida(fila),
                # Criterio 2 de la ficha, las tres piezas y en claro:
                #  · quién lo PIDIÓ  → el titular de la constancia (`sub` opaco,
                #    cuyo mapeo destruye esta misma transacción);
                #  · quién lo EJECUTÓ → repetido aquí además de en `actor` para
                #    que la fila se lea sola, sin cruzar columnas;
                #  · con qué PRUEBA  → la constancia y el digest del escrito.
                "requested_by_subject": str(constancia["user_sub"]),
                "executed_by": claims.sub,
                "request_id": str(request_id),
                "request_channel": constancia["channel"],
                "request_received_at": constancia["received_at"].isoformat(),
                "proof_digest": constancia["proof_digest"],
            },
        )
    return ErasureOut(**fila)


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
