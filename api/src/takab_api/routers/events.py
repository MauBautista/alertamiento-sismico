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


# Tope del filtro por conjunto. Es el techo de "cuántos incidentes puede tener
# cargados la pantalla de evaluación a la vez"; más que eso es una consulta de
# catálogo, no un enriquecimiento de tabla.
MAX_EVENT_IDS = 200


@router.get("/events", response_model=EventPage)
async def list_events(
    conn: AsyncConnection = Depends(read_session),
    source: str | None = Query(None),
    cursor: str | None = Query(None),
    limit: int | None = Query(None),
    ids: str | None = Query(None, description="event_id separados por coma (máx. 200)"),
) -> EventPage:
    """Lista eventos sísmicos (detected_at desc) con paginación keyset estable.

    [T-2.39] Con ``ids`` devuelve EXACTAMENTE ese conjunto y el keyset se desactiva:
    la pantalla de evaluación enriquece las filas que tiene cargadas, no las 50 más
    recientes. Antes, al pasar de página, incidentes con evento existente perdían
    magnitud, epicentro y nodos sin decir por qué.
    """
    size = clamp_limit(limit)
    id_list: list[str] | None = None
    if ids is not None:
        id_list = [part.strip() for part in ids.split(",") if part.strip()]
        if len(id_list) > MAX_EVENT_IDS:
            raise http_error(422, f"demasiados event_id (máximo {MAX_EVENT_IDS})")
        if not id_list:
            return EventPage(items=[], next_cursor=None)
        size = min(len(id_list), MAX_EVENT_IDS)

    cur_ts, cur_id = (None, None)
    if cursor is not None:
        cur_ts, cur_id = decode_cursor(cursor)

    stmt, params = q.select_events(
        source=source,
        cursor_detected_at=cur_ts,
        cursor_id=cur_id,
        limit=size + 1,
        ids=id_list,
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
