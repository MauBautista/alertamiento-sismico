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
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
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

    # [T-5.18] El freno, ANTES de renderizar: la única puerta de este endpoint era
    # de rol, así que un usuario autenticado podía reexportar el mismo incidente
    # sin límite — y cada exportación renderiza un PDF, lo sube a S3 y, con la IA
    # encendida, sale a una red de pago. Dos techos, el mismo par que los
    # comandos: el del usuario y el del EDIFICIO (dos operadores coordinados
    # agotan el segundo sin rebasar ninguno el suyo — `RO-8.e`).
    await _freno_de_exportacion(conn, claims, str(incident["site_id"]), settings)

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
    narrative = await build_narrative(
        model,
        settings,
        conn=conn,
        tenant_id=str(incident["tenant_id"]),
        # [T-5.18] El actor va para que la fila de CRUCE de la cuota tenga
        # autor. Sin él la transición se sella igual —no se audita dos
        # veces— pero nadie sabría quién estaba exportando al agotarse.
        actor=f"user:{claims.sub}",
    )
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
        meta={
            "variant": variant,
            "folio": model.folio,
            "content_sha256": model.content_sha256(),
            # [T-5.18] El sitio, para que el techo por EDIFICIO se pueda contar
            # desde aquí sin un join. El de usuario ya salía del `actor`.
            "site_id": str(incident["site_id"]),
        },
    )
    return ReportOut(
        evidence_id=evidence_id, url=presign_get(settings, key), expires_in=PRESIGN_TTL_S
    )


# ──────────────────────────────── [T-5.18] el tope y el freno


_VENTANA_S = 60.0

#: Los dos conteos salen de `audit_log`, que es donde ya queda cada exportación y
#: que **no se poda nunca** (regla de oro 11): no hace falta tabla nueva ni un
#: contador que se pueda perder. El de usuario sale del `actor`; el del edificio,
#: del `site_id` que el `meta` empezó a llevar en esta misma ficha.
_CUENTA_USUARIO = text(
    "SELECT count(*) FROM audit_log WHERE verb = 'export_pdf' AND actor = :actor AND ts > :since"
)
_CUENTA_SITIO = text(
    "SELECT count(*) FROM audit_log "
    "WHERE verb = 'export_pdf' AND meta->>'site_id' = :site AND ts > :since"
)


async def _freno_de_exportacion(
    conn: AsyncConnection, claims: Claims, site_id: str, settings: Settings
) -> None:
    """429 si se rebasa el techo por usuario o el del edificio.

    Es el ÚNICO 429 de este endpoint, y llega antes de renderizar: rechazar
    después de haber gastado el PDF y la llamada de IA no protegería de nada.
    """
    since = datetime.now(tz=UTC) - timedelta(seconds=_VENTANA_S)
    actor = f"user:{claims.sub}"
    por_usuario = (
        await conn.execute(_CUENTA_USUARIO, {"actor": actor, "since": since})
    ).scalar_one()
    if por_usuario >= settings.report_rate_user_per_min:
        raise http_error(429, "rate-limit de exportación por usuario excedido")
    por_sitio = (await conn.execute(_CUENTA_SITIO, {"site": site_id, "since": since})).scalar_one()
    if por_sitio >= settings.report_rate_site_per_min:
        raise http_error(429, "rate-limit de exportación del sitio excedido")
