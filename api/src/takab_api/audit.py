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
    """Inserta una fila append-only; ``ts``/``audit_id`` los pone la DB."""
    conn.execute(_AUDIT_SQL, (tenant_id, actor, verb, obj, Jsonb(meta or {})))


async def audit_async(
    conn: AsyncConnection,
    *,
    tenant_id: object,
    actor: str,
    verb: str,
    obj: str,
    meta: dict | None = None,
) -> None:
    """Front async (routers): misma fila, bajo la sesión RLS del request."""
    await conn.execute(
        _AUDIT_SQL_ASYNC,
        {
            "tenant_id": tenant_id,
            "actor": actor,
            "verb": verb,
            "object": obj,
            "meta": json.dumps(meta or {}),
        },
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
