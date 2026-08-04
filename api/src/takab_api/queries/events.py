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
    ids: list[str] | None = None,
) -> tuple[TextClause, dict[str, Any]]:
    """Lista keyset de eventos sísmicos, opcionalmente filtrada por ``source``.

    [T-2.39] Con ``ids`` la consulta pasa a ser una BÚSQUEDA por conjunto y el keyset
    se desactiva. Existe porque la pantalla de evaluación enriquecía sus filas con los
    50 eventos más recientes: al cargar la segunda página, incidentes con evento
    perfectamente existente se quedaban sin magnitud, epicentro ni nodos, en silencio.
    """
    where: list[str] = []
    params: dict[str, Any] = {"limit": limit}
    if ids:
        where.append("event_id = ANY(:ids)")
        params["ids"] = ids
    if source is not None:
        where.append("source = :source")
        params["source"] = source
    if not ids and cursor_detected_at is not None and cursor_id is not None:
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
    """Votos de quórum del evento, con ``delta_s`` por sensor/estación.

    [T-2.39] Resuelve el NOMBRE de la estación. Los votos son dato de RED —pueden
    venir de sensores de otros clientes— y la consola solo tenía el uuid, que
    truncaba a 8 caracteres: ocho hex no le dicen nada a nadie.

    Los LEFT JOIN pasan por la RLS de ``sensors``/``sites``, así que una estación
    ajena devuelve ``NULL`` en ambos campos. Eso NO es un fallo: es exactamente lo
    que hay que decir ("otra red"), y una etiqueta inventada sería peor que el uuid.
    """
    sql = (
        "SELECT qv.event_id, qv.sensor_id, qv.detected_at, qv.pga_g, qv.delta_s, "
        "       qv.counted, sn.serial AS station_serial, st.code AS site_code "
        "FROM quorum_votes qv "
        "LEFT JOIN sensors sn ON sn.sensor_id = qv.sensor_id "
        "LEFT JOIN sites st ON st.site_id = sn.site_id "
        "WHERE qv.event_id = :id "
        "ORDER BY qv.detected_at ASC, qv.sensor_id ASC"
    )
    return text(sql), {"id": event_id}
