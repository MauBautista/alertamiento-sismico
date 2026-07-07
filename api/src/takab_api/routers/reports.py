"""Exportación PDF por incidente (T-1.20 · B5).

``POST /incidents/{id}/report`` construye el reporte (incidente + cadena de
dictámenes + quórum con offsets + deslinde §1), lo sube al bucket de evidencia,
lo registra como ``evidence_objects kind='report_pdf'`` (sha256) con huella en
``audit_log`` y responde con la URL presignada de descarga.

Roles: los de export (RBAC §2) MENOS ``gov_operator`` — gov descarga evidencia
ya existente (``exports``), pero generar evidencia inserta una fila con el
``tenant_id`` del incidente ajeno, que su propia RLS rechaza por diseño.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.audit import audit_async
from takab_api.auth.claims import Claims
from takab_api.auth.deps import get_session, require_roles
from takab_api.dictamen.pdf import build_report_lines, render_pdf
from takab_api.queries import dictamens as dictamens_q
from takab_api.queries import events as events_q
from takab_api.queries import reports as q
from takab_api.routers._common import http_error
from takab_api.routers._s3 import PRESIGN_TTL_S, presign_get, put_object
from takab_api.routers.exports import EXPORT_ROLES
from takab_api.schemas.reports import ReportOut
from takab_api.settings import Settings

REPORT_ROLES: tuple[str, ...] = tuple(r for r in EXPORT_ROLES if r != "gov_operator")

_require_report = require_roles(*REPORT_ROLES)

router = APIRouter()


@router.post("/incidents/{incident_id}/report", response_model=ReportOut, status_code=201)
async def generate_report(
    incident_id: UUID,
    claims: Claims = Depends(_require_report),
    conn: AsyncConnection = Depends(get_session),
) -> ReportOut:
    """Genera el PDF del incidente y lo registra como evidencia inmutable."""
    settings = Settings()
    if not settings.evidence_bucket:
        raise http_error(503, "bucket de evidencia no configurado")

    incident = (
        (await conn.execute(q.SELECT_INCIDENT, {"incident_id": incident_id})).mappings().first()
    )
    if incident is None:
        raise http_error(404, "incidente no encontrado")

    d_stmt, d_params = dictamens_q.select_dictamens(str(incident_id))
    chain = [dict(r) for r in (await conn.execute(d_stmt, d_params)).mappings().all()]
    votes: list[dict] = []
    if incident["event_id"] is not None:
        v_stmt, v_params = events_q.select_quorum_votes(incident["event_id"])
        votes = [dict(r) for r in (await conn.execute(v_stmt, v_params)).mappings().all()]

    pdf = render_pdf(build_report_lines(dict(incident), chain, votes))
    sha256 = hashlib.sha256(pdf).hexdigest()
    key = (
        f"evidence/{incident['tenant_id']}/{incident_id}/"
        f"report-{datetime.now(tz=UTC):%Y%m%dT%H%M%SZ}.pdf"
    )
    put_object(settings, key, pdf, content_type="application/pdf")

    ev_stmt, ev_params = q.insert_evidence(
        tenant_id=str(incident["tenant_id"]),
        incident_id=str(incident_id),
        s3_key=key,
        sha256=sha256,
    )
    evidence_id = (await conn.execute(ev_stmt, ev_params)).scalar_one()
    await audit_async(
        conn,
        tenant_id=incident["tenant_id"],
        actor=f"user:{claims.sub}",
        verb="export_pdf",
        obj=f"evidence:{evidence_id}",
    )
    return ReportOut(
        evidence_id=evidence_id, url=presign_get(settings, key), expires_in=PRESIGN_TTL_S
    )
