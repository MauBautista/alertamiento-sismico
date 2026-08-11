"""Bitácora de los comandos que NO ocurrieron (T-2.86.b · `RO-8.g` / `RO-8.k`).

Hasta aquí la superficie más sensible del sistema —la que abre válvulas de gas—
solo escribía `command_issued`: **registraba lo que salió bien y callaba lo que
se intentó**. Un atacante que sondease con comandos repetidos era invisible en
`audit_log`, que es exactamente donde se investigaría el incidente.

Este módulo es el único sitio que escribe ese rechazo, y tiene tres decisiones
dentro que conviene no deshacer sin releerlas.

## 1. Por qué fuera de banda

El request de FastAPI vive en UNA transacción (`db/session.py`). Auditar y acto
seguido lanzar el 403/409/429 hace rollback y **se lleva la fila por delante**.
Un `commit()` a media request tampoco vale: tiraría los GUCs de RLS que sostienen
el aislamiento por tenant. Igual que `audit.audit_out_of_band_async` (T-2.36), se
escribe en una conexión propia que sí commitea. Aquí no se reutiliza aquel helper
porque el conteo del presupuesto y el INSERT tienen que compartir conexión —y por
tanto contexto RLS— para que cuenten exactamente las filas que van a escribirse.

**Y con la conexión lateral se heredaba su defecto (T-2.112, medido).** El
`except Exception` de abajo decía "best-effort" pero no lo era: sin tope de espera
no hay excepción que capturar, solo una espera infinita. Con la transacción del
request abierta —y sosteniendo el ACCESS SHARE de `audit_log` en cuanto la haya
leído—, si un tercero pide entretanto el ACCESS EXCLUSIVE de la tabla (el TRUNCATE
de un teardown, un `VACUUM FULL`, una migración) la lateral se encola detrás de él
y el ciclo se cierra FUERA de PostgreSQL: request → lateral → ACCESS EXCLUSIVE →
request. El detector de interbloqueos no lo ve, porque la conexión del request no
espera un lock: está *idle in transaction*. Reproducido antes del arreglo en
`tests/api/test_rejection_audit_deadlock.py` (las dos formas se colgaban 25 s hasta
que el tope del test las cortaba; sin él, para siempre). La costura es la misma que
cerró T-2.73.c: la lateral fija `lock_timeout` y CEDE — se pierde el contador, que
queda en el log del servicio, no el 403 ni la conexión.

## 2. Por qué hay presupuesto, y por qué la última fila es una MARCA

`audit_log` es append-only (trigger `forbid_update_delete` + `REVOKE UPDATE,
DELETE`) y **nunca se poda por retención** (regla de oro 11). Una fila por intento
sin techo convierte la bitácora en el blanco: quien inunde la API llena para
siempre la tabla que sostiene el compliance. Y el techo no puede ser "una fila
agregada con un contador que se incrementa", porque eso exige UPDATE y la tabla
no lo permite —ni debe permitirlo—.

Así que: fila por intento **hasta agotar un presupuesto** por
`(tenant tocado, actor, ventana)`, y la ÚLTIMA fila del presupuesto no es un
detalle más sino la marca `audit_budget_exhausted`. De ese modo el silencio
posterior queda declarado DENTRO de la propia tabla y nadie lo lee como calma.
Cota dura: `AUDIT_BUDGET` filas por actor y ventana, pase lo que pase.

El presupuesto se lleva por **actor autenticado**, no por objeto: el `site_id` de
la URL lo elige quien ataca (espacio de UUID infinito ⇒ la cota nunca ataría),
mientras que el `sub` viene de un JWT firmado y no es rotable a voluntad.

Rechazar sigue siendo gratis e instantáneo: lo que el presupuesto acota es
cuánto se ESCRIBE, jamás la decisión de seguridad, que no cambia nunca.

## 3. Qué se considera "sabido"

Todo rechazo que llega aquí trae ya un **JWT válido** (`require_roles` corta
antes): la sesión está probada y, por el pool Cognito, respaldada por MFA. Eso es
lo que va en `actor`. Lo que puede NO estar probado es el **dispositivo**: cuando
la firma de la intención no verifica, el `key_id` que venía dentro es un dato
ofrecido por quien fue rechazado. Por eso `meta.actor_proof` distingue
`"session"` de `"session+device"`, y el `key_id` no probado se archiva bajo
`claimed_intent_key_id` — nunca se asciende a hecho.

Y no se archivan credenciales, solo el hecho (mismo criterio que T-2.36): la
firma de la intención jamás entra en claro (es un blob controlado por el
atacante, en una tabla que no se poda) y el nonce tampoco — va su SHA-256, que
permite correlacionar sondeos del mismo nonce sin guardar el token.

## 4. Bajo qué tenant se archiva

Bajo el **tocado**, no el del operador. Quien pregunta "¿quién intentó abrir MI
válvula?" es el dueño del edificio, y la política `audit_read` filtra por
`tenant_id`: archivarlo bajo el operador lo dejaría fuera de la vista de su
dueño. T-2.71 se pagó una vez por la inversión de esto.

Corolario deliberado: aquí solo se audita lo que ocurre **después de resolver el
sitio**. Antes (401 sin token, 403 de matriz de rol, 404 de sitio invisible bajo
RLS, 400 de canal/acción) el tenant tocado no es resoluble sin romper RLS, y
archivarlo bajo el del sondeador respondería una pregunta distinta de la que hace
el cliente.
"""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from takab_api.audit import LATERAL_LOCK_TIMEOUT, audit_async
from takab_api.db.session import SessionCtx, get_tenant_conn

if TYPE_CHECKING:
    from uuid import UUID

    from takab_api.auth.claims import Claims

log = logging.getLogger(__name__)

#: Verbo ÚNICO de todo rechazo de comando; el porqué va en ``meta.reason``.
#: Un solo verbo mantiene barata la consulta "¿qué se intentó contra este
#: edificio?" y hace que el presupuesto cuente todas las clases juntas.
REJECTION_VERB = "command_rejected"

#: Motivo de la última fila del presupuesto: "de aquí en adelante no escribo".
BUDGET_EXHAUSTED = "audit_budget_exhausted"

#: Filas de rechazo por (tenant tocado, actor, ventana). No es una perilla de
#: despliegue —es higiene de una tabla que no se poda—, así que vive aquí y no
#: en ``Settings``. Un operador legítimo produce rechazos aislados; 20 en cinco
#: minutos ya es un patrón, y a partir de ahí basta con saber que sigue.
AUDIT_BUDGET = 20
AUDIT_WINDOW_S = 300.0

#: Prueba de identidad detrás del intento (ver §3 del docstring).
PROOF_SESSION = "session"
PROOF_SESSION_DEVICE = "session+device"

_RECENT = text(
    "SELECT count(*) FROM audit_log "
    "WHERE tenant_id = CAST(:tenant_id AS uuid) AND verb = :verb AND actor = :actor "
    "  AND ts > now() - make_interval(secs => :window_s)"
)


def fingerprint(value: str) -> str:
    """SHA-256 hex de una credencial que NO debe archivarse en claro."""
    return hashlib.sha256(value.encode()).hexdigest()


async def audit_command_rejection(
    *,
    claims: Claims,
    tenant_id: str,
    site_id: UUID | str,
    reason: str,
    status: int,
    channel: str | None = None,
    action: str | None = None,
    actor_proof: str = PROOF_SESSION,
    extra: dict[str, Any] | None = None,
) -> None:
    """Deja constancia de UN comando rechazado. Una petición ⇒ como mucho una fila.

    ``tenant_id`` es el del sitio TOCADO. Best-effort por diseño: si la conexión
    secundaria falla, la decisión de seguridad del request no cambia — perder una
    fila de bitácora es preferible a convertir un 403 en un 500.

    [T-2.112] Ese "best-effort" ahora incluye **no esperar para siempre**: la lateral
    fija el mismo ``lock_timeout`` que ``audit.audit_out_of_band_async`` (§1 del
    docstring del módulo). El ``except`` sigue siendo ancho aquí —a diferencia del de
    ``audit.py``, que se estrechó a ``SQLAlchemyError``— porque esta ruta se invoca en
    mitad de un camino de RECHAZO: un fallo de Python en el helper no puede convertir
    un 403 en un 500. Divergencia deliberada, no descuido.
    """
    actor = f"user:{claims.sub}"
    # El contexto RLS es el del tenant TOCADO a propósito: así el conteo ve
    # exactamente las filas que este mismo helper escribe (la policy `audit_read`
    # filtra por tenant_id) y el INSERT aterriza donde su dueño lo va a buscar.
    ctx = SessionCtx(tenant_id=tenant_id, role=claims.role, user_id=claims.sub)
    try:
        async with get_tenant_conn(ctx) as conn:
            # [T-2.112] Tope de espera de la LATERAL, antes de tocar `audit_log`. Se
            # importa el de `audit.py` a propósito: es UNA sola política para las dos
            # conexiones laterales del proyecto, y dos copias derivarían en silencio.
            await conn.execute(LATERAL_LOCK_TIMEOUT)
            used = await conn.scalar(
                _RECENT,
                {
                    "tenant_id": tenant_id,
                    "verb": REJECTION_VERB,
                    "actor": actor,
                    "window_s": AUDIT_WINDOW_S,
                },
            )
            used = used or 0
            if used >= AUDIT_BUDGET:
                return  # el agotamiento ya está marcado en esta ventana
            if used == AUDIT_BUDGET - 1:
                # Última del presupuesto: se gasta en DECIR que se agotó, no en
                # un detalle más. Deliberadamente sin campos del atacante.
                meta: dict[str, Any] = {
                    "reason": BUDGET_EXHAUSTED,
                    "suppressed_reason": reason,
                    "status": status,
                    "budget": AUDIT_BUDGET,
                    "window_s": AUDIT_WINDOW_S,
                }
            else:
                meta = {"reason": reason, "status": status, "actor_proof": actor_proof}
                if channel is not None:
                    meta["channel"] = channel
                if action is not None:
                    meta["action"] = action
                if extra:
                    meta.update(extra)
            await audit_async(
                conn,
                tenant_id=tenant_id,
                actor=actor,
                verb=REJECTION_VERB,
                obj=f"site:{site_id}",
                meta=meta,
            )
    except Exception:  # noqa: BLE001 — best-effort: jamás degradar un 4xx a 500
        log.warning("no se pudo auditar el rechazo de comando (%s)", reason, exc_info=True)
