"""Routers de lectura de incidentes (T-1.22 · B2): lista keyset, detalle, timeline.

Roles con acceso = quienes tienen la Consola C4I en RBAC §2 (la matriz de rutas es
la fuente única). El acuse (POST /incidents/{id}/ack) vive en ``incidents_ack``; aquí
solo lectura. RLS acota por tenant en cada consulta.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.auth.deps import require_roles
from takab_api.auth.matrix import CONSOLE, ROLE_ROUTE_MATRIX
from takab_api.queries import incidents as q
from takab_api.routers._common import (
    clamp_limit,
    decode_cursor,
    encode_cursor,
    http_error,
    read_session,
)
from takab_api.schemas.incidents import IncidentActionOut, IncidentOut, IncidentPage

# Roles con Consola C4I (celda ≠ "—" en RBAC §2), derivados de la matriz de rutas.
CONSOLE_ROLES: tuple[str, ...] = tuple(
    sorted(r for r, routes in ROLE_ROUTE_MATRIX.items() if CONSOLE in routes)
)

_VALID_STATE = frozenset({"open", "acked", "in_review", "closed"})
_VALID_SEVERITY = frozenset({"info", "watch", "warning", "critical"})

_require_console = require_roles(*CONSOLE_ROLES)

router = APIRouter(dependencies=[Depends(_require_console)])


@router.get("/incidents", response_model=IncidentPage)
async def list_incidents(
    conn: AsyncConnection = Depends(read_session),
    state: str | None = Query(None),
    severity: str | None = Query(None),
    site_id: str | None = Query(None),
    q_prefix: str | None = Query(None, alias="q"),
    cursor: str | None = Query(None),
    limit: int | None = Query(None),
) -> IncidentPage:
    """Lista incidentes (opened_at desc) con filtros y paginación keyset estable."""
    if state is not None and state not in _VALID_STATE:
        raise http_error(400, "state inválido")
    if severity is not None and severity not in _VALID_SEVERITY:
        raise http_error(400, "severity inválido")

    size = clamp_limit(limit)
    cur_ts, cur_id = (None, None)
    if cursor is not None:
        cur_ts, cur_id = decode_cursor(cursor)

    stmt, params = q.select_incidents(
        state=state,
        severity=severity,
        site_id=site_id,
        q=q_prefix,
        cursor_opened_at=cur_ts,
        cursor_id=cur_id,
        limit=size + 1,
    )
    rows = (await conn.execute(stmt, params)).mappings().all()

    next_cursor = None
    if len(rows) > size:
        rows = rows[:size]
        last = rows[-1]
        next_cursor = encode_cursor(last["opened_at"].isoformat(), str(last["incident_id"]))

    return IncidentPage(items=[IncidentOut(**dict(r)) for r in rows], next_cursor=next_cursor)


@router.get("/incidents/{incident_id}", response_model=IncidentOut)
async def get_incident(
    incident_id: UUID,
    conn: AsyncConnection = Depends(read_session),
) -> IncidentOut:
    """Detalle de un incidente. 404 si no existe o no es visible por RLS."""
    stmt, params = q.select_incident(str(incident_id))
    row = (await conn.execute(stmt, params)).mappings().first()
    if row is None:
        raise http_error(404, "incidente no encontrado")
    return IncidentOut(**dict(row))


@router.get("/incidents/{incident_id}/actions", response_model=list[IncidentActionOut])
async def list_incident_actions(
    incident_id: UUID,
    conn: AsyncConnection = Depends(read_session),
) -> list[IncidentActionOut]:
    """Timeline append-only del incidente. 404 si el incidente no es visible."""
    exists_stmt, exists_params = q.incident_exists(str(incident_id))
    if (await conn.execute(exists_stmt, exists_params)).first() is None:
        raise http_error(404, "incidente no encontrado")
    stmt, params = q.select_incident_actions(str(incident_id))
    rows = (await conn.execute(stmt, params)).mappings().all()
    return [IncidentActionOut(**dict(r)) for r in rows]
