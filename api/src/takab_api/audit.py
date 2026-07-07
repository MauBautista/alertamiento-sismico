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
from typing import TYPE_CHECKING

import psycopg
from psycopg.types.json import Jsonb
from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection

_AUDIT_SQL = (
    "INSERT INTO audit_log (tenant_id, actor, verb, object, meta) VALUES (%s, %s, %s, %s, %s)"
)

_AUDIT_SQL_ASYNC = text(
    "INSERT INTO audit_log (tenant_id, actor, verb, object, meta) "
    "VALUES (:tenant_id, :actor, :verb, :object, CAST(:meta AS jsonb))"
)


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
