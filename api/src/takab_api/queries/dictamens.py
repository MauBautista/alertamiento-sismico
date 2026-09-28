"""SQL de dictámenes (T-1.22 · B2). Append-only: firmar = INSERTAR fila nueva.

Un dictamen nunca se actualiza; corregir o firmar = insertar una fila que apunta a
la anterior por ``supersedes_dictamen_id`` (el trigger append-only lo fuerza). RLS
filtra por tenant; el ``tenant_id`` de la fila nueva se toma del propio incidente.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import TextClause, text

from takab_api.dictamen.rules import banda_de
from takab_api.dictamen.sistema import FIRMA_HUMANA_SQL

_COLS = (
    "dictamen_id, tenant_id, incident_id, status, basis, signed_by, "
    "supersedes_dictamen_id, created_at, signature_kind, band"
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
        text("SELECT tenant_id, site_id FROM incidents WHERE incident_id = CAST(:id AS uuid)"),
        {"id": incident_id},
    )


def lock_incident(incident_id: str) -> tuple[TextClause, dict[str, Any]]:
    """[T-9.30 · D-43] ``tenant_id`` del incidente visible, tomando la fila ``FOR UPDATE``.

    Toda inserción en la cadena (worker, firma, confirmación) serializa aquí y valida
    la cabeza DENTRO de la misma transacción: sin esto, dos escritores leen la misma
    cabeza y la cadena se bifurca. None → 404."""
    return (
        text(
            "SELECT tenant_id, site_id FROM incidents "
            "WHERE incident_id = CAST(:id AS uuid) FOR UPDATE"
        ),
        {"id": incident_id},
    )


def select_damage_reports(incident_id: str) -> tuple[TextClause, dict[str, Any]]:
    """[D-49 · R4] Los reportes de daño del incidente: id, hora y claves.

    Se lee DENTRO del lock del incidente: sus ids son ``basis.danos_vistos`` de la
    firma humana que se inserta, y ``sistema.danos_no_vistos`` los filtra para el
    409 «requiere inspector». Misma forma que ``_DAMAGE_SQL`` del worker."""
    sql = (
        "SELECT d.report_id, d.created_at, "
        "COALESCE(array_agg(DISTINCT c.value->>'key') "
        "FILTER (WHERE c.value->>'key' IS NOT NULL), ARRAY[]::text[]) AS claves "
        "FROM damage_reports d LEFT JOIN LATERAL jsonb_array_elements(CASE WHEN "
        "jsonb_typeof(d.categories) = 'array' THEN d.categories ELSE '[]'::jsonb END) c "
        "ON true WHERE d.incident_id = CAST(:id AS uuid) "
        "GROUP BY d.report_id, d.created_at ORDER BY d.created_at, d.report_id"
    )
    return text(sql), {"id": incident_id}


def select_last_human_signature(incident_id: str) -> tuple[TextClause, dict[str, Any]]:
    """[D-49 · R4] La ÚLTIMA firma HUMANA de la cadena (``FIRMA_HUMANA_SQL``), o None."""
    sql = (
        "SELECT d.dictamen_id, d.signature_kind, d.created_at, d.basis FROM dictamens d "
        f"WHERE d.incident_id = CAST(:id AS uuid) AND {FIRMA_HUMANA_SQL} "
        "ORDER BY d.created_at DESC, d.dictamen_id DESC LIMIT 1"
    )
    return text(sql), {"id": incident_id}


def select_chain_head_row(incident_id: str) -> tuple[TextClause, dict[str, Any]]:
    """[T-9.31] La CABEZA vigente completa (id, status, banda, firma), o None."""
    sql = (
        "SELECT dictamen_id, status, band, signed_by, signature_kind, created_at "
        "FROM dictamens WHERE incident_id = CAST(:id AS uuid) "
        "ORDER BY created_at DESC, dictamen_id DESC LIMIT 1"
    )
    return text(sql), {"id": incident_id}


def select_chain_head(incident_id: str) -> tuple[TextClause, dict[str, Any]]:
    """Id del dictamen más reciente del incidente (a superseder), o None si no hay."""
    sql = (
        "SELECT dictamen_id FROM dictamens WHERE incident_id = CAST(:id AS uuid) "
        "ORDER BY created_at DESC, dictamen_id DESC LIMIT 1"
    )
    return text(sql), {"id": incident_id}


def select_chain_basis(incident_id: str) -> tuple[TextClause, dict[str, Any]]:
    """[T-7.37] Los `basis` de la CADENA, de la cabeza hacia atrás.

    No basta con la cabeza: al firmar, el `basis` de la fila nueva es `{}` o
    `{"notes": …}`, así que en una cadena ya firmada la congelación de umbrales
    vive en una fila anterior. Buscar solo en la cabeza la perdería justo en el
    documento que más pesa.
    """
    sql = (
        "SELECT basis FROM dictamens WHERE incident_id = CAST(:id AS uuid) "
        "ORDER BY created_at DESC, dictamen_id DESC"
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
    signature_kind: str = "inspector",
) -> tuple[TextClause, dict[str, Any]]:
    """Inserta una fila nueva de dictamen firmada y devuelve la fila completa.

    [T-9.31 · D-43] ``signature_kind`` declara QUIÉN firmó (``signed_by`` sólo dice
    «firmado») y ``band`` se deriva del status firmado."""
    sql = (
        "INSERT INTO dictamens "
        "(tenant_id, incident_id, status, basis, signed_by, supersedes_dictamen_id, "
        "signature_kind, band, created_at) "
        "VALUES (CAST(:tenant AS uuid), CAST(:incident AS uuid), :status, "
        "CAST(:basis AS jsonb), CAST(:signed_by AS uuid), "
        "CAST(:supersedes AS uuid), :signature_kind, :band, "
        # [T-9.30] `created_at` MONÓTONO, como el del worker: `now()` es el inicio de
        # la transacción y puede quedar DETRÁS de la cabeza que esta fila supersede
        # (si esperó el lock del incidente), con lo que no sería la cabeza nueva.
        "GREATEST(clock_timestamp(), COALESCE((SELECT max(created_at) FROM dictamens "
        "WHERE incident_id = CAST(:incident AS uuid)) + interval '1 microsecond', "
        "'-infinity'::timestamptz))) "
        f"RETURNING {_COLS}"
    )
    return text(sql), {
        "signature_kind": signature_kind,
        "band": banda_de(status),
        "tenant": tenant_id,
        "incident": incident_id,
        "status": status,
        "basis": basis,
        "signed_by": signed_by,
        "supersedes": supersedes,
    }
