"""Routers de eventos sísmicos (T-1.22 · B2): datos DE RED.

``seismic_events``/``quorum_votes`` los lee cualquier usuario autenticado (RLS =
``app_role() IS NOT NULL``); no hay filtro por tenant. El detalle incluye los votos
de quórum con su ``delta_s`` por sensor/estación.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.queries import events as q
from takab_api.routers._common import (
    clamp_limit,
    decode_cursor,
    encode_cursor,
    http_error,
    read_session,
)
from takab_api.schemas.events import (
    EventDetailOut,
    EventPage,
    QuorumVoteOut,
    SeismicEventOut,
)

router = APIRouter()


@router.get("/events", response_model=EventPage)
async def list_events(
    conn: AsyncConnection = Depends(read_session),
    source: str | None = Query(None),
    cursor: str | None = Query(None),
    limit: int | None = Query(None),
) -> EventPage:
    """Lista eventos sísmicos (detected_at desc) con paginación keyset estable."""
    size = clamp_limit(limit)
    cur_ts, cur_id = (None, None)
    if cursor is not None:
        cur_ts, cur_id = decode_cursor(cursor)

    stmt, params = q.select_events(
        source=source, cursor_detected_at=cur_ts, cursor_id=cur_id, limit=size + 1
    )
    rows = (await conn.execute(stmt, params)).mappings().all()

    next_cursor = None
    if len(rows) > size:
        rows = rows[:size]
        last = rows[-1]
        next_cursor = encode_cursor(last["detected_at"].isoformat(), str(last["event_id"]))

    return EventPage(items=[SeismicEventOut(**dict(r)) for r in rows], next_cursor=next_cursor)


@router.get("/events/{event_id}", response_model=EventDetailOut)
async def get_event(
    event_id: str,
    conn: AsyncConnection = Depends(read_session),
) -> EventDetailOut:
    """Detalle del evento + sus votos de quórum. 404 si el evento no existe."""
    stmt, params = q.select_event(event_id)
    row = (await conn.execute(stmt, params)).mappings().first()
    if row is None:
        raise http_error(404, "evento no encontrado")

    votes_stmt, votes_params = q.select_quorum_votes(event_id)
    votes = (await conn.execute(votes_stmt, votes_params)).mappings().all()
    return EventDetailOut(**dict(row), quorum_votes=[QuorumVoteOut(**dict(v)) for v in votes])
