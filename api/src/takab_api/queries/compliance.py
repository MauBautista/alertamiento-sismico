"""SQL de ``compliance_labels`` (T-2.82).

Todo pasa bajo la RLS del request: ``cl_read`` decide qué filas existen para quien
pregunta y ``cl_admin`` decide quién escribe. Nada de esto se vuelve a filtrar en
Python — dos filtros sobre la misma frontera dan dos verdades.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.compliance import ComplianceDocument, parse_document

#: ¿Existe el cliente PARA QUIEN PREGUNTA? (RLS ``tenants_read``). Se consulta antes
#: que las etiquetas para poder distinguir "no lo puedes ver" (404) de "no declaró
#: nada" (documento vacío) — regla de oro 7.
TENANT_VISIBLE = text("SELECT 1 FROM tenants WHERE tenant_id = CAST(:tenant AS uuid)")

SELECT_LABELS = text(
    "SELECT labels, updated_at, updated_by FROM compliance_labels "
    "WHERE tenant_id = CAST(:tenant AS uuid)"
)

#: Alta o reemplazo. ``RETURNING`` no es adorno: si la RLS deja la sentencia en 0
#: filas —cosa que un UPDATE bajo RLS hace EN SILENCIO, sin lanzar— el router se
#: entera y no responde 200 a una escritura que no ocurrió.
UPSERT_LABELS = text(
    "INSERT INTO compliance_labels (tenant_id, labels, updated_at, updated_by) "
    "VALUES (CAST(:tenant AS uuid), CAST(:labels AS jsonb), now(), CAST(:actor AS uuid)) "
    "ON CONFLICT (tenant_id) DO UPDATE SET "
    "  labels = EXCLUDED.labels, updated_at = now(), updated_by = EXCLUDED.updated_by "
    "RETURNING labels, updated_at, updated_by"
)

#: Marco declarado del DUEÑO del incidente. Se llega por ``incidents`` a propósito: la
#: RLS del incidente es la que decide si esta respuesta existe, así que el marco del
#: cliente no puede escaparse por un camino más ancho que el propio incidente.
LABELS_FOR_INCIDENT = text(
    "SELECT cl.labels FROM incidents i "
    "LEFT JOIN compliance_labels cl ON cl.tenant_id = i.tenant_id "
    "WHERE i.incident_id = CAST(:incident AS uuid)"
)


async def document_for_incident(conn: AsyncConnection, incident_id: str) -> ComplianceDocument:
    """Documento declarado por el cliente dueño del incidente.

    Fuente única de la pantalla de Triage y del dictamen PDF: si cada uno lo leyera a
    su manera acabarían discrepando, y un dictamen que no coincide con lo que el
    inspector vio al firmar es peor que ninguno.
    """
    row = (await conn.execute(LABELS_FOR_INCIDENT, {"incident": incident_id})).first()
    return parse_document(row.labels) if row is not None else ComplianceDocument()
