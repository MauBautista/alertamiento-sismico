"""Superficie móvil · recursos por INCIDENTE (T-2.03 · spec §5).

- ``POST/GET /incidents/{id}/checkins`` — check-in de vida (propio; DELEGADO
  para tácticos con ``roster_read``: "verificado en persona", distinguible).
- ``GET /incidents/{id}/roster``        — roster × último check-in por persona
  (headcount 2.6; lectura de PII → auditada).
- ``POST/GET /incidents/{id}/damage-reports`` — formulario de daños → Triage.

``life_checkins``/``damage_reports`` son EVIDENCIA (append-only, jamás se
podan). El alcance sigue R2: occupant enrolado en el sitio del incidente;
tácticos por ``site_scope``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.audit import audit_async
from takab_api.auth.claims import Claims, scope_filter
from takab_api.auth.deps import get_session, require_roles
from takab_api.auth.matrix import roles_with_action
from takab_api.queries import mobile as q
from takab_api.routers._common import http_error, integrity_error
from takab_api.routers._s3 import presign_put, read_object
from takab_api.routers.incidents import CONSOLE_ROLES
from takab_api.schemas.mobile import (
    CheckinIn,
    CheckinOut,
    DamageReportIn,
    DamageReportOut,
    EvidenceRegisterIn,
    EvidenceRegisterOut,
    EvidenceVerifyOut,
    RosterCheckin,
    RosterEntry,
    RosterOut,
)
from takab_api.settings import Settings

_CHECKIN_ROLES = roles_with_action("checkin_submit")
_ROSTER_ROLES = roles_with_action("roster_read")
_DAMAGE_ROLES = roles_with_action("damage_report_submit")
_EVIDENCE_ROLES = roles_with_action("evidence_upload")
# La consola (Triage) LEE los reportes de daños; los tácticos también ven los suyos.
_DAMAGE_READ_ROLES = tuple(sorted(set(CONSOLE_ROLES) | set(_DAMAGE_ROLES)))

_require_checkin = require_roles(*_CHECKIN_ROLES)
_require_roster = require_roles(*_ROSTER_ROLES)
_require_damage = require_roles(*_DAMAGE_ROLES)
_require_damage_read = require_roles(*_DAMAGE_READ_ROLES)
_require_evidence = require_roles(*_EVIDENCE_ROLES)

router = APIRouter()


async def _incident_in_scope(conn: AsyncConnection, claims: Claims, incident_id: UUID) -> Any:
    """Incidente visible (RLS) Y su sitio dentro del alcance del portador.

    occupant: enrolado en el sitio (R2) ⇒ si no, el MISMO 404 (sin filtración).
    Resto: ``site_scope`` del claim (default-deny).
    """
    row = (await conn.execute(q.INCIDENT_FOR_MOBILE, {"incident": str(incident_id)})).first()
    if row is None:
        raise http_error(404, "incidente no encontrado")
    if claims.role == "occupant":
        if await q.my_assignment(conn, claims.sub, row.site_id) is None:
            raise http_error(404, "incidente no encontrado")
        return row
    allowed = scope_filter(claims)
    if allowed is not None and str(row.site_id) not in allowed:
        raise http_error(403, "incidente fuera de tu alcance")
    return row


@router.post("/incidents/{incident_id}/checkins", response_model=CheckinOut, status_code=201)
async def submit_checkin(
    incident_id: UUID,
    body: CheckinIn,
    response: Response,
    claims: Claims = Depends(_require_checkin),
    conn: AsyncConnection = Depends(get_session),
) -> CheckinOut:
    """Check-in de vida. DEBE funcionar encolado offline y sincronizar después
    (la app manda ``ts_device``; el servidor sella ``created_at``).

    [T-2.06] Idempotente ante replays de la cola offline: el mismo
    ``checkin_id`` de cliente devuelve 200 con LA MISMA fila (jamás duplica);
    un id ajeno (otro portador u otro incidente) ⇒ 409 sin fuga.

    Delegado (``subject_user_id`` ≠ portador): SOLO roles con ``roster_read``
    (el brigadista marca "verificado en persona"); queda ``via='delegated'`` +
    ``verified_by`` — distinguible del check-in propio en datos (spec 2.6).
    """
    incident = await _incident_in_scope(conn, claims, incident_id)

    subject = str(body.subject_user_id) if body.subject_user_id else claims.sub
    delegated = subject != claims.sub
    if delegated and claims.role not in _ROSTER_ROLES:
        raise http_error(403, "el check-in delegado requiere rol de headcount")

    lon, lat = body.location if body.location is not None else (None, None)
    try:
        row = (
            await conn.execute(
                q.INSERT_CHECKIN,
                {
                    "checkin_id": str(body.checkin_id) if body.checkin_id else None,
                    "tenant": str(incident.tenant_id),
                    "incident": str(incident_id),
                    "subject": subject,
                    "site": str(incident.site_id),
                    "status": body.status,
                    "lon": lon,
                    "lat": lat,
                    "zone": str(body.zone_id) if body.zone_id else None,
                    "ts_device": body.ts_device,
                    "via": "delegated" if delegated else "self",
                    "verified_by": claims.sub if delegated else None,
                },
            )
        ).first()
    except IntegrityError as exc:
        raise integrity_error(exc) from exc

    if row is None:
        # ON CONFLICT DO NOTHING: replay del mismo portador ⇒ la fila original
        # (200, sin audit — es el MISMO evento); id ajeno ⇒ 409.
        row = (
            await conn.execute(
                q.CHECKIN_REPLAY,
                {
                    "checkin_id": str(body.checkin_id),
                    "incident": str(incident_id),
                    "subject": subject,
                },
            )
        ).first()
        if row is None:
            raise http_error(409, "checkin_id en conflicto con otro registro")
        response.status_code = 200
        return CheckinOut(**dict(row._mapping))

    await audit_async(
        conn,
        tenant_id=str(incident.tenant_id),
        actor=f"user:{claims.sub}",
        verb="checkin_delegated" if delegated else "checkin_submit",
        obj=f"incident:{incident_id}",
        meta={
            "status": body.status,
            "subject": subject,
            # El GPS es PII: en el audit viaja solo SI se envió, jamás el punto.
            "with_location": body.location is not None,
        },
    )
    return CheckinOut(**dict(row._mapping))


@router.get("/incidents/{incident_id}/checkins", response_model=list[CheckinOut])
async def list_my_checkins(
    incident_id: UUID,
    scope: str = Query(default="me", pattern="^me$"),
    claims: Claims = Depends(_require_checkin),
    conn: AsyncConnection = Depends(get_session),
) -> list[CheckinOut]:
    """Check-ins PROPIOS del portador en el incidente (reconstrucción de la
    máquina de estados al abrir la app). El roster completo vive en /roster
    (gated aparte: es PII de terceros)."""
    await _incident_in_scope(conn, claims, incident_id)
    rows = (
        await conn.execute(q.MY_CHECKINS, {"incident": str(incident_id), "sub": claims.sub})
    ).all()
    return [CheckinOut(**dict(r._mapping)) for r in rows]


@router.get("/incidents/{incident_id}/roster", response_model=RosterOut)
async def incident_roster(
    incident_id: UUID,
    claims: Claims = Depends(_require_roster),
    conn: AsyncConnection = Depends(get_session),
) -> RosterOut:
    """Roster del sitio del incidente × último check-in por persona (2.6).

    Lectura de PII (nombres/teléfonos): queda en ``audit_log`` quién la pidió.
    """
    incident = await _incident_in_scope(conn, claims, incident_id)
    rows = (
        await conn.execute(q.ROSTER, {"incident": str(incident_id), "site": str(incident.site_id)})
    ).all()

    entries: list[RosterEntry] = []
    safe = need_help = unreported = 0
    for r in rows:
        checkin: RosterCheckin | None = None
        if r.c_status is not None:
            checkin = RosterCheckin(
                status=r.c_status,
                via=r.c_via,
                created_at=r.c_created_at,
                ts_device=r.c_ts_device,
            )
            if r.c_status == "safe":
                safe += 1
            else:
                need_help += 1
        else:
            unreported += 1
        entries.append(
            RosterEntry(
                user_id=r.user_id,
                display_name=r.display_name,
                phone=r.phone,
                zone_id=r.zone_id,
                zone_name=r.zone_name,
                checkin=checkin,
            )
        )

    await audit_async(
        conn,
        tenant_id=str(incident.tenant_id),
        actor=f"user:{claims.sub}",
        verb="roster_read",
        obj=f"incident:{incident_id}",
        meta={"entries": len(entries)},
    )
    return RosterOut(
        incident_id=incident_id,
        site_id=incident.site_id,
        total=len(entries),
        safe=safe,
        need_help=need_help,
        unreported=unreported,
        entries=entries,
    )


@router.post(
    "/incidents/{incident_id}/damage-reports", response_model=DamageReportOut, status_code=201
)
async def submit_damage_report(
    incident_id: UUID,
    body: DamageReportIn,
    claims: Claims = Depends(_require_damage),
    conn: AsyncConnection = Depends(get_session),
) -> DamageReportOut:
    """Reporte de daños (2.4) → alimenta Triage. ``people_at_risk`` se DERIVA de
    la categoría ``people_trapped`` (prioridad máxima). [T-2.10] Con personas en
    riesgo, se registra un ``incident_action`` que el orchestrator OPS convierte
    en notificación INMEDIATA al SOC (email por la cascada existente)."""
    incident = await _incident_in_scope(conn, claims, incident_id)
    people_at_risk = any(c.key == "people_trapped" for c in body.categories)

    try:
        row = (
            await conn.execute(
                q.INSERT_DAMAGE_REPORT,
                {
                    "tenant": str(incident.tenant_id),
                    "incident": str(incident_id),
                    "site": str(incident.site_id),
                    "zone": str(body.zone_id) if body.zone_id else None,
                    "sub": claims.sub,
                    "categories": json.dumps([c.model_dump() for c in body.categories]),
                    "people_at_risk": people_at_risk,
                    "notes": body.notes,
                    "evidence_ids": [str(e) for e in body.evidence_ids],
                    "intent_key_id": str(body.intent_key_id) if body.intent_key_id else None,
                    "intent_signature": body.intent_signature,
                    "ts_device": body.ts_device,
                },
            )
        ).first()
    except IntegrityError as exc:
        raise integrity_error(exc) from exc

    if people_at_risk:
        # Timeline → el orchestrator OPS notifica al SOC de inmediato (espejo
        # del dictamen_request). El trigger NOTIFY de 0004 despierta al worker.
        await conn.execute(
            q.INSERT_PEOPLE_AT_RISK_ACTION,
            {
                "incident": str(incident_id),
                "tenant": str(incident.tenant_id),
                "actor": f"user:{claims.sub}",
                "payload": json.dumps({"report_id": str(row.report_id)}),
            },
        )

    await audit_async(
        conn,
        tenant_id=str(incident.tenant_id),
        actor=f"user:{claims.sub}",
        verb="damage_report_submit",
        obj=f"incident:{incident_id}",
        meta={
            "report_id": str(row.report_id),
            "people_at_risk": people_at_risk,
            "categories": [c.key for c in body.categories],
        },
    )
    return DamageReportOut(**dict(row._mapping))


@router.get("/incidents/{incident_id}/damage-reports", response_model=list[DamageReportOut])
async def list_damage_reports(
    incident_id: UUID,
    claims: Claims = Depends(_require_damage_read),
    conn: AsyncConnection = Depends(get_session),
) -> list[DamageReportOut]:
    """Reportes del incidente (Triage de la consola + tácticos en campo)."""
    await _incident_in_scope(conn, claims, incident_id)
    rows = (await conn.execute(q.LIST_DAMAGE_REPORTS, {"incident": str(incident_id)})).all()
    return [DamageReportOut(**dict(r._mapping)) for r in rows]


@router.post(
    "/incidents/{incident_id}/evidence", response_model=EvidenceRegisterOut, status_code=201
)
async def register_evidence(
    incident_id: UUID,
    body: EvidenceRegisterIn,
    claims: Claims = Depends(_require_evidence),
    conn: AsyncConnection = Depends(get_session),
) -> EvidenceRegisterOut:
    """[T-2.10 · 2.3] Registra una foto forense (SHA-256 declarado en captura)
    y devuelve un PUT presignado. La foto sube DIRECTO a S3 sin credenciales
    AWS (regla de oro 6); su huella queda guardada para verificarla después."""
    incident = await _incident_in_scope(conn, claims, incident_id)
    settings = Settings()
    # s3_key determinista por tenant/incidente/evidencia: aísla por tenant en
    # el propio prefijo del objeto (nada de nombres adivinables entre clientes).
    s3_key = f"evidence/{incident.tenant_id}/{incident_id}/photo-{uuid4().hex}.jpg"
    try:
        row = (
            await conn.execute(
                q.INSERT_EVIDENCE,
                {
                    "tenant": str(incident.tenant_id),
                    "incident": str(incident_id),
                    "s3_key": s3_key,
                    "sha256": body.sha256,
                    "ts_from": body.ts_from,
                },
            )
        ).first()
    except IntegrityError as exc:
        raise integrity_error(exc) from exc

    upload_url = (
        presign_put(settings, s3_key, content_type=body.content_type)
        if settings.evidence_bucket
        else None
    )
    await audit_async(
        conn,
        tenant_id=str(incident.tenant_id),
        actor=f"user:{claims.sub}",
        verb="evidence_registered",
        obj=f"evidence:{row.evidence_id}",
        # La huella declarada queda en el audit: si el blob se altera, la
        # verificación posterior lo delata contra ESTE valor.
        meta={"sha256": body.sha256, "incident": str(incident_id)},
    )
    return EvidenceRegisterOut(evidence_id=row.evidence_id, upload_url=upload_url)


@router.post("/evidence/{evidence_id}/verify", response_model=EvidenceVerifyOut)
async def verify_evidence(
    evidence_id: UUID,
    claims: Claims = Depends(_require_damage_read),
    conn: AsyncConnection = Depends(get_session),
) -> EvidenceVerifyOut:
    """[T-2.10 · 2.3] Re-hashea el objeto realmente subido y lo confronta con la
    huella declarada en captura. Alterar un byte del blob ⇒ ``verified=false``.
    Lo consumen Triage (consola) y los tácticos que revisan su propia evidencia."""
    row = (await conn.execute(q.EVIDENCE_FOR_VERIFY, {"evidence": str(evidence_id)})).first()
    if row is None:
        raise http_error(404, "evidencia no encontrada")
    # Mismo alcance que la lectura de daños: consola por rol, táctico por sitio.
    if claims.role not in CONSOLE_ROLES:
        allowed = scope_filter(claims)
        if allowed is not None and str(row.site_id) not in allowed:
            raise http_error(404, "evidencia no encontrada")

    settings = Settings()
    if not settings.evidence_bucket:
        raise http_error(503, "bucket de evidencia no configurado")
    blob = read_object(settings, row.s3_key)
    if blob is None:
        # Registrada pero aún sin subir (o key ausente): no es "verificada".
        return EvidenceVerifyOut(
            evidence_id=evidence_id, verified=False, expected_sha256=row.sha256, actual_sha256=None
        )
    actual = hashlib.sha256(blob).hexdigest()
    verified = row.sha256 is not None and hmac.compare_digest(actual, row.sha256)
    await audit_async(
        conn,
        tenant_id=str(row.tenant_id),
        actor=f"user:{claims.sub}",
        verb="evidence_verified",
        obj=f"evidence:{evidence_id}",
        meta={"verified": verified},
    )
    return EvidenceVerifyOut(
        evidence_id=evidence_id,
        verified=verified,
        expected_sha256=row.sha256,
        actual_sha256=actual,
    )
