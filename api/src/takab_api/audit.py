"""Auditoría inmutable — ÚNICA fuente del INSERT a ``audit_log`` (T-1.24).

Todos los servicios auditan por aquí (ingesta, exports, reports, commands,
config sync…): un solo lugar define el shape de la fila y el contract-test
``tests/contracts/test_audit_single_writer.py`` veta cualquier INSERT a
``audit_log`` fuera de este módulo. La tabla es append-only (trigger en DDL) y
NUNCA se poda por retención (blueprint §9; contract-test de compliance).

Dos frentes para los dos stacks de DB del proyecto:
- ``audit()``       — psycopg sync (workers de ingesta/backfill/config sync).
- ``audit_async()`` — SQLAlchemy async (routers FastAPI bajo RLS del request).
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import TYPE_CHECKING

import psycopg
from psycopg.types.json import Jsonb
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from takab_api.db.session import BACKGROUND_LOCK_TIMEOUT_MS, lock_timeout_stmt

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection

_log = logging.getLogger(__name__)

_AUDIT_SQL = (
    "INSERT INTO audit_log (tenant_id, actor, verb, object, meta) VALUES (%s, %s, %s, %s, %s)"
)

_AUDIT_SQL_ASYNC = text(
    "INSERT INTO audit_log (tenant_id, actor, verb, object, meta) "
    "VALUES (:tenant_id, :actor, :verb, :object, CAST(:meta AS jsonb))"
)

# --------------------------------------------------------------------------
# [T-2.138] La fila que se escribe POR ENTREGA y no por hecho
# --------------------------------------------------------------------------
#
# `T-2.136` midió los 7 caminos de la ingesta contra una reentrega real de SQS:
# 6 quedan en UNA fila (PK natural, UPSERT por `event_uuid`, guarda monotónica) y
# el séptimo —`ingest_reject`— dejaba DOS, porque `audit_log` no tiene clave
# natural. La tabla no se poda jamás (regla de oro 11), así que el renglón de más
# es permanente.
#
# El arreglo vive AQUÍ, y tiene que vivir aquí: `audit.py` es el escritor único
# de la tabla (contract-test `tests/contracts/test_audit_single_writer.py`), así
# que es el único sitio donde se puede definir la forma de la fila sin abrirle una
# excepción al veto.
#
# **Lo que NO se podía hacer:** una clave sobre `(tenant, actor, verb, object,
# meta)` colapsaría rechazos genuinamente distintos —la razón la compone el
# cross-check de identidad y se repite idéntica para mensajes distintos—, que es
# peor que duplicar uno. Por eso la clave lleva CUBETA: la huella dice "el mismo
# hecho", la cubeta lo acota a la ventana en la que una reentrega es posible.

#: Verbos cuya fila se escribe por ENTREGA y no por hecho. El censo se enumera a
#: propósito y es diminuto: ampliarlo significa aceptar perder repeticiones
#: legítimas de ese verbo, y esa decisión no se hereda sin escribirla. Un `export`
#: repetido, por ejemplo, son DOS descargas — dos hechos de compliance distintos.
DEDUPE_VERBS = frozenset({"ingest_reject"})

#: Ancho de la cubeta, en segundos = **horizonte de reentrega de SQS**:
#: `maxReceiveCount (5) × VisibilityTimeout de la peor cola que consume la ingesta
#: (q-telemetry, 90 s)`. No es un número elegido: lo ata al Terraform REAL el test
#: `tests/test_audit_reentrega.py::test_la_ventana_se_deriva_del_terraform_real…`,
#: que cae si alguien mueve la visibilidad o el maxReceiveCount.
#:
#: **Por qué cubeta y no reloj.** Comparar contra `ts > now() - ventana` obliga a
#: leer por `ts` y deja el veredicto a merced de qué fila se vea; comparar cubetas
#: usa el MISMO índice que impone la unicidad. Se mira la cubeta actual y la
#: ANTERIOR, y ahí desaparece el agujero de borde: dos entregas separadas menos
#: que el ancho caen siempre en la misma cubeta o en la contigua. El precio,
#: declarado: la ventana efectiva está entre una y dos veces el ancho — nunca
#: menos que el horizonte de reentrega, nunca más del doble.
VENTANA_REENTREGA_S = 450

#: Comprobación previa + respaldo físico, en una sentencia. La lectura resuelve el
#: caso normal (reentrega tras vencer la visibilidad, con la fila anterior ya
#: commiteada); el `ON CONFLICT` resuelve el que la lectura NO puede ver: dos
#: entregas CONCURRENTES —el modo de fallo que abrió `T-2.136`, una consulta que
#: se pasa del `VisibilityTimeout`— corren en transacciones distintas y ninguna ve
#: la fila de la otra hasta el commit. El índice sí.
_AUDIT_SQL_DEDUPE = """
INSERT INTO audit_log (tenant_id, actor, verb, object, meta, dedupe_digest, dedupe_bucket)
SELECT %s, %s, %s, %s, %s, %s, c.cubeta
  FROM (SELECT floor(EXTRACT(EPOCH FROM clock_timestamp()) / %s)::bigint AS cubeta) c
 WHERE NOT EXISTS (
         SELECT 1 FROM audit_log a
          WHERE a.dedupe_digest = %s AND a.dedupe_bucket >= c.cubeta - 1)
ON CONFLICT (dedupe_digest, dedupe_bucket) WHERE dedupe_digest IS NOT NULL DO NOTHING
"""

_AUDIT_SQL_DEDUPE_ASYNC = text(
    "INSERT INTO audit_log "
    "  (tenant_id, actor, verb, object, meta, dedupe_digest, dedupe_bucket) "
    "SELECT :tenant_id, :actor, :verb, :object, CAST(:meta AS jsonb), :digest, c.cubeta "
    "  FROM (SELECT floor(EXTRACT(EPOCH FROM clock_timestamp()) / :ventana)::bigint AS cubeta) c "
    " WHERE NOT EXISTS ("
    "         SELECT 1 FROM audit_log a "
    "          WHERE a.dedupe_digest = :digest AND a.dedupe_bucket >= c.cubeta - 1) "
    "ON CONFLICT (dedupe_digest, dedupe_bucket) WHERE dedupe_digest IS NOT NULL DO NOTHING"
)


def dedupe_digest_for(
    *,
    tenant_id: object,
    actor: str,
    verb: str,
    obj: str,
    meta: dict | None,
) -> str | None:
    """Huella del HECHO auditado, o ``None`` si el verbo no es de reentrega.

    Se calcula sobre la fila entera y canonizada (claves ordenadas), que es todo
    lo que llega hasta aquí. **Lo que esta huella NO puede distinguir, dicho en
    voz alta:** dos mensajes DISTINTOS cuya evidencia salga byte-idéntica dentro
    de la ventana se cuentan como uno, porque la fila no lleva id del mensaje —
    eso se queda en `ingest/handlers.py` y nunca cruza esta frontera. Si algún día
    hace falta CONTAR rechazos repetidos, lo que tiene que viajar es el id del
    mensaje; aflojar la clave devolvería el renglón permanente de `T-2.136`.
    """
    if verb not in DEDUPE_VERBS:
        return None
    canonico = json.dumps(
        {
            "tenant_id": None if tenant_id is None else str(tenant_id),
            "actor": actor,
            "verb": verb,
            "object": obj,
            "meta": meta or {},
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


# Tope de espera por un lock en una conexión de SEGUNDO PLANO.
#
# [T-2.130] **El número ya no se declara aquí**: la política —los dos escalones,
# request y segundo plano— vive en ``db/session.py``, que es donde se abre la
# conexión que la aplica. Esto son alias, y se conservan porque los importan por su
# nombre ``commands/rejection_audit.py`` (T-2.112) y los tests de T-2.121; el número
# es el mismo objeto, así que las dos políticas no pueden derivar por construcción.
#
# Consumidores del escalón de segundo plano hoy:
#   · ``audit_out_of_band_async`` (aquí)
#   · ``audit_command_rejection``  (``commands/rejection_audit.py``, T-2.112)
#   · el hub del WebSocket         (``ws/hub.py``, T-2.121)
#   · el poller                    (``ws/poller.py``, T-2.121)
#
# Por qué existe (T-2.73.c): la conexión del request ya leyó ``audit_log`` y sostiene
# su ACCESS SHARE mientras Python espera a la lateral. Si alguien pide entretanto el
# ACCESS EXCLUSIVE de la tabla (un ``TRUNCATE`` de teardown, un ``VACUUM FULL``, una
# migración), la lateral se encola DETRÁS de él y el ciclo se cierra por fuera de
# PostgreSQL: request → lateral → ACCESS EXCLUSIVE → request. El detector de
# interbloqueos no lo ve —la conexión del request está *idle*, no esperando un lock—
# así que sin este tope la espera es literalmente para siempre.
LATERAL_LOCK_TIMEOUT_MS = BACKGROUND_LOCK_TIMEOUT_MS
LATERAL_LOCK_TIMEOUT = lock_timeout_stmt(BACKGROUND_LOCK_TIMEOUT_MS)


def audit(
    conn: psycopg.Connection,
    *,
    tenant_id: str | None,
    actor: str,
    verb: str,
    obj: str,
    meta: dict | None = None,
) -> None:
    """Inserta una fila append-only; ``ts``/``audit_id`` los pone la DB.

    [T-2.138] Para los verbos de ``DEDUPE_VERBS`` la fila lleva clave de
    reentrega y la segunda entrega del MISMO hecho no escribe.
    """
    digest = dedupe_digest_for(tenant_id=tenant_id, actor=actor, verb=verb, obj=obj, meta=meta)
    if digest is None:
        conn.execute(_AUDIT_SQL, (tenant_id, actor, verb, obj, Jsonb(meta or {})))
        return
    conn.execute(
        _AUDIT_SQL_DEDUPE,
        (
            tenant_id,
            actor,
            verb,
            obj,
            Jsonb(meta or {}),
            digest,
            VENTANA_REENTREGA_S,
            digest,
        ),
    )


async def audit_async(
    conn: AsyncConnection,
    *,
    tenant_id: object,
    actor: str,
    verb: str,
    obj: str,
    meta: dict | None = None,
) -> None:
    """Front async (routers): misma fila, bajo la sesión RLS del request.

    [T-2.138] La clave de reentrega se calcula con el MISMO helper que el front
    sync: los dos frentes escriben la misma fila o el veto del escritor único
    sería decorativo. Hoy ningún verbo de ``DEDUPE_VERBS`` entra por aquí (la
    ingesta es sync); el día que entre, se comportará igual sin tocar nada.
    """
    digest = dedupe_digest_for(tenant_id=tenant_id, actor=actor, verb=verb, obj=obj, meta=meta)
    params = {
        "tenant_id": tenant_id,
        "actor": actor,
        "verb": verb,
        "object": obj,
        "meta": json.dumps(meta or {}),
    }
    if digest is None:
        await conn.execute(_AUDIT_SQL_ASYNC, params)
        return
    await conn.execute(
        _AUDIT_SQL_DEDUPE_ASYNC,
        {**params, "digest": digest, "ventana": VENTANA_REENTREGA_S},
    )


async def audit_out_of_band_async(
    ctx: object,
    *,
    tenant_id: object,
    actor: str,
    verb: str,
    obj: str,
    meta: dict | None = None,
) -> None:
    """Audita en una conexión PROPIA que sí commitea (T-2.36).

    Existe por un caso concreto: el registro de un intento FALLIDO. El request de
    FastAPI vive en una sola transacción (``db/session.py``), así que auditar y acto
    seguido lanzar el 403 hace rollback y **se lleva la fila de auditoría por
    delante** — el contador de rate-limit nunca armaría y el bloqueo por intentos
    sería decorativo. Un ``commit()`` a media request tampoco vale: tiraría los GUCs
    de RLS que sostienen el aislamiento por tenant.

    ``ctx`` es un ``db.session.SessionCtx`` (se recibe sin tipar para no importar el
    módulo de sesión desde aquí y crear un ciclo). Best-effort por diseño: si la
    conexión secundaria falla, la decisión de seguridad del request no cambia — solo
    se pierde el contador, y eso es preferible a convertir un 403 en un 500.

    Ese "best-effort" estaba escrito pero no implementado (T-2.73.c): sin tope de
    espera ni captura, una lateral encolada tras un ACCESS EXCLUSIVE de ``audit_log``
    colgaba el request **para siempre** y dejaba la conexión del request en
    ``idle in transaction``, bloqueando a su vez a quien pidió el lock. Ahora la
    lateral espera un máximo acotado y, si no puede escribir, cede: se pierde el
    contador (queda en el log del servicio), no el 403 ni la conexión.
    """
    from takab_api.db.session import get_tenant_conn  # local: evita ciclo de imports

    try:
        async with get_tenant_conn(ctx) as conn:  # type: ignore[arg-type]
            await conn.execute(LATERAL_LOCK_TIMEOUT)
            await audit_async(conn, tenant_id=tenant_id, actor=actor, verb=verb, obj=obj, meta=meta)
    except SQLAlchemyError:
        # Solo fallos de la BASE: un error de Python (contrato roto del helper) debe
        # seguir siendo ruidoso, o el veto del contract-test se volvería decorativo.
        _log.warning(
            "auditoría fuera de banda perdida: verb=%s object=%s tenant=%s",
            verb,
            obj,
            tenant_id,
            exc_info=True,
        )
