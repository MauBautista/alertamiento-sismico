"""SQL de eventos sísmicos y votos de quórum (T-1.22 · B2).

``seismic_events``/``quorum_votes`` son datos DE RED: su RLS es
``app_role() IS NOT NULL`` (cualquier usuario autenticado lee). El epicentro
``geography`` se aplana a lon/lat. Keyset sobre ``(detected_at, event_id)`` desc.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import TextClause, text

_COLS = (
    "event_id, source, magnitude, "
    "ST_X(epicenter::geometry) AS epicenter_lon, "
    "ST_Y(epicenter::geometry) AS epicenter_lat, "
    "depth_km, detected_at, meta"
)


def select_events(
    *,
    source: str | None,
    cursor_detected_at: str | None,
    cursor_id: str | None,
    limit: int,
) -> tuple[TextClause, dict[str, Any]]:
    """Lista keyset de eventos sísmicos, opcionalmente filtrada por ``source``."""
    where: list[str] = []
    params: dict[str, Any] = {"limit": limit}
    if source is not None:
        where.append("source = :source")
        params["source"] = source
    if cursor_detected_at is not None and cursor_id is not None:
        where.append("(detected_at, event_id) < (CAST(:cur_ts AS timestamptz), :cur_id)")
        params["cur_ts"] = cursor_detected_at
        params["cur_id"] = cursor_id
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    sql = (
        f"SELECT {_COLS} FROM seismic_events{clause} "
        "ORDER BY detected_at DESC, event_id DESC LIMIT :limit"
    )
    return text(sql), params


def select_event(event_id: str) -> tuple[TextClause, dict[str, Any]]:
    """Detalle de un evento sísmico por su id textual."""
    sql = f"SELECT {_COLS} FROM seismic_events WHERE event_id = :id"
    return text(sql), {"id": event_id}


def select_quorum_votes(event_id: str) -> tuple[TextClause, dict[str, Any]]:
    """Votos de quórum del evento, con ``delta_s`` por sensor/estación."""
    sql = (
        "SELECT event_id, sensor_id, detected_at, pga_g, delta_s, counted "
        "FROM quorum_votes WHERE event_id = :id "
        "ORDER BY detected_at ASC, sensor_id ASC"
    )
    return text(sql), {"id": event_id}
