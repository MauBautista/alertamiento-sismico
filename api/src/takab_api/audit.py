"""Helper mínimo de auditoría sobre ``audit_log`` (T-1.24 lo formaliza)."""

from __future__ import annotations

import psycopg
from psycopg.types.json import Jsonb


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
    conn.execute(
        "INSERT INTO audit_log (tenant_id, actor, verb, object, meta) VALUES (%s, %s, %s, %s, %s)",
        (tenant_id, actor, verb, obj, Jsonb(meta or {})),
    )
