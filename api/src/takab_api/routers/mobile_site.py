"""Superficie móvil · recursos por SITIO (T-2.03 · spec §5).

- ``GET /sites/{id}/mobile-state``      — estado consolidado (phase derivada +
  ingredientes crudos; el teléfono jamás decide fases — spec §4.1).
- ``GET/POST/DELETE /sites/{id}/assets`` — rutas de evacuación / punto de
  reunión / manual (S3 presignado; gestión = ``manage_fleet``).
- ``POST/GET/DELETE /sites/{id}/enrollment-codes`` — códigos de alta
  (``enrollment_manage``).
- ``GET /sites/{id}/drills``            — activo (banner) + próximo (agenda
  D4c, informativa) + último ejecutado.

Alcance: ``assert_site_access`` (R2) — el occupant solo ve el sitio donde está
ENROLADO; el resto por ``site_scope`` del claim. RLS acota el tenant SIEMPRE.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.audit import audit_async
from takab_api.auth.claims import Claims
from takab_api.auth.deps import get_claims, get_session, require_roles
from takab_api.auth.matrix import roles_with_action
from takab_api.queries import mobile as q
from takab_api.routers._common import http_error, integrity_error
from takab_api.routers._s3 import presign_get, presign_put
from takab_api.schemas.fleet import DEGRADADO, OPERATIVO, SIN_ENLACE, derive_fleet_state
from takab_api.schemas.mobile import (
    DirectoryEntryOut,
    EnrollmentCodeIn,
    EnrollmentCodeOut,
    MobileDrillOut,
    MobileIncidentOut,
    MobileReentryOut,
    MobileSiteHealthOut,
    MobileStateOut,
    MobileZoneOut,
    Phase,
    SiteAssetCreateIn,
    SiteAssetCreateOut,
    SiteAssetOut,
)
from takab_api.settings import Settings

_ENROLLMENT_ROLES = roles_with_action("enrollment_manage")
_FLEET_ROLES = roles_with_action("manage_fleet")

_require_enrollment_admin = require_roles(*_ENROLLMENT_ROLES)
_require_fleet = require_roles(*_FLEET_ROLES)

router = APIRouter()

# Dictamen HABITABLE: libera el reingreso (spec §7 · 2.7 "HABITAR").
_HABITABLE = frozenset({"normal_operation", "inhabit_monitor"})


async def _site_health(
    conn: AsyncConnection, site_id: UUID, settings: Settings
) -> MobileSiteHealthOut:
    """Salud agregada del sitio: cada gabinete se deriva con la verdad única de
    Flota (`derive_fleet_state`, mismos umbrales) y gana el PEOR. Sin gabinetes
    ⇒ SIN ENLACE honesto (no hay quién proteja el edificio)."""
    rows = (await conn.execute(q.SITE_HEALTH, {"site": str(site_id)})).all()
    worst = SIN_ENLACE
    heartbeat_at = None
    age_s: float | None = None
    has_wr1 = False
    rank = {OPERATIVO: 0, DEGRADADO: 1, SIN_ENLACE: 2}
    if rows:
        states = []
        for r in rows:
            has_wr1 = has_wr1 or bool(r.has_wr1)
            states.append(
                derive_fleet_state(
                    age_s=r.age_s,
                    power_status=r.power_status,
                    battery_pct=r.battery_pct,
                    cert_days_remaining=r.cert_days_remaining,
                    mqtt_rtt_ms=r.mqtt_rtt_ms,
                    seedlink_lag_s=r.seedlink_lag_s,
                    ntp_offset_ms=r.ntp_offset_ms,
                    sin_enlace_s=settings.sin_enlace_min * 60.0,
                    battery_min_pct=settings.fleet_battery_min_pct,
                    cert_min_days=settings.fleet_cert_min_days,
                    mqtt_rtt_max_ms=settings.fleet_mqtt_rtt_max_ms,
                    seedlink_lag_max_s=settings.fleet_seedlink_lag_max_s,
                    ntp_offset_max_ms=settings.fleet_ntp_offset_max_ms,
                )
            )
            if r.health_ts is not None and (heartbeat_at is None or r.health_ts > heartbeat_at):
                heartbeat_at = r.health_ts
                age_s = r.age_s
        worst = max(states, key=lambda s: rank[s])
    return MobileSiteHealthOut(
        status=worst, heartbeat_at=heartbeat_at, age_s=age_s, has_wr1=has_wr1
    )


def _asset_out(row: Any, settings: Settings) -> SiteAssetOut:
    """Fila → asset con URL presignada (o None si es textual/sin bucket)."""
    url: str | None = None
    if row.s3_key and settings.evidence_bucket:
        url = presign_get(settings, row.s3_key)
    return SiteAssetOut(
        asset_id=row.asset_id,
        kind=row.kind,
        title=row.title,
        description=row.description,
        zone_id=row.zone_id,
        content_type=row.content_type,
        url=url,
        updated_at=row.updated_at,
    )


@router.get("/sites/{site_id}/mobile-state", response_model=MobileStateOut)
async def mobile_state(
    site_id: UUID,
    claims: Claims = Depends(get_claims),
    conn: AsyncConnection = Depends(get_session),
) -> MobileStateOut:
    """Estado consolidado del sitio para la app (push = despertador; ESTO es la
    verdad). Derivación de ``phase`` documentada en el schema."""
    site = await q.assert_site_access(conn, claims, site_id)
    settings = Settings()

    incident_row = (await conn.execute(q.OPEN_INCIDENT, {"site": str(site_id)})).first()
    tier_row = (await conn.execute(q.LATEST_TIER, {"site": str(site_id)})).first()
    latest_tier = tier_row.new_tier if tier_row else None

    incident: MobileIncidentOut | None = None
    dictamen_status: str | None = None
    dictamen_signed = False
    phase: Phase = "idle"
    if incident_row is not None:
        incident = MobileIncidentOut(
            incident_id=incident_row.incident_id,
            trigger=incident_row.trigger,
            severity=incident_row.severity,
            state=incident_row.state,
            opened_at=incident_row.opened_at,
            node_count=incident_row.node_count,
            max_pga_g=incident_row.max_pga_g,
        )
        dictamen_row = (
            await conn.execute(q.LATEST_DICTAMEN, {"incident": str(incident_row.incident_id)})
        ).first()
        if dictamen_row is not None:
            dictamen_status = dictamen_row.status
            dictamen_signed = dictamen_row.signed_by is not None
        if dictamen_signed and dictamen_status in _HABITABLE:
            phase = "reentry_approved"
        elif latest_tier == "normal":
            phase = "shaking_concluded"
        else:
            phase = "alert_active"

    my_zone: MobileZoneOut | None = None
    assignment = await q.my_assignment(conn, claims.sub, site_id)
    if assignment is not None and assignment.zone_id is not None:
        my_zone = MobileZoneOut(
            zone_id=assignment.zone_id,
            name=assignment.zone_name or "",
            level_code=assignment.level_code,
            evac_policy=assignment.evac_policy,
        )

    labels_row = (await conn.execute(q.COMPLIANCE_LABELS, {"tenant": str(site.tenant_id)})).first()
    assembly_row = (await conn.execute(q.ASSEMBLY_POINT, {"site": str(site_id)})).first()

    drill_active = (
        await conn.execute(q.ACTIVE_DRILL_FOR_SITE, {"site": str(site_id)})
    ).first() is not None
    next_row = (await conn.execute(q.NEXT_SCHEDULED_DRILL)).first()
    last_row = (await conn.execute(q.LAST_DRILL_FOR_SITE, {"site": str(site_id)})).first()

    return MobileStateOut(
        site_id=site.site_id,
        site_name=site.name,
        server_ts=datetime.now(tz=UTC),
        phase=phase,
        incident=incident,
        latest_tier=latest_tier,
        my_zone=my_zone,
        reentry=MobileReentryOut(
            blocked=incident is not None and phase != "reentry_approved",
            dictamen_status=dictamen_status,
            dictamen_signed=dictamen_signed,
        ),
        assembly_point=_asset_out(assembly_row, settings) if assembly_row else None,
        compliance_labels=dict(labels_row.labels) if labels_row else {},
        drill=MobileDrillOut(
            active=drill_active,
            next_scheduled_at=next_row.scheduled_at if next_row else None,
            last_started_at=last_row.started_at if last_row else None,
            last_note=last_row.note if last_row else None,
        ),
        site_health=await _site_health(conn, site_id, settings),
    )


@router.get("/sites/{site_id}/directory", response_model=list[DirectoryEntryOut])
async def site_directory(
    site_id: UUID,
    claims: Claims = Depends(get_claims),
    conn: AsyncConnection = Depends(get_session),
) -> list[DirectoryEntryOut]:
    """[T-2.07 · 1.7] Directorio de emergencia del sitio: brigadistas,
    seguridad y administración con teléfono de un toque. Es el roster PÚBLICO
    del inmueble (publicación deliberada dentro del sitio — no audita por
    lectura, regla de logging por evento); los occupants jamás se listan."""
    await q.assert_site_access(conn, claims, site_id)
    rows = (await conn.execute(q.SITE_DIRECTORY, {"site": str(site_id)})).all()
    return [DirectoryEntryOut(**dict(r._mapping)) for r in rows]


@router.get("/sites/{site_id}/assets", response_model=list[SiteAssetOut])
async def list_site_assets(
    site_id: UUID,
    claims: Claims = Depends(get_claims),
    conn: AsyncConnection = Depends(get_session),
) -> list[SiteAssetOut]:
    """Assets del sitio con URL presignada de descarga (cacheables offline)."""
    await q.assert_site_access(conn, claims, site_id)
    settings = Settings()
    rows = (await conn.execute(q.LIST_ASSETS, {"site": str(site_id)})).all()
    return [_asset_out(r, settings) for r in rows]


@router.post("/sites/{site_id}/assets", response_model=SiteAssetCreateOut, status_code=201)
async def create_site_asset(
    site_id: UUID,
    body: SiteAssetCreateIn,
    claims: Claims = Depends(_require_fleet),
    conn: AsyncConnection = Depends(get_session),
) -> SiteAssetCreateOut:
    """Registra un asset; con ``with_file`` devuelve además la URL PUT presignada
    (la subida es directa del cliente a S3 — sin credenciales AWS en la app)."""
    site = await q.site_or_404(conn, site_id)
    settings = Settings()

    s3_key: str | None = None
    upload_url: str | None = None
    if body.with_file:
        if not settings.evidence_bucket:
            raise http_error(503, "bucket de evidencia no configurado")
        s3_key = f"assets/{site.tenant_id}/{site_id}/{uuid4().hex}"
        upload_url = presign_put(settings, s3_key, content_type=body.content_type)

    try:
        row = (
            await conn.execute(
                q.INSERT_ASSET,
                {
                    "tenant": str(site.tenant_id),
                    "site": str(site_id),
                    "zone": str(body.zone_id) if body.zone_id else None,
                    "kind": body.kind,
                    "title": body.title,
                    "description": body.description,
                    "s3_key": s3_key,
                    "content_type": body.content_type,
                    "by": claims.sub,
                },
            )
        ).first()
    except IntegrityError as exc:
        raise integrity_error(exc) from exc

    await audit_async(
        conn,
        tenant_id=str(site.tenant_id),
        actor=f"user:{claims.sub}",
        verb="site_asset_create",
        obj=f"asset:{row.asset_id}",
        meta={"kind": body.kind, "with_file": body.with_file},
    )
    return SiteAssetCreateOut(asset=_asset_out(row, settings), upload_url=upload_url)


@router.delete("/sites/{site_id}/assets/{asset_id}", status_code=204)
async def delete_site_asset(
    site_id: UUID,
    asset_id: UUID,
    claims: Claims = Depends(_require_fleet),
    conn: AsyncConnection = Depends(get_session),
) -> None:
    site = await q.site_or_404(conn, site_id)
    row = (await conn.execute(q.DELETE_ASSET, {"id": str(asset_id), "site": str(site_id)})).first()
    if row is None:
        raise http_error(404, "asset no encontrado")
    await audit_async(
        conn,
        tenant_id=str(site.tenant_id),
        actor=f"user:{claims.sub}",
        verb="site_asset_delete",
        obj=f"asset:{asset_id}",
        meta={},
    )


@router.post("/sites/{site_id}/enrollment-codes", response_model=EnrollmentCodeOut, status_code=201)
async def create_enrollment_code(
    site_id: UUID,
    body: EnrollmentCodeIn,
    claims: Claims = Depends(_require_enrollment_admin),
    conn: AsyncConnection = Depends(get_session),
) -> EnrollmentCodeOut:
    """Alta de un código de enrolamiento (siempre ``grants_role='occupant'``,
    CHECK de DB). Vigencia/usos acotan el abuso (RBAC §4.1)."""
    site = await q.site_or_404(conn, site_id)
    try:
        row = (
            await conn.execute(
                q.INSERT_CODE_FULL,
                {
                    "code": body.code,
                    "tenant": str(site.tenant_id),
                    "site": str(site_id),
                    "zone": str(body.zone_id) if body.zone_id else None,
                    "expires_at": body.expires_at,
                    "max_uses": body.max_uses,
                },
            )
        ).first()
    except IntegrityError as exc:
        raise integrity_error(exc) from exc
    await audit_async(
        conn,
        tenant_id=str(site.tenant_id),
        actor=f"user:{claims.sub}",
        verb="enrollment_code_create",
        obj=f"site:{site_id}",
        meta={"code": body.code, "max_uses": body.max_uses},
    )
    return EnrollmentCodeOut(**dict(row._mapping))


@router.get("/sites/{site_id}/enrollment-codes", response_model=list[EnrollmentCodeOut])
async def list_enrollment_codes(
    site_id: UUID,
    claims: Claims = Depends(_require_enrollment_admin),
    conn: AsyncConnection = Depends(get_session),
) -> list[EnrollmentCodeOut]:
    await q.site_or_404(conn, site_id)
    rows = (await conn.execute(q.LIST_CODES, {"site": str(site_id)})).all()
    return [EnrollmentCodeOut(**dict(r._mapping)) for r in rows]


@router.delete("/sites/{site_id}/enrollment-codes/{code}", status_code=204)
async def deactivate_enrollment_code(
    site_id: UUID,
    code: str,
    claims: Claims = Depends(_require_enrollment_admin),
    conn: AsyncConnection = Depends(get_session),
) -> None:
    """Desactiva (no borra: el historial de usos es auditable)."""
    site = await q.site_or_404(conn, site_id)
    row = (await conn.execute(q.DEACTIVATE_CODE, {"code": code, "site": str(site_id)})).first()
    if row is None:
        raise http_error(404, "código no encontrado")
    await audit_async(
        conn,
        tenant_id=str(site.tenant_id),
        actor=f"user:{claims.sub}",
        verb="enrollment_code_deactivate",
        obj=f"site:{site_id}",
        meta={"code": code},
    )


@router.get("/sites/{site_id}/drills", response_model=MobileDrillOut)
async def site_drills(
    site_id: UUID,
    claims: Claims = Depends(get_claims),
    conn: AsyncConnection = Depends(get_session),
) -> MobileDrillOut:
    """Simulacros del sitio para la card de 1.1: activo + próximo + último."""
    await q.assert_site_access(conn, claims, site_id)
    active = (
        await conn.execute(q.ACTIVE_DRILL_FOR_SITE, {"site": str(site_id)})
    ).first() is not None
    next_row = (await conn.execute(q.NEXT_SCHEDULED_DRILL)).first()
    last_row = (await conn.execute(q.LAST_DRILL_FOR_SITE, {"site": str(site_id)})).first()
    return MobileDrillOut(
        active=active,
        next_scheduled_at=next_row.scheduled_at if next_row else None,
        last_started_at=last_row.started_at if last_row else None,
        last_note=last_row.note if last_row else None,
    )
