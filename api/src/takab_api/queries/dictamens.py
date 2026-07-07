"""SQL de dictámenes (T-1.22 · B2). Append-only: firmar = INSERTAR fila nueva.

Un dictamen nunca se actualiza; corregir o firmar = insertar una fila que apunta a
la anterior por ``supersedes_dictamen_id`` (el trigger append-only lo fuerza). RLS
filtra por tenant; el ``tenant_id`` de la fila nueva se toma del propio incidente.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import TextClause, text

_COLS = (
    "dictamen_id, tenant_id, incident_id, status, basis, signed_by, "
    "supersedes_dictamen_id, created_at"
)


def select_dictamens(incident_id: str) -> tuple[TextClause, dict[str, Any]]:
    """Cadena de dictámenes del incidente, más reciente primero."""
    sql = (
        f"SELECT {_COLS} FROM dictamens WHERE incident_id = CAST(:id AS uuid) "
        "ORDER BY created_at DESC, dictamen_id DESC"
    )
    return text(sql), {"id": incident_id}


def select_incident_tenant(incident_id: str) -> tuple[TextClause, dict[str, Any]]:
    """``tenant_id`` del incidente visible (para la fila del dictamen). None → 404."""
    return (
        text("SELECT tenant_id FROM incidents WHERE incident_id = CAST(:id AS uuid)"),
        {"id": incident_id},
    )


def select_chain_head(incident_id: str) -> tuple[TextClause, dict[str, Any]]:
    """Id del dictamen más reciente del incidente (a superseder), o None si no hay."""
    sql = (
        "SELECT dictamen_id FROM dictamens WHERE incident_id = CAST(:id AS uuid) "
        "ORDER BY created_at DESC, dictamen_id DESC LIMIT 1"
    )
    return text(sql), {"id": incident_id}


def insert_dictamen(
    *,
    tenant_id: str,
    incident_id: str,
    status: str,
    basis: str,
    signed_by: str,
    supersedes: str | None,
) -> tuple[TextClause, dict[str, Any]]:
    """Inserta una fila nueva de dictamen firmada y devuelve la fila completa."""
    sql = (
        "INSERT INTO dictamens "
        "(tenant_id, incident_id, status, basis, signed_by, supersedes_dictamen_id) "
        "VALUES (CAST(:tenant AS uuid), CAST(:incident AS uuid), :status, "
        "CAST(:basis AS jsonb), CAST(:signed_by AS uuid), "
        "CAST(:supersedes AS uuid)) "
        f"RETURNING {_COLS}"
    )
    return text(sql), {
        "tenant": tenant_id,
        "incident": incident_id,
        "status": status,
        "basis": basis,
        "signed_by": signed_by,
        "supersedes": supersedes,
    }
