"""Exportación PDF por incidente (T-1.20 · B5).

``POST /incidents/{id}/report`` construye el reporte (incidente + cadena de
dictámenes + quórum con offsets + deslinde §1), lo sube al bucket de evidencia,
lo registra como ``evidence_objects kind='report_pdf'`` (sha256) con huella en
``audit_log`` y responde con la URL presignada de descarga.

Roles: los de la acción ``generate_report`` en la matriz (superadmin, inspector).
Es un subconjunto estricto de ``export``: gov_operator descarga evidencia ya
existente (``exports``), pero GENERARLA inserta una fila con el ``tenant_id`` del
incidente ajeno, que su propia RLS rechaza por diseño. La acción va separada para
que la consola no le pinte un botón condenado al 403 (regla de oro 7).
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.audit import audit_async
from takab_api.auth.claims import Claims
from takab_api.auth.deps import get_session, require_roles
from takab_api.auth.matrix import roles_with_action
from takab_api.dictamen.builder import build_model
from takab_api.dictamen.pdf import render
from takab_api.narrative import apply_narrative, build_narrative
from takab_api.queries import reports as q
from takab_api.routers._common import http_error
from takab_api.routers._s3 import PRESIGN_TTL_S, get_object, presign_get, put_object
from takab_api.schemas.reports import ReportOut
from takab_api.settings import Settings

# Fuente única: roles con acción generate_report en la matriz (espejo de RBAC §2).
REPORT_ROLES: tuple[str, ...] = roles_with_action("generate_report")

_require_report = require_roles(*REPORT_ROLES)

router = APIRouter()


#: Variantes del dictamen. `technical` es pericial; `executive` es para quien decide.
VARIANTS = ("technical", "executive")


@router.post("/incidents/{incident_id}/report", response_model=ReportOut, status_code=201)
async def generate_report(
    incident_id: UUID,
    variant: str = Query("technical", description="technical | executive"),
    claims: Claims = Depends(_require_report),
    conn: AsyncConnection = Depends(get_session),
) -> ReportOut:
    """Genera el PDF del incidente y lo registra como evidencia inmutable.

    [T-2.41] Dos documentos del mismo modelo. Se conserva `report_pdf` como `kind` de
    evidencia: la variante va en la key de S3 y en la auditoría, y ampliar el CHECK
    del DDL por una etiqueta no lo valdría.

    El gate de "sin dictamen no hay PDF" se retiró: un incidente sin dictamen YA tiene
    hechos que reportar —lo que midió el sensor, quién acusó, qué estaciones
    corroboraron— y el documento lo rotula como preliminar.
    """
    settings = Settings()
    if not settings.evidence_bucket:
        raise http_error(503, "bucket de evidencia no configurado")
    if variant not in VARIANTS:
        raise http_error(422, f"variante desconocida: {variant}")

    incident = (
        (await conn.execute(q.SELECT_INCIDENT, {"incident_id": incident_id})).mappings().first()
    )
    if incident is None:
        raise http_error(404, "incidente no encontrado")

    model = await build_model(
        conn,
        str(incident_id),
        variant=variant,
        generated_at=datetime.now(tz=UTC),
        # La lectura del miniSEED es best-effort dentro del builder: un fallo de S3
        # degrada la sección, nunca tumba la exportación.
        fetch_object=lambda key: get_object(settings, key),
        settings=settings,
    )
    if model is None:  # pragma: no cover - el SELECT de arriba ya lo cubre
        raise http_error(404, "incidente no encontrado")

    # [T-2.42] Prosa que RODEA al veredicto. `build_narrative` nunca lanza: si el
    # proveedor falla, degrada al determinista y el PDF lo declara. El veredicto que
    # el documento afirma ya está en `model` y esta llamada no lo toca.
    narrative = await build_narrative(model, settings)
    apply_narrative(model, narrative)

    pdf = render(model, variant)
    sha256 = hashlib.sha256(pdf).hexdigest()
    key = (
        f"evidence/{incident['tenant_id']}/{incident_id}/"
        f"report-{variant}-{datetime.now(tz=UTC):%Y%m%dT%H%M%SZ}.pdf"
    )
    put_object(settings, key, pdf, content_type="application/pdf")

    ev_stmt, ev_params = q.insert_evidence(
        tenant_id=str(incident["tenant_id"]),
        incident_id=str(incident_id),
        s3_key=key,
        sha256=sha256,
    )
    evidence_id = (await conn.execute(ev_stmt, ev_params)).scalar_one()
    # Procedencia de la prosa. No hay tabla nueva: la narrativa queda congelada en el
    # PDF —que ya es evidencia inmutable con sha256— y su procedencia va al log
    # append-only, que por la regla de oro 11 no se poda nunca.
    await audit_async(
        conn,
        tenant_id=incident["tenant_id"],
        actor=f"user:{claims.sub}",
        verb="narrative_generated",
        obj=f"evidence:{evidence_id}",
        meta=narrative.provenance(),
    )
    await audit_async(
        conn,
        tenant_id=incident["tenant_id"],
        actor=f"user:{claims.sub}",
        verb="export_pdf",
        obj=f"evidence:{evidence_id}",
        meta={"variant": variant, "folio": model.folio, "content_sha256": model.content_sha256()},
    )
    return ReportOut(
        evidence_id=evidence_id, url=presign_get(settings, key), expires_in=PRESIGN_TTL_S
    )
