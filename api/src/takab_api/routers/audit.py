"""Lectura del audit trail (T-1.57): ``GET /audit`` keyset, solo lectura.

Cerraba la deuda anotada en T-1.29 («audit_log NO tiene endpoint de lectura»).
La RLS ``audit_read`` acota QUÉ filas ve cada rol (tenant propio o interno;
``tenant_id NULL`` solo internos); la acción ``read_audit`` de la matriz decide
QUIÉN entra al endpoint — el router deriva los roles de ella, jamás los lista a
mano. La ESCRITURA no existe aquí: el único escritor es ``takab_api.audit``
(contract-test single-writer) y la tabla es append-only por trigger.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.auth.deps import require_roles
from takab_api.auth.matrix import roles_with_action
from takab_api.queries.audit import select_audit
from takab_api.routers._common import (
    clamp_limit,
    decode_cursor,
    encode_cursor,
    parse_range_filters,
    read_session,
)
from takab_api.schemas.audit import AuditPage, AuditRowOut

AUDIT_ROLES: tuple[str, ...] = roles_with_action("read_audit")

router = APIRouter(dependencies=[Depends(require_roles(*AUDIT_ROLES))])


@router.get("/audit", response_model=AuditPage)
async def list_audit(
    conn: AsyncConnection = Depends(read_session),
    actor: str | None = Query(None),
    verb: str | None = Query(None),
    object_prefix: str | None = Query(None, alias="object"),
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    cursor: str | None = Query(None),
    limit: int | None = Query(None),
) -> AuditPage:
    """Audit trail (ts desc) con filtros exactos (actor/verb), prefijo (object)
    y rango de fechas; paginación keyset estable."""
    from_ts, to_ts = parse_range_filters(from_, to)
    size = clamp_limit(limit)
    cur_ts, cur_id = (None, None)
    if cursor is not None:
        cur_ts, cur_id = decode_cursor(cursor)

    stmt, params = select_audit(
        actor=actor,
        verb=verb,
        object_prefix=object_prefix,
        from_ts=from_ts,
        to_ts=to_ts,
        cursor_ts=cur_ts,
        cursor_id=cur_id,
        limit=size + 1,
    )
    rows = (await conn.execute(stmt, params)).mappings().all()

    next_cursor = None
    if len(rows) > size:
        rows = rows[:size]
        last = rows[-1]
        next_cursor = encode_cursor(last["ts"].isoformat(), str(last["audit_id"]))

    return AuditPage(items=[AuditRowOut(**dict(r)) for r in rows], next_cursor=next_cursor)
