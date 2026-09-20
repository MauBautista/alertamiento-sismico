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
# [T-7.54] El `state` del incidente viaja con la fila porque el freno de
# descarga lo necesita: un tope de gasto que niega evidencia durante una
# emergencia es peor que no tener tope, así que la evidencia de un incidente
# ABIERTO no se frena. `LEFT JOIN` y no `JOIN`: un `report_pdf` de simulacro
# cuelga de `drill_id` y tiene `incident_id` NULL — con un INNER, pedirlo daría
# 404 y la descarga del reporte de simulacro dejaría de existir.
GET_EVIDENCE = text(
    "SELECT e.evidence_id, e.tenant_id, e.kind, e.s3_key, i.state AS incident_state "
    "FROM evidence_objects e LEFT JOIN incidents i ON i.incident_id = e.incident_id "
    "WHERE e.evidence_id = :evidence_id"
)

# [T-7.54] El contador del freno. Sale de `audit_log`, igual que el de
# exportación y por la misma razón: ya hay una fila por descarga desde `T-7.45`
# y esa tabla no se poda nunca (regla de oro 11), así que no hace falta ni tabla
# nueva ni un contador que se pueda perder al reiniciar.
#
# ⚠️ `verb LIKE 'download\_%'` y no una lista de verbos: el verbo se DERIVA del
# `kind` (`download_<kind>`), así que enumerarlos aquí crearía una segunda lista
# que hay que sincronizar a mano con el CHECK del DDL — y un `kind` nuevo nacería
# sin freno y sin que nadie lo notara. El `\_` escapa el comodín de `LIKE`.
#
# Anclada en `ts > :since`, que es el único índice servible: la RLS de lectura de
# `audit_log` es un `OR` y apoyarse en `tenant_id` no sirve.
CUENTA_DESCARGAS_USUARIO = text(
    "SELECT count(*) FROM audit_log "
    r"WHERE verb LIKE 'download\_%' AND actor = :actor AND ts > :since"
)
