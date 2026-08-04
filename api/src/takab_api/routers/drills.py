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
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import TextClause, text
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.audit import audit_async
from takab_api.auth.claims import Claims, scope_filter
from takab_api.auth.deps import get_session, require_roles
from takab_api.auth.matrix import roles_with_action
from takab_api.commands.keys import CommandKeyProvider
from takab_api.commands.publisher import CommandPublisher
from takab_api.commands.service import issue_signed_command
from takab_api.routers._common import (
    clamp_limit,
    decode_cursor,
    encode_cursor,
    http_error,
)
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
# Lectura: cualquier rol con MONITOREO — el banner lo ven todos los del SOC y
# gov_operator LEE el registro (evidencia para Protección Civil; RLS acota).
_require_console = require_roles(*CONSOLE_ROLES)

router = APIRouter()

# Sitios del tenant con gateway comandable (RLS acota al tenant del token).
_COMMANDABLE = (
    "EXISTS (SELECT 1 FROM gateways g WHERE g.site_id = %(alias)s.site_id"
    " AND g.status <> 'retired' AND g.iot_thing IS NOT NULL)"
)

_COMMANDABLE_SITES = text(
    "SELECT s.site_id, s.tenant_id FROM sites s WHERE "
    + (_COMMANDABLE % {"alias": "s"})
    + " ORDER BY s.site_id"
)

# [T-2.48] Sitios VIVOS del tenant, comandables o no: a lo que puede apuntar una
# AGENDA. Un simulacro se programa semanas antes — exigir gabinete al agendar
# impediría planear el simulacro del edificio cuyo gabinete se instala el jueves.
_TENANT_SITES = text(
    "SELECT s.site_id, s.tenant_id, s.name, "
    + (_COMMANDABLE % {"alias": "s"})
    + " AS commandable FROM sites s WHERE s.status <> 'retired' ORDER BY s.site_id"
)

# [T-2.48] A qué sitios apuntaba una agenda: es lo que precarga el botón
# EJECUTAR AHORA del banner armado.
_SELECT_AGENDA_SITES = text(
    "SELECT ds.site_id FROM drill_sites ds WHERE ds.drill_id = CAST(:drill AS uuid) "
    "ORDER BY ds.site_id"
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
_DRILL_COLS = (
    "d.drill_id, d.tenant_id, d.initiated_by, d.note, d.duration_s, "
    "d.started_at, d.stopped_at, d.stop_reason, d.scheduled_at, "
    "(d.scheduled_at IS NULL AND d.stopped_at IS NULL "
    "AND now() < d.started_at + make_interval(secs => d.duration_s)) AS active"
)

_SELECT_ACTIVE = text(
    f"SELECT {_DRILL_COLS} FROM drills d "
    "WHERE d.scheduled_at IS NULL AND d.stopped_at IS NULL "
    "AND now() < d.started_at + make_interval(secs => d.duration_s) "
    "ORDER BY d.started_at DESC, d.drill_id DESC LIMIT 1"
)

_SELECT_DRILL = text(f"SELECT {_DRILL_COLS} FROM drills d WHERE d.drill_id = CAST(:drill AS uuid)")

# [T-2.48] `commandable` se evalúa AL LEER: ``drill_sites`` no tiene dónde
# congelarlo y esta tarea es aditiva (sin DDL). Es la diferencia entre "no había
# a quién mandarle el simulacro" y "el sitio no acusó" — dos hechos que la
# pantalla NO puede colapsar (regla de oro 7).
_SELECT_DRILL_SITES = text(
    "SELECT ds.drill_id, ds.site_id, s.name AS site_name, ds.command_id, "
    "c.status AS command_status, c.ack, " + (_COMMANDABLE % {"alias": "ds"}) + " AS commandable "
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

# [T-2.48] Cancelar SOLO toca una agenda todavía pendiente. El doble guardia
# (`scheduled_at IS NOT NULL AND stopped_at IS NULL`) es lo que impide reescribir
# el motivo de un simulacro que ya ocurrió: la evidencia de que sonó en los
# edificios no se "descancela" (regla de oro 11).
_CANCEL_DRILL = text(
    "UPDATE drills SET stopped_at = :now, stop_reason = 'cancelled' "
    "WHERE drill_id = CAST(:drill AS uuid) "
    "AND scheduled_at IS NOT NULL AND stopped_at IS NULL "
    "RETURNING drill_id"
)

_KINDS: dict[str, str] = {
    "executed": "d.scheduled_at IS NULL",
    "scheduled": "d.scheduled_at IS NOT NULL",
}


def _select_drills_page(
    *, kind: str, cursor: tuple[str, str] | None, limit: int
) -> tuple[TextClause, dict[str, Any]]:
    """Página keyset del registro, ordenada por ``(started_at, drill_id)`` desc.

    El desempate por ``drill_id`` no es cosmético: sin él dos simulacros creados
    en el mismo milisegundo (una agenda y su ejecución, p. ej.) podrían repetirse
    o perderse al pasar de página.
    """
    where: list[str] = []
    params: dict[str, Any] = {"limit": limit}
    if kind in _KINDS:
        where.append(_KINDS[kind])
    if cursor is not None:
        where.append(
            "(d.started_at, d.drill_id) < (CAST(:cur_ts AS timestamptz), CAST(:cur_id AS uuid))"
        )
        params["cur_ts"], params["cur_id"] = cursor
    clause = f" WHERE {' AND '.join(where)}" if where else ""
    return (
        text(
            f"SELECT {_DRILL_COLS} FROM drills d{clause} "
            "ORDER BY d.started_at DESC, d.drill_id DESC LIMIT :limit"
        ),
        params,
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
                commandable=bool(r["commandable"]),
            )
        )
    return out


def _drill_out(row: Any, sites: list[DrillSiteOut]) -> DrillOut:
    return DrillOut(**{**dict(row), "sites": sites})


def _require_scope(claims: Claims, site_ids: list[Any]) -> None:
    """403 si el usuario tiene ``site_scope`` y algún sitio queda fuera."""
    scope = scope_filter(claims)
    if scope is None:
        return
    outside = [str(s) for s in site_ids if str(s) not in scope]
    if outside:
        raise http_error(403, f"sitio(s) fuera del alcance del usuario: {outside}")


async def _schedule_drill(body: DrillCreateIn, claims: Claims, conn: AsyncConnection) -> DrillOut:
    """[T-2.03·D4c + T-2.48] Fila de AGENDA: anuncio, jamás comandos.

    Desde T-2.48 deja constancia de **a qué sitios apunta** (``drill_sites`` con
    ``command_id NULL``). Sin eso un simulacro programado no dice a quién iba
    dirigido: ni el banner armado puede precargar el botón, ni el registro sirve
    de evidencia de a quién se planeó avisar.

    Una agenda SÍ puede apuntar a un sitio sin gabinete comandable: se programa
    semanas antes y el hardware puede llegar en medio. La ausencia de comando de
    ese sitio queda rotulada aparte (``commandable``), nunca como "no acusó".
    """
    if body.scheduled_at is None or body.scheduled_at <= datetime.now(tz=UTC):
        raise http_error(422, "scheduled_at debe ser futuro")
    rows = (await conn.execute(_TENANT_SITES)).mappings().all()
    by_id = {row["site_id"]: row for row in rows}
    if body.site_ids is not None:
        missing = [str(s) for s in body.site_ids if s not in by_id]
        if missing:
            raise http_error(404, f"sitio(s) no visibles o retirados: {missing}")
        targets = [by_id[s] for s in body.site_ids]
    else:
        # Sin lista explícita se apunta a lo comandable HOY (mismo default que la
        # ejecución). Puede quedar vacío: agendar antes de instalar es legítimo.
        targets = [row for row in rows if row["commandable"]]
    _require_scope(claims, [t["site_id"] for t in targets])

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
    for target in targets:
        await conn.execute(
            _INSERT_DRILL_SITE,
            {
                "drill": agenda["drill_id"],
                "site": target["site_id"],
                "tenant": claims.tenant_id,
                "command": None,
            },
        )
    await audit_async(
        conn,
        tenant_id=claims.tenant_id,
        actor=f"user:{claims.sub}",
        verb="drill_scheduled",
        obj=f"drill:{agenda['drill_id']}",
        meta={"scheduled_at": body.scheduled_at.isoformat(), "sites": len(targets)},
    )
    return _drill_out(
        {**dict(agenda), "active": False},
        [
            DrillSiteOut(
                site_id=t["site_id"],
                site_name=t["name"],
                command_id=None,
                command_status=None,
                ack=None,
                commandable=bool(t["commandable"]),
            )
            for t in targets
        ],
    )


async def _armed_drill(from_scheduled: UUID, conn: AsyncConnection) -> Any:
    """La agenda que se va a ejecutar, o 404/409 con la razón exacta."""
    row = (await conn.execute(_SELECT_DRILL, {"drill": str(from_scheduled)})).mappings().first()
    if row is None:
        raise http_error(404, "simulacro programado no encontrado")
    if row["scheduled_at"] is None:
        raise http_error(409, "ese simulacro no está programado (no es una agenda)")
    if row["stopped_at"] is not None:
        raise http_error(409, f"el simulacro programado ya está cerrado: {row['stop_reason']}")
    return row


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

    [T-2.48] Con ``from_scheduled`` se EJECUTA una agenda ya armada, heredando
    sus sitios/duración/nota, y la agenda queda consumida. Sigue siendo un clic
    humano en una sesión viva: aquí no hay temporizador que dispare nada — un
    actuador que se activa solo por reloj rompería la regla de oro 8.
    """
    if body.scheduled_at is not None:
        if body.from_scheduled is not None:
            raise http_error(422, "scheduled_at y from_scheduled son excluyentes")
        return await _schedule_drill(body, claims, conn)

    armed = None if body.from_scheduled is None else await _armed_drill(body.from_scheduled, conn)

    settings = Settings()
    commandable = (await conn.execute(_COMMANDABLE_SITES)).mappings().all()
    by_id = {row["site_id"]: row for row in commandable}
    # Sitios apuntados por la agenda que HOY no tienen gabinete comandable: se
    # registran sin comando en vez de abortar. La lista se eligió semanas antes;
    # que un edificio perdiera el enlace no puede dejar sin simulacro a los otros.
    unreachable: list[Any] = []
    planned: list[Any] | None = body.site_ids
    if planned is None and armed is not None:
        planned = [
            r["site_id"]
            for r in (await conn.execute(_SELECT_AGENDA_SITES, {"drill": str(armed["drill_id"])}))
            .mappings()
            .all()
        ]
    if body.site_ids is not None:
        missing = [str(s) for s in body.site_ids if s not in by_id]
        if missing:
            raise http_error(404, f"sitio(s) sin gateway comandable o no visibles: {missing}")
        targets = [by_id[s] for s in body.site_ids]
    elif planned is not None:
        targets = [by_id[s] for s in planned if s in by_id]
        unreachable = [s for s in planned if s not in by_id]
    else:
        targets = list(commandable)
    if not targets:
        raise http_error(409, "el tenant no tiene sitios con gateway comandable")
    _require_scope(claims, [t["site_id"] for t in targets] + unreachable)

    duration, note = body.duration_s, body.note
    if armed is not None:
        # "Precargado" de verdad: sin campos explícitos manda lo que se programó.
        if "duration_s" not in body.model_fields_set:
            duration = armed["duration_s"]
        if "note" not in body.model_fields_set:
            note = armed["note"]

    drill = (
        (
            await conn.execute(
                _INSERT_DRILL,
                {
                    "tenant": claims.tenant_id,
                    "user_id": claims.sub,
                    "note": note,
                    "duration": duration,
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
                payload_extra={"duration_s": duration},
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
                commandable=True,
            )
        )

    for site_id in unreachable:
        await conn.execute(
            _INSERT_DRILL_SITE,
            {
                "drill": drill_id,
                "site": site_id,
                "tenant": claims.tenant_id,
                "command": None,
            },
        )
        sites.append(
            DrillSiteOut(
                site_id=site_id,
                site_name=None,
                command_id=None,
                command_status=None,
                ack=None,
                commandable=False,
            )
        )

    await audit_async(
        conn,
        tenant_id=claims.tenant_id,
        actor=f"user:{claims.sub}",
        verb="drill_started",
        obj=f"drill:{drill_id}",
        meta={
            "sites": len(sites),
            "duration_s": duration,
            "unreachable": len(unreachable),
            **({} if armed is None else {"from_scheduled": str(armed["drill_id"])}),
        },
    )
    if armed is not None:
        # Consumir la agenda es lo que apaga el banner armado. Sin esto la
        # consola seguiría anunciando un simulacro que ya ocurrió: un rótulo
        # falso en pantalla es exactamente lo que prohíbe la regla de oro 7.
        await conn.execute(
            _STOP_DRILL,
            {"drill": str(armed["drill_id"]), "now": datetime.now(tz=UTC), "reason": "executed"},
        )
        await audit_async(
            conn,
            tenant_id=claims.tenant_id,
            actor=f"user:{claims.sub}",
            verb="drill_executed",
            obj=f"drill:{armed['drill_id']}",
            meta={"drill_id": str(drill_id)},
        )
    return _drill_out({**dict(drill), "active": True}, sites)


@router.get("/drills", response_model=DrillList, dependencies=[Depends(_require_console)])
async def list_drills(
    conn: AsyncConnection = Depends(get_session),
    kind: Literal["all", "executed", "scheduled"] = Query("all"),
    cursor: str | None = Query(None),
    limit: int | None = Query(None),
) -> DrillList:
    """Registro de simulacros con acuse por sitio (evidencia de cumplimiento).

    [T-2.48] Paginación keyset y filtro por tipo: ``executed`` es lo que sonó en
    los edificios, ``scheduled`` la agenda (de ahí sale el banner armado).
    """
    size = clamp_limit(limit)
    cur = decode_cursor(cursor) if cursor is not None else None
    stmt, params = _select_drills_page(kind=kind, cursor=cur, limit=size + 1)
    rows = (await conn.execute(stmt, params)).mappings().all()

    next_cursor = None
    if len(rows) > size:
        rows = rows[:size]
        last = rows[-1]
        next_cursor = encode_cursor(last["started_at"].isoformat(), str(last["drill_id"]))

    sites = await _sites_of(rows, conn)
    return DrillList(
        items=[_drill_out(r, sites.get(r["drill_id"], [])) for r in rows],
        next_cursor=next_cursor,
    )


@router.get(
    "/drills/active", response_model=ActiveDrillOut, dependencies=[Depends(_require_console)]
)
async def active_drill(conn: AsyncConnection = Depends(get_session)) -> ActiveDrillOut:
    """El drill vivo del tenant (banner de la consola). Cualquier rol web lo ve."""
    live = (await conn.execute(_SELECT_ACTIVE)).mappings().first()
    if live is None:
        return ActiveDrillOut(drill=None)
    sites = await _sites_of([live], conn)
    return ActiveDrillOut(drill=_drill_out(live, sites.get(live["drill_id"], [])))


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


@router.post("/drills/{drill_id}/cancel", response_model=DrillOut)
async def cancel_drill(
    drill_id: UUID,
    claims: Claims = Depends(_require_drill),
    conn: AsyncConnection = Depends(get_session),
) -> DrillOut:
    """[T-2.48] Cancela un simulacro PROGRAMADO antes de que se ejecute.

    Solo aplica a la agenda. Un simulacro que ya corrió no se cancela: sonó en
    edificios reales y el registro es evidencia de cumplimiento — marcarlo
    "cancelado" después reescribiría un hecho (regla de oro 11). Para ese caso
    existe ``/stop``, que cierra la ventana sin negar que ocurrió.

    Idempotente y sin emitir nada: una agenda ya cerrada (cancelada o ejecutada)
    se devuelve TAL CUAL, conservando su ``stop_reason`` original.
    """
    row = (await conn.execute(_SELECT_DRILL, {"drill": str(drill_id)})).mappings().first()
    if row is None:
        raise http_error(404, "simulacro no encontrado")
    if row["scheduled_at"] is None:
        raise http_error(409, "un simulacro ya ejecutado no se cancela: usa /stop")

    cancelled = (
        await conn.execute(_CANCEL_DRILL, {"drill": str(drill_id), "now": datetime.now(tz=UTC)})
    ).first()
    if cancelled is not None:
        await audit_async(
            conn,
            tenant_id=str(row["tenant_id"]),
            actor=f"user:{claims.sub}",
            verb="drill_cancelled",
            obj=f"drill:{drill_id}",
            meta={"scheduled_at": row["scheduled_at"].isoformat()},
        )
        row = (await conn.execute(_SELECT_DRILL, {"drill": str(drill_id)})).mappings().one()
    sites_map = await _sites_of([row], conn)
    return _drill_out(row, sites_map.get(row["drill_id"], []))
