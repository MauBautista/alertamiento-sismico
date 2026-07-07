"""SQL de exportación de evidencia (T-1.22 · B4).

Todas las consultas corren como ``takab_app`` con los GUCs del request → RLS de
``evidence_objects`` filtra por tenant (y deja ver ``gov_shared`` al gov_operator
por su policy). La escritura en ``audit_log`` deja huella inmutable del export.
"""

from __future__ import annotations

from sqlalchemy import text

# Evidencias de un incidente (RLS por tenant + rama gov_shared).
LIST_EVIDENCE = text(
    "SELECT evidence_id, incident_id, sensor_id, kind, s3_key, ts_from, ts_to, "
    "sha256, created_at FROM evidence_objects "
    "WHERE incident_id = :incident_id ORDER BY created_at DESC, evidence_id"
)

# Una evidencia por id (visibilidad decidida por RLS).
GET_EVIDENCE = text(
    "SELECT evidence_id, tenant_id, kind, s3_key FROM evidence_objects "
    "WHERE evidence_id = :evidence_id"
)

# Huella de auditoría del export (verb export_miniseed|export_pdf).
INSERT_AUDIT = text(
    "INSERT INTO audit_log (tenant_id, actor, verb, object) "
    "VALUES (:tenant_id, :actor, :verb, :object)"
)
