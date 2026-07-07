"""SQL de la exportación PDF por incidente (T-1.20 · B5).

Lecturas bajo RLS (``takab_app`` + GUCs del request): el incidente invisible
para el tenant simplemente no aparece (404 sin fuga). La fila de evidencia se
inserta con el ``tenant_id`` del propio incidente (WITH CHECK de la policy).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import TextClause, text

# Incidente + sitio para el encabezado del reporte (RLS decide visibilidad).
SELECT_INCIDENT = text(
    "SELECT i.incident_id, i.tenant_id, i.event_id, i.opened_at, i.closed_at, "
    "i.severity, i.state, i.trigger, i.max_pga_g, i.max_pgv_cms, "
    "s.name AS site_name, s.code AS site_code "
    "FROM incidents i JOIN sites s ON s.site_id = i.site_id "
    "WHERE i.incident_id = :incident_id"
)


def insert_evidence(
    *, tenant_id: str, incident_id: str, s3_key: str, sha256: str
) -> tuple[TextClause, dict[str, Any]]:
    """Registra el PDF subido como evidencia inmutable del incidente."""
    sql = (
        "INSERT INTO evidence_objects (tenant_id, incident_id, kind, s3_key, sha256) "
        "VALUES (CAST(:tenant AS uuid), CAST(:incident AS uuid), 'report_pdf', "
        ":key, :sha) RETURNING evidence_id"
    )
    return text(sql), {
        "tenant": tenant_id,
        "incident": incident_id,
        "key": s3_key,
        "sha": sha256,
    }
