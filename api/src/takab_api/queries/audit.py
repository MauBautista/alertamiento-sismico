"""SQL de lectura de ``audit_log`` (T-1.57). SOLO SELECT.

El único ESCRITOR de audit_log es ``takab_api.audit`` (contract-test
single-writer); aquí vive exclusivamente la lectura. RLS ``audit_read`` acota:
tenant propio o rol interno; las filas de plataforma (``tenant_id NULL``) solo
las ven los internos. Keyset sobre ``(ts, audit_id)`` descendente — mismo patrón
que ``queries/incidents`` (estable ante inserciones, sin OFFSET); ``audit_id``
es bigint identity, el cursor lo transporta como texto.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import TextClause, text

_COLS = "audit_id, ts, tenant_id, actor, verb, object, meta"


def select_audit(
    *,
    actor: str | None,
    verb: str | None,
    object_prefix: str | None,
    from_ts: datetime | None,
    to_ts: datetime | None,
    cursor_ts: str | None,
    cursor_id: str | None,
    limit: int,
) -> tuple[TextClause, dict[str, Any]]:
    """Lista keyset del audit trail con filtros opcionales. Pide ``limit`` filas."""
    where: list[str] = []
    params: dict[str, Any] = {"limit": limit}
    if actor is not None:
        where.append("actor = :actor")
        params["actor"] = actor
    if verb is not None:
        where.append("verb = :verb")
        params["verb"] = verb
    if object_prefix is not None:
        where.append("starts_with(object, :obj)")
        params["obj"] = object_prefix
    if from_ts is not None:
        where.append("ts >= :from_ts")
        params["from_ts"] = from_ts
    if to_ts is not None:
        where.append("ts < :to_ts")
        params["to_ts"] = to_ts
    if cursor_ts is not None and cursor_id is not None:
        where.append("(ts, audit_id) < (CAST(:cur_ts AS timestamptz), CAST(:cur_id AS bigint))")
        params["cur_ts"] = cursor_ts
        params["cur_id"] = cursor_id
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    sql = f"SELECT {_COLS} FROM audit_log{clause} ORDER BY ts DESC, audit_id DESC LIMIT :limit"
    return text(sql), params
