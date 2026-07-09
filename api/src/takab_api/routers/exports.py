"""Exportación de evidencia (T-1.22 · B4, gate #5).

- ``GET /incidents/{id}/evidence`` — lista ``evidence_objects`` del incidente;
  RLS filtra por tenant (gov ve ``gov_shared`` por su policy). Cualquier rol web.
- ``POST /evidence/{id}/download`` — verifica visibilidad con un SELECT bajo RLS,
  emite una URL GET presignada de 300 s y escribe ``audit_log``. Roles con export
  (RBAC §2 · Triage export): superadmin, gov_operator, inspector. Sin bucket de
  evidencia configurado → 503 (dev local sin AWS sigue vivo).

El presigned URL se firma en proceso (sin red): boto3 usa las credenciales del
rol de la tarea ECS en prod y las de moto en tests.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.audit import audit_async
from takab_api.auth.claims import Claims
from takab_api.auth.deps import get_session, require_roles, require_web_surface
from takab_api.auth.matrix import roles_with_action
from takab_api.queries import exports as q
from takab_api.routers._common import http_error
from takab_api.routers._s3 import PRESIGN_TTL_S, presign_get
from takab_api.schemas.exports import EvidenceList, EvidenceObject, PresignedDownload
from takab_api.settings import Settings

# Fuente única: roles con acción export en la matriz (espejo de RBAC §2).
EXPORT_ROLES: tuple[str, ...] = roles_with_action("export")

_require_export = require_roles(*EXPORT_ROLES)

router = APIRouter()


@router.get("/incidents/{incident_id}/evidence", response_model=EvidenceList)
async def list_evidence(
    incident_id: UUID,
    _claims: Claims = Depends(require_web_surface),
    conn: AsyncConnection = Depends(get_session),
) -> EvidenceList:
    """Lista la evidencia de un incidente visible para el tenant (RLS)."""
    rows = (await conn.execute(q.LIST_EVIDENCE, {"incident_id": incident_id})).mappings().all()
    return EvidenceList(items=[EvidenceObject(**dict(r)) for r in rows])


@router.post("/evidence/{evidence_id}/download", response_model=PresignedDownload)
async def download_evidence(
    evidence_id: UUID,
    claims: Claims = Depends(_require_export),
    conn: AsyncConnection = Depends(get_session),
) -> PresignedDownload:
    """Presigned GET 300 s de un objeto de evidencia + huella en ``audit_log``."""
    settings = Settings()
    if not settings.evidence_bucket:
        raise http_error(503, "bucket de evidencia no configurado")

    row = (await conn.execute(q.GET_EVIDENCE, {"evidence_id": evidence_id})).first()
    if row is None:
        raise http_error(404, "evidencia no encontrada")

    verb = "export_pdf" if row.kind == "report_pdf" else "export_miniseed"
    url = presign_get(settings, row.s3_key)

    await audit_async(
        conn,
        tenant_id=row.tenant_id,
        actor=f"user:{claims.sub}",
        verb=verb,
        obj=f"evidence:{evidence_id}",
    )
    return PresignedDownload(url=url, expires_in=PRESIGN_TTL_S)
