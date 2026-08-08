"""T-2.79 · Resolución del aviso vigente y registro append-only del consentimiento.

QUÉ AVISO APLICA (decisión: plataforma **y** tenant, gana el más específico)
───────────────────────────────────────────────────────────────────────────────
TAKAB se vende a Protección Civil, gobierno y empresas. Bajo la LFPDPPP el
*responsable* de los datos de una persona es quien decide sobre su tratamiento,
y para los ocupantes de un hospital ese responsable es **el hospital**, no TAKAB:
un cliente tiene que poder publicar SU aviso. Pero exigirlo antes de operar
dejaría a todo cliente nuevo sin ningún aviso que mostrar el primer día, que es
peor que mostrar el de la plataforma.

Así que hay dos orígenes y una regla de desempate sin ambigüedad:

* **tenant** — fila de ``privacy_notices``. Gana siempre que exista una vigente.
* **plataforma** — artefacto del repo (``texts/*.json``). Es el caso por defecto.

"Vigente" es un PREDICADO, no una columna: la fila de mayor ``effective_at`` que
ya pasó, desempatando por ``seq`` (orden total de publicación). Sin worker de
rotación — la pregunta "¿y si el job muere?" se contesta borrando el job.

La respuesta SIEMPRE dice de dónde salió (``source``). Un aviso sin origen
declarado no se puede auditar: "acepté el aviso" no significa lo mismo si el
texto lo puso el hospital que si lo puso la plataforma.

QUÉ PASA CUANDO EL AVISO CAMBIA (decisión: se vuelve a pedir, NO se bloquea)
───────────────────────────────────────────────────────────────────────────────
El estado del consentimiento es una función de dos cosas: el digest vigente y el
digest sellado en la última decisión del sujeto. ``stale`` significa "aceptó,
pero otro texto". Lo que el sistema hace con ``stale`` es **pedirlo otra vez en
un momento tranquilo**, y nada más.

**Dónde NO puede bloquear, y por qué es una decisión de seguridad y no de
cumplimiento.** En una emergencia sísmica, un brigadista que no puede hacer
check-in porque hay un aviso nuevo pendiente de aceptar es un fallo de
seguridad. Las reglas de oro 1 y 2 lo cierran por arriba —el camino
SASMEX→actuador vive en el gabinete y no depende de la nube, así que ni se
entera de que este módulo existe— pero en la nube hay que ser explícito:

* **jamás gatea** el check-in de vida, el botón de ayuda, el reporte de daños,
  la alerta en pantalla ni el voceo. Ninguna de esas rutas importa este módulo,
  y hay un test que lo comprueba insertando el estado peor (sin consentimiento
  ninguno) y exigiendo que el check-in siga dando 201;
* lo único que hace un ``stale``/``missing`` es **encender un aviso no
  bloqueante** en la app y en la consola.

Y al revés: nada de esto es excusa para no registrar. El acto queda con su
instante, su digest y su vía, que es lo que lo hace probable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.privacy.artifacts import NoticeSpec, get_catalog

#: Estados que la UI tiene que saber pintar (regla de oro 7 en la capa de datos:
#: el `stale` no es un adorno del front, es un estado que el servidor declara).
MISSING = "missing"
CURRENT = "current"
STALE = "stale"
WITHDRAWN = "withdrawn"

DEFAULT_LOCALE = "es-MX"

_SELECT_NOTICE = text(
    "SELECT notice_id, purpose, locale, version, title, body, digest, "
    "       effective_at, published_at, published_by "
    "FROM privacy_notices "
    "WHERE tenant_id = CAST(:tenant AS uuid) AND purpose = :purpose AND locale = :locale "
    "  AND effective_at <= now() "
    "ORDER BY effective_at DESC, seq DESC LIMIT 1"
)

# La última decisión del sujeto. `subject_ref` y no `user_sub` para que la misma
# consulta sirva a una persona y a un número de teléfono (costura T-2.77).
_SELECT_CONSENT = text(
    "SELECT consent_id, decision, notice_source, notice_id, notice_digest, "
    "       notice_version, notice_locale, via, actor_sub, decided_at "
    "FROM privacy_consents "
    "WHERE tenant_id = CAST(:tenant AS uuid) AND purpose = :purpose "
    "  AND subject_ref = :subject "
    "ORDER BY decided_at DESC, consent_id DESC LIMIT 1"
)

_HISTORY = text(
    "SELECT consent_id, decision, notice_source, notice_id, notice_digest, "
    "       notice_version, notice_locale, via, actor_sub, decided_at "
    "FROM privacy_consents "
    "WHERE tenant_id = CAST(:tenant AS uuid) AND purpose = :purpose "
    "  AND subject_ref = :subject "
    "ORDER BY decided_at DESC, consent_id DESC LIMIT :limit"
)

_INSERT_CONSENT = text(
    "INSERT INTO privacy_consents "
    "(tenant_id, purpose, subject_kind, user_sub, subject_ref, decision, notice_source, "
    " notice_id, notice_digest, notice_version, notice_locale, via, actor_sub) "
    "VALUES (CAST(:tenant AS uuid), :purpose, :subject_kind, CAST(:user AS uuid), :subject, "
    " :decision, :source, CAST(:notice AS uuid), :digest, :version, :locale, :via, "
    " CAST(:actor AS uuid)) "
    "RETURNING consent_id, decided_at"
)

_INSERT_NOTICE = text(
    "INSERT INTO privacy_notices "
    "(tenant_id, purpose, locale, version, title, body, effective_at, published_by) "
    "VALUES (CAST(:tenant AS uuid), :purpose, :locale, :version, :title, :body, "
    " COALESCE(CAST(:effective AS timestamptz), now()), CAST(:by AS uuid)) "
    "RETURNING notice_id, digest, version, effective_at, published_at"
)


@dataclass(frozen=True)
class ResolvedNotice:
    """El aviso que aplica AHORA a un sujeto, con su origen declarado."""

    purpose: str
    locale: str
    version: str
    title: str
    body: str
    digest: str
    source: str  # 'repo' (plataforma) | 'tenant'
    notice_id: str | None
    provisional: bool
    provisional_reason: str
    effective_at: datetime | None

    @property
    def paragraphs(self) -> tuple[str, ...]:
        """El cuerpo partido en párrafos. NO hay resumen aparte a propósito: un
        resumen que se enseña pero no se sella deja consentir un texto distinto
        del que se leyó."""
        return tuple(p.strip() for p in self.body.split("\n\n") if p.strip())


def _from_spec(spec: NoticeSpec) -> ResolvedNotice:
    return ResolvedNotice(
        purpose=spec.purpose,
        locale=spec.locale,
        version=spec.version,
        title=spec.title,
        body=spec.body,
        digest=spec.digest,
        source="repo",
        notice_id=None,
        provisional=spec.provisional,
        provisional_reason=spec.provisional_reason,
        effective_at=None,
    )


def _from_row(row: Any, purpose: str) -> ResolvedNotice:
    return ResolvedNotice(
        purpose=purpose,
        locale=row["locale"],
        version=row["version"],
        title=row["title"],
        body=row["body"],
        digest=row["digest"],
        source="tenant",
        notice_id=str(row["notice_id"]),
        # Un aviso publicado por el cliente NO lo revisa LEGAL de TAKAB: lo firma
        # el responsable de esos datos, que es quien lo publica. Marcarlo
        # "provisional" sería afirmar algo sobre un texto ajeno que no sabemos.
        provisional=False,
        provisional_reason="",
        effective_at=row["effective_at"],
    )


async def current_notice(
    conn: AsyncConnection, *, tenant_id: str, purpose: str, locale: str = DEFAULT_LOCALE
) -> ResolvedNotice | None:
    """El aviso vigente: el del tenant si lo hay, si no el de plataforma.

    ``None`` solo si NINGUNO existe (ni fila ni artefacto legible para ese
    propósito y locale). Es un estado real —`empty` en la UI— y no se disfraza
    con un texto de relleno: mostrar un aviso inventado es peor que no mostrar
    ninguno, porque el consentimiento se daría sobre algo que nadie escribió.
    """
    fila = (
        (
            await conn.execute(
                _SELECT_NOTICE, {"tenant": tenant_id, "purpose": purpose, "locale": locale}
            )
        )
        .mappings()
        .one_or_none()
    )
    if fila is not None:
        return _from_row(fila, purpose)
    spec = get_catalog().get(purpose, locale)
    return _from_spec(spec) if spec is not None else None


async def latest_consent(
    conn: AsyncConnection, *, tenant_id: str, purpose: str, subject_ref: str
) -> Any:
    """La ÚLTIMA decisión del sujeto (aceptar o retirar), o ``None``.

    El estado se DERIVA del registro append-only; no hay columna "vigente" que
    alguien tenga que acordarse de actualizar (mismo criterio que ``drills`` y
    ``maintenance_windows``).
    """
    return (
        (
            await conn.execute(
                _SELECT_CONSENT,
                {"tenant": tenant_id, "purpose": purpose, "subject": subject_ref},
            )
        )
        .mappings()
        .one_or_none()
    )


async def consent_history(
    conn: AsyncConnection, *, tenant_id: str, purpose: str, subject_ref: str, limit: int = 20
) -> list[Any]:
    """El historial completo, del más reciente al más antiguo.

    Existe porque el registro append-only solo vale si se puede LEER: "acepté la
    v1, la retiré, volví a aceptar la v2" es la respuesta a una reclamación, y
    quedarse con la última fila la haría irrespondible.
    """
    return list(
        (
            await conn.execute(
                _HISTORY,
                {
                    "tenant": tenant_id,
                    "purpose": purpose,
                    "subject": subject_ref,
                    "limit": max(1, min(limit, 200)),
                },
            )
        )
        .mappings()
        .all()
    )


def consent_state(notice: ResolvedNotice | None, consent: Any) -> str:
    """El estado, como función de (texto vigente, última decisión).

    Cuatro salidas y ninguna ambigua:

    * ``missing``   — nunca decidió nada;
    * ``withdrawn`` — la última decisión fue retirar (aunque el texto no cambie);
    * ``current``   — aceptó **este** texto (digest a digest);
    * ``stale``     — aceptó, pero **otro** texto. Este es el caso que un diseño
      por número de versión no puede ver.

    Ojo con el orden: ``withdrawn`` se decide ANTES de comparar digests. Si se
    comparara primero, retirar el consentimiento sobre el texto vigente saldría
    como ``current`` y el sistema afirmaría que hay consentimiento donde el
    sujeto dijo que no.
    """
    if consent is None:
        return MISSING
    if consent["decision"] == "withdraw":
        return WITHDRAWN
    if notice is None:
        return STALE
    return CURRENT if consent["notice_digest"] == notice.digest else STALE


async def record_consent(
    conn: AsyncConnection,
    *,
    tenant_id: str,
    purpose: str,
    notice: ResolvedNotice,
    decision: str,
    via: str,
    actor_sub: str,
    user_sub: str | None = None,
    msisdn: str | None = None,
) -> Any:
    """Escribe UNA fila. Nunca actualiza: retirar y volver a aceptar son filas.

    ``notice_digest`` se copia del aviso que se resolvió en ESTA petición, que
    es el que el cliente acaba de leer. Derivarlo después por JOIN convertiría
    cada edición del aviso en una reescritura silenciosa del pasado.
    """
    es_usuario = msisdn is None
    return (
        (
            await conn.execute(
                _INSERT_CONSENT,
                {
                    "tenant": tenant_id,
                    "purpose": purpose,
                    "subject_kind": "user" if es_usuario else "msisdn",
                    "user": user_sub if es_usuario else None,
                    "subject": user_sub if es_usuario else msisdn,
                    "decision": decision,
                    "source": notice.source,
                    "notice": notice.notice_id,
                    "digest": notice.digest,
                    "version": notice.version,
                    "locale": notice.locale,
                    "via": via,
                    "actor": actor_sub,
                },
            )
        )
        .mappings()
        .one()
    )


async def publish_notice(
    conn: AsyncConnection,
    *,
    tenant_id: str,
    purpose: str,
    locale: str,
    version: str,
    title: str,
    body: str,
    published_by: str,
    effective_at: datetime | None = None,
) -> Any:
    """Publica el aviso del TENANT. No hay `update_notice` y no lo habrá.

    El índice único sobre el digest rechaza republicar el mismo texto con otra
    etiqueta (no es una versión), y el índice único sobre la etiqueta rechaza
    reutilizarla para otro texto (sería una versión que miente).
    """
    return (
        (
            await conn.execute(
                _INSERT_NOTICE,
                {
                    "tenant": tenant_id,
                    "purpose": purpose,
                    "locale": locale,
                    "version": version,
                    "title": title,
                    "body": body,
                    "effective": effective_at,
                    "by": published_by,
                },
            )
        )
        .mappings()
        .one()
    )


# ---------------------------------------------------------------------------
# COSTURA T-2.77 · el opt-in de WhatsApp, leído del motor y no del rule_set
# ---------------------------------------------------------------------------

_OPT_IN = text(
    "SELECT decision, decided_at FROM privacy_consents "
    "WHERE tenant_id = CAST(:tenant AS uuid) AND purpose = 'whatsapp_alerts' "
    "  AND subject_kind = 'msisdn' AND subject_ref = :msisdn "
    "ORDER BY decided_at DESC, consent_id DESC LIMIT 1"
)


async def whatsapp_opt_in_at(
    conn: AsyncConnection, *, tenant_id: str, msisdn: str
) -> datetime | None:
    """Instante del opt-in VIGENTE de un número, o ``None`` si no lo hay.

    Es el reemplazo exacto de ``notifications.whatsapp.opt_in.at`` del
    ``rule_set``, que T-2.77 puso como parche declarándolo así: *"cuando T-2.79
    exista, este canal debe leerlo de ahí en vez de del rule_set"*. La diferencia
    no es cosmética: el ``rule_set`` guarda un instante suelto que cualquiera
    puede teclear y que no dice sobre qué texto se consintió ni quién lo
    registró; esto devuelve el instante de una fila append-only con su digest,
    su vía y su actor.

    ``withdraw`` devuelve ``None``: retirado el consentimiento, no hay opt-in —
    y el provider ya se niega a enviar sin él (``notify_failed``, rojo en la
    consola), que es el comportamiento correcto y no cambia.

    **El interruptor todavía no está puesto** y es deliberado: hoy el destino se
    arma en ``notify/config.resolve_destinations``, que es una función PURA sobre
    el ``rule_set`` y no tiene conexión a la base. Enchufarla aquí obliga a mover
    la construcción del destino al orquestador, que es superficie de T-2.77 y
    tiene su propia ficha (``T-2.77.b``). Ver el comentario en ``notify/config.py``.
    """
    fila = (
        (await conn.execute(_OPT_IN, {"tenant": tenant_id, "msisdn": msisdn}))
        .mappings()
        .one_or_none()
    )
    if fila is None or fila["decision"] != "accept":
        return None
    return fila["decided_at"]


# [T-2.80] Aquí vivía `audit_meta()`: declarada, nunca llamada y además
# incompatible con su consumidor (devolvía `str` vía `json.dumps` mientras
# `audit_async` espera `meta: dict | None`). El router escribió su propio
# `_meta` en `routers/privacy.py` y esta quedó huérfana. Se borra en vez de
# "arreglarse": el único `meta` de privacidad es el del router.
