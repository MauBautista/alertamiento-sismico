"""SQL de incidentes (T-1.22 · B2). RLS filtra por tenant en cada statement.

La paginación es keyset sobre ``(opened_at, incident_id)`` en orden descendente:
estable ante inserciones y sin OFFSET. El cursor opaco (``routers._common``) lleva
``opened_at`` en ISO y el ``incident_id``; aquí se castean a sus tipos.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import TextClause, text

_COLS = (
    "incident_id, event_uuid, tenant_id, site_id, event_id, opened_at, closed_at, "
    "severity, state, trigger, max_pga_g, max_pgv_cms, summary"
)


def select_incidents(
    *,
    state: str | None,
    severity: str | None,
    site_id: str | None,
    q: str | None,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
    cursor_opened_at: str | None,
    cursor_id: str | None,
    limit: int,
) -> tuple[TextClause, dict[str, Any]]:
    """Lista keyset de incidentes con filtros opcionales. Pide ``limit`` filas."""
    where: list[str] = []
    params: dict[str, Any] = {"limit": limit}
    if state is not None:
        where.append("state = :state")
        params["state"] = state
    if severity is not None:
        where.append("severity = :severity")
        params["severity"] = severity
    if site_id is not None:
        where.append("site_id = CAST(:site_id AS uuid)")
        params["site_id"] = site_id
    if q is not None:
        # Prefijo del id textual del evento sísmico (p.ej. 'EVT-20260510').
        where.append("starts_with(event_id, :q)")
        params["q"] = q
    # [T-1.57] Rango de fechas sobre opened_at (semiabierto [from, to) — combinable
    # con el cursor: ambos acotan y el keyset sigue siendo estable).
    if from_ts is not None:
        where.append("opened_at >= :from_ts")
        params["from_ts"] = from_ts
    if to_ts is not None:
        where.append("opened_at < :to_ts")
        params["to_ts"] = to_ts
    if cursor_opened_at is not None and cursor_id is not None:
        where.append(
            "(opened_at, incident_id) < (CAST(:cur_ts AS timestamptz), CAST(:cur_id AS uuid))"
        )
        params["cur_ts"] = cursor_opened_at
        params["cur_id"] = cursor_id
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    sql = (
        f"SELECT {_COLS} FROM incidents{clause} "
        "ORDER BY opened_at DESC, incident_id DESC LIMIT :limit"
    )
    return text(sql), params


def select_incident(incident_id: str) -> tuple[TextClause, dict[str, Any]]:
    """Detalle de un incidente por id (RLS decide visibilidad)."""
    sql = f"SELECT {_COLS} FROM incidents WHERE incident_id = CAST(:id AS uuid)"
    return text(sql), {"id": incident_id}


def incident_exists(incident_id: str) -> tuple[TextClause, dict[str, Any]]:
    """Existencia/visibilidad de un incidente (para distinguir 404 de lista vacía)."""
    return (
        text("SELECT 1 FROM incidents WHERE incident_id = CAST(:id AS uuid)"),
        {"id": incident_id},
    )


def select_incident_actions(incident_id: str) -> tuple[TextClause, dict[str, Any]]:
    """Timeline append-only de un incidente, en orden cronológico estable."""
    sql = (
        "SELECT action_id, incident_id, tenant_id, ts, kind, actor, payload "
        "FROM incident_actions WHERE incident_id = CAST(:id AS uuid) "
        "ORDER BY ts ASC, action_id ASC"
    )
    return text(sql), {"id": incident_id}
