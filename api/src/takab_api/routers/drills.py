"""Simulacro institucional (T-1.60 · cierra M-1): drill_start firmado a N sitios.

Un simulacro JAMÁS toca ``incidents`` ni relés: en cada gabinete pinta el
banner "SIMULACRO — NO ES REAL" del panel LAN y (si hay hardware de audio)
vocea el mensaje de simulacro. La emisión reutiliza ``issue_signed_command``
(regla de oro 8, superficie única); el acuse por sitio se deriva por JOIN al
comando — el registro completo es la evidencia para Protección Civil (gov LEE
por RLS, no escribe). Una alerta real ABORTA el drill en el edge; aquí solo se
registra el fin (`stop`) o se deja vencer la ventana (estado derivado).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.audit import audit_async
from takab_api.auth.claims import Claims, scope_filter
from takab_api.auth.deps import get_session, require_roles
from takab_api.auth.matrix import roles_with_action
from takab_api.commands.keys import CommandKeyProvider
from takab_api.commands.publisher import CommandPublisher
from takab_api.commands.service import issue_signed_command
from takab_api.routers._common import http_error
from takab_api.routers.commands import get_key_provider, get_publisher
from takab_api.routers.incidents import CONSOLE_ROLES
from takab_api.schemas.drills import (
    ActiveDrillOut,
    DrillCreateIn,
    DrillList,
    DrillOut,
    DrillSiteOut,
)
from takab_api.settings import Settings

DRILL_ROLES: tuple[str, ...] = roles_with_action("drill_start")

_require_drill = require_roles(*DRILL_ROLES)
# Lectura: cualquier rol con Consola C4I — el banner lo ven todos los del SOC y
# gov_operator LEE el registro (evidencia para Protección Civil; RLS acota).
_require_console = require_roles(*CONSOLE_ROLES)

router = APIRouter()

# Sitios del tenant con gateway comandable (RLS acota al tenant del token).
_COMMANDABLE_SITES = text(
    "SELECT s.site_id, s.tenant_id FROM sites s WHERE EXISTS ("
    "  SELECT 1 FROM gateways g WHERE g.site_id = s.site_id"
    "  AND g.status <> 'retired' AND g.iot_thing IS NOT NULL)"
    " ORDER BY s.site_id"
)

_INSERT_DRILL = text(
    "INSERT INTO drills (tenant_id, initiated_by, note, duration_s) "
    "VALUES (CAST(:tenant AS uuid), CAST(:user_id AS uuid), :note, :duration) "
    "RETURNING drill_id, tenant_id, initiated_by, note, duration_s, started_at, "
    "stopped_at, stop_reason, scheduled_at"
)

# [T-2.03·D4c] Fila de AGENDA: anuncio del "próximo simulacro" para la app.
# JAMÁS emite comandos ni deriva `active` — ejecutar el simulacro a esa hora
# sigue siendo un acto del operador (LO REAL GANA queda intacto).
_INSERT_DRILL_AGENDA = text(
    "INSERT INTO drills (tenant_id, initiated_by, note, duration_s, scheduled_at) "
    "VALUES (CAST(:tenant AS uuid), CAST(:user_id AS uuid), :note, :duration, "
    ":scheduled_at) "
    "RETURNING drill_id, tenant_id, initiated_by, note, duration_s, started_at, "
    "stopped_at, stop_reason, scheduled_at"
)

_INSERT_DRILL_SITE = text(
    "INSERT INTO drill_sites (drill_id, site_id, tenant_id, command_id) "
    "VALUES (CAST(:drill AS uuid), CAST(:site AS uuid), CAST(:tenant AS uuid), "
    "CAST(:command AS uuid))"
)

# active = DERIVADO: sin fin manual y dentro de la ventana (sin worker de cierre).
# Las filas de AGENDA (scheduled_at, T-2.03·D4c) jamás derivan activo.
_SELECT_DRILLS = text(
    "SELECT d.drill_id, d.tenant_id, d.initiated_by, d.note, d.duration_s, "
    "d.started_at, d.stopped_at, d.stop_reason, d.scheduled_at, "
    "(d.scheduled_at IS NULL AND d.stopped_at IS NULL "
    "AND now() < d.started_at + make_interval(secs => d.duration_s)) "
    "AS active "
    "FROM drills d ORDER BY d.started_at DESC LIMIT :limit"
)

_SELECT_DRILL = text(
    "SELECT d.drill_id, d.tenant_id, d.initiated_by, d.note, d.duration_s, "
    "d.started_at, d.stopped_at, d.stop_reason, d.scheduled_at, "
    "(d.scheduled_at IS NULL AND d.stopped_at IS NULL "
    "AND now() < d.started_at + make_interval(secs => d.duration_s)) "
    "AS active "
    "FROM drills d WHERE d.drill_id = CAST(:drill AS uuid)"
)

_SELECT_DRILL_SITES = text(
    "SELECT ds.drill_id, ds.site_id, s.name AS site_name, ds.command_id, "
    "c.status AS command_status, c.ack "
    "FROM drill_sites ds "
    "LEFT JOIN sites s ON s.site_id = ds.site_id "
    "LEFT JOIN commands c ON c.command_id = ds.command_id "
    "WHERE ds.drill_id = ANY(:drills) ORDER BY s.name NULLS LAST, ds.site_id"
)

_STOP_DRILL = text(
    "UPDATE drills SET stopped_at = :now, stop_reason = :reason "
    "WHERE drill_id = CAST(:drill AS uuid) AND stopped_at IS NULL "
    "RETURNING drill_id"
)


async def _sites_of(rows: Any, conn: AsyncConnection) -> dict[UUID, list[DrillSiteOut]]:
    ids = [r["drill_id"] for r in rows]
    if not ids:
        return {}
    site_rows = (await conn.execute(_SELECT_DRILL_SITES, {"drills": ids})).mappings().all()
    out: dict[UUID, list[DrillSiteOut]] = {i: [] for i in ids}
    for r in site_rows:
        out[r["drill_id"]].append(
            DrillSiteOut(
                site_id=r["site_id"],
                site_name=r["site_name"],
                command_id=r["command_id"],
                command_status=r["command_status"],
                ack=r["ack"],
            )
        )
    return out


def _drill_out(row: Any, sites: list[DrillSiteOut]) -> DrillOut:
    return DrillOut(**{**dict(row), "sites": sites})


@router.post("/drills", response_model=DrillOut, status_code=201)
async def start_drill(
    body: DrillCreateIn,
    claims: Claims = Depends(_require_drill),
    conn: AsyncConnection = Depends(get_session),
    publisher: CommandPublisher = Depends(get_publisher),
    keys: CommandKeyProvider = Depends(get_key_provider),
) -> DrillOut:
    """Inicia el simulacro: 1 comando firmado `drill_start` por sitio.

    [T-2.03·D4c] Con ``scheduled_at`` la fila es AGENDA (anuncio del "próximo
    simulacro" para la app): sin comandos, sin banner, jamás ``active``.
    """
    if body.scheduled_at is not None:
        if body.scheduled_at <= datetime.now(tz=UTC):
            raise http_error(422, "scheduled_at debe ser futuro")
        agenda = (
            (
                await conn.execute(
                    _INSERT_DRILL_AGENDA,
                    {
                        "tenant": claims.tenant_id,
                        "user_id": claims.sub,
                        "note": body.note,
                        "duration": body.duration_s,
                        "scheduled_at": body.scheduled_at,
                    },
                )
            )
            .mappings()
            .one()
        )
        await audit_async(
            conn,
            tenant_id=claims.tenant_id,
            actor=f"user:{claims.sub}",
            verb="drill_scheduled",
            obj=f"drill:{agenda['drill_id']}",
            meta={"scheduled_at": body.scheduled_at.isoformat()},
        )
        return _drill_out({**dict(agenda), "active": False}, [])

    settings = Settings()
    commandable = (await conn.execute(_COMMANDABLE_SITES)).mappings().all()
    by_id = {row["site_id"]: row for row in commandable}
    if body.site_ids is not None:
        missing = [str(s) for s in body.site_ids if s not in by_id]
        if missing:
            raise http_error(404, f"sitio(s) sin gateway comandable o no visibles: {missing}")
        targets = [by_id[s] for s in body.site_ids]
    else:
        targets = list(commandable)
    if not targets:
        raise http_error(409, "el tenant no tiene sitios con gateway comandable")
    scope = scope_filter(claims)
    if scope is not None:
        outside = [str(t["site_id"]) for t in targets if str(t["site_id"]) not in scope]
        if outside:
            raise http_error(403, f"sitio(s) fuera del alcance del usuario: {outside}")

    drill = (
        (
            await conn.execute(
                _INSERT_DRILL,
                {
                    "tenant": claims.tenant_id,
                    "user_id": claims.sub,
                    "note": body.note,
                    "duration": body.duration_s,
                },
            )
        )
        .mappings()
        .one()
    )
    drill_id = drill["drill_id"]

    sites: list[DrillSiteOut] = []
    for target in targets:
        command_id: UUID | None = None
        command_status: str | None = None
        # Best-effort POR SITIO: un gabinete sin clave/publicación no aborta el
        # drill de los demás — queda registrado SIN comando (evidencia honesta).
        try:
            row = await issue_signed_command(
                conn,
                settings=settings,
                publisher=publisher,
                keys=keys,
                claims=claims,
                site_id=target["site_id"],
                tenant_id=str(target["tenant_id"]),
                channel="system",
                action="drill_start",
                event_id=f"DRILL-{drill_id}",
                payload_extra={"duration_s": body.duration_s},
            )
            command_id, command_status = row["command_id"], row["status"]
        except Exception:  # noqa: BLE001 — best-effort por sitio, registrado como NULL
            command_id, command_status = None, None
        await conn.execute(
            _INSERT_DRILL_SITE,
            {
                "drill": drill_id,
                "site": target["site_id"],
                "tenant": claims.tenant_id,
                "command": str(command_id) if command_id else None,
            },
        )
        sites.append(
            DrillSiteOut(
                site_id=target["site_id"],
                site_name=None,
                command_id=command_id,
                command_status=command_status,
                ack=None,
            )
        )

    await audit_async(
        conn,
        tenant_id=claims.tenant_id,
        actor=f"user:{claims.sub}",
        verb="drill_started",
        obj=f"drill:{drill_id}",
        meta={"sites": len(sites), "duration_s": body.duration_s},
    )
    return _drill_out({**dict(drill), "active": True}, sites)


@router.get("/drills", response_model=DrillList, dependencies=[Depends(_require_console)])
async def list_drills(conn: AsyncConnection = Depends(get_session)) -> DrillList:
    """Registro de simulacros con acuse por sitio (evidencia de cumplimiento)."""
    rows = (await conn.execute(_SELECT_DRILLS, {"limit": 50})).mappings().all()
    sites = await _sites_of(rows, conn)
    return DrillList(items=[_drill_out(r, sites.get(r["drill_id"], [])) for r in rows])


@router.get(
    "/drills/active", response_model=ActiveDrillOut, dependencies=[Depends(_require_console)]
)
async def active_drill(conn: AsyncConnection = Depends(get_session)) -> ActiveDrillOut:
    """El drill vivo del tenant (banner de la consola). Cualquier rol web lo ve."""
    rows = (await conn.execute(_SELECT_DRILLS, {"limit": 10})).mappings().all()
    live = [r for r in rows if r["active"]]
    if not live:
        return ActiveDrillOut(drill=None)
    sites = await _sites_of(live[:1], conn)
    return ActiveDrillOut(drill=_drill_out(live[0], sites.get(live[0]["drill_id"], [])))


@router.post("/drills/{drill_id}/stop", response_model=DrillOut)
async def stop_drill(
    drill_id: UUID,
    claims: Claims = Depends(_require_drill),
    conn: AsyncConnection = Depends(get_session),
    publisher: CommandPublisher = Depends(get_publisher),
    keys: CommandKeyProvider = Depends(get_key_provider),
) -> DrillOut:
    """Termina el simulacro antes de la ventana y avisa a los gabinetes."""
    settings = Settings()
    now = datetime.now(tz=UTC)
    stopped = (
        await conn.execute(_STOP_DRILL, {"drill": str(drill_id), "now": now, "reason": "manual"})
    ).first()
    row = (await conn.execute(_SELECT_DRILL, {"drill": str(drill_id)})).mappings().first()
    if row is None:
        raise http_error(404, "simulacro no encontrado")
    # `stopped is None` = ya estaba parado: idempotente, se devuelve tal cual.
    sites_map = await _sites_of([row], conn)
    sites = sites_map.get(row["drill_id"], [])
    if stopped is not None:
        # drill_stop best-effort a los sitios que SÍ recibieron el start.
        for site in sites:
            if site.command_id is None:
                continue
            try:
                await issue_signed_command(
                    conn,
                    settings=settings,
                    publisher=publisher,
                    keys=keys,
                    claims=claims,
                    site_id=site.site_id,
                    tenant_id=str(row["tenant_id"]),
                    channel="system",
                    action="drill_stop",
                    event_id=f"DRILL-{drill_id}",
                    now=now,
                )
            except Exception:  # noqa: BLE001 — el fin de ventana del edge es el respaldo
                continue
        await audit_async(
            conn,
            tenant_id=str(row["tenant_id"]),
            actor=f"user:{claims.sub}",
            verb="drill_stopped",
            obj=f"drill:{drill_id}",
        )
    return _drill_out(row, sites)
