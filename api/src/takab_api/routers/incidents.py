"""Routers de lectura de incidentes (T-1.22 · B2): lista keyset, detalle, timeline.

Roles con acceso = quienes tienen MONITOREO en RBAC §2 (la matriz de rutas es
la fuente única). El acuse (POST /incidents/{id}/ack) vive en ``incidents_ack``; aquí
solo lectura. RLS acota por tenant en cada consulta.
"""

from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.audit import audit_async
from takab_api.auth.claims import Claims, scope_filter
from takab_api.auth.deps import (
    get_claims,
    get_console_scope,
    get_session,
    require_roles,
)
from takab_api.auth.matrix import CONSOLE, ROLE_ROUTE_MATRIX, roles_with_action
from takab_api.auth.scope import ConsoleScope
from takab_api.queries import incidents as q
from takab_api.queries import mobile as mobile_q
from takab_api.routers._common import (
    clamp_limit,
    decode_cursor,
    encode_cursor,
    http_error,
    parse_range_filters,
    read_session,
)
from takab_api.schemas.incidents import IncidentActionOut, IncidentOut, IncidentPage

# Roles con MONITOREO (celda ≠ "—" en RBAC §2), derivados de la matriz de rutas.
CONSOLE_ROLES: tuple[str, ...] = tuple(
    sorted(r for r, routes in ROLE_ROUTE_MATRIX.items() if CONSOLE in routes)
)

_VALID_STATE = frozenset({"open", "acked", "in_review", "closed"})
_VALID_SEVERITY = frozenset({"info", "watch", "warning", "critical"})

_require_console = require_roles(*CONSOLE_ROLES)

router = APIRouter(dependencies=[Depends(_require_console)])

# [T-2.08] La traza del incidente (timeline BMS) también la lee el DASHBOARD
# TÁCTICO móvil (RBAC §3 · ``panel_read``): vive en un router propio sin el
# candado global de consola. MISMO endpoint y MISMA query para ambas
# superficies — cero transformaciones divergentes (criterio 2.1).
PANEL_ROLES: tuple[str, ...] = roles_with_action("panel_read")
_require_console_or_panel = require_roles(*sorted({*CONSOLE_ROLES, *PANEL_ROLES}))

actions_router = APIRouter(dependencies=[Depends(_require_console_or_panel)])


@router.get("/incidents", response_model=IncidentPage)
async def list_incidents(
    conn: AsyncConnection = Depends(read_session),
    scope: ConsoleScope = Depends(get_console_scope),
    state: str | None = Query(None),
    severity: str | None = Query(None),
    site_id: str | None = Query(None),
    q_prefix: str | None = Query(None, alias="q"),
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    cursor: str | None = Query(None),
    limit: int | None = Query(None),
) -> IncidentPage:
    """Lista incidentes (opened_at desc) con filtros, rango de fechas (T-1.57)
    y paginación keyset estable."""
    if state is not None and state not in _VALID_STATE:
        raise http_error(400, "state inválido")
    if severity is not None and severity not in _VALID_SEVERITY:
        raise http_error(400, "severity inválido")
    from_ts, to_ts = parse_range_filters(from_, to)

    size = clamp_limit(limit)
    cur_ts, cur_id = (None, None)
    if cursor is not None:
        cur_ts, cur_id = decode_cursor(cursor)

    stmt, params = q.select_incidents(
        state=state,
        severity=severity,
        site_id=site_id,
        q=q_prefix,
        from_ts=from_ts,
        to_ts=to_ts,
        cursor_opened_at=cur_ts,
        cursor_id=cur_id,
        scope=scope,
        limit=size + 1,
    )
    rows = (await conn.execute(stmt, params)).mappings().all()

    next_cursor = None
    if len(rows) > size:
        rows = rows[:size]
        last = rows[-1]
        next_cursor = encode_cursor(last["opened_at"].isoformat(), str(last["incident_id"]))

    return IncidentPage(items=[IncidentOut(**dict(r)) for r in rows], next_cursor=next_cursor)


@router.get("/incidents/{incident_id}", response_model=IncidentOut)
async def get_incident(
    incident_id: UUID,
    conn: AsyncConnection = Depends(read_session),
) -> IncidentOut:
    """Detalle de un incidente. 404 si no existe o no es visible por RLS."""
    stmt, params = q.select_incident(str(incident_id))
    row = (await conn.execute(stmt, params)).mappings().first()
    if row is None:
        raise http_error(404, "incidente no encontrado")
    return IncidentOut(**dict(row))


@actions_router.get("/incidents/{incident_id}/actions", response_model=list[IncidentActionOut])
async def list_incident_actions(
    incident_id: UUID,
    claims: Claims = Depends(get_claims),
    conn: AsyncConnection = Depends(read_session),
) -> list[IncidentActionOut]:
    """Timeline append-only del incidente. 404 si el incidente no es visible.

    [T-2.08] MONITOREO por rol, o dashboard táctico móvil (``panel_read``):
    el táctico queda además acotado a su ``site_scope`` default-deny — fuera de
    alcance recibe el MISMO 404 (sin filtración de existencia).
    """
    stmt, params = q.select_incident(str(incident_id))
    row = (await conn.execute(stmt, params)).mappings().first()
    if row is None:
        raise http_error(404, "incidente no encontrado")
    if claims.role not in CONSOLE_ROLES:
        allowed = scope_filter(claims)
        if allowed is not None and str(row["site_id"]) not in allowed:
            raise http_error(404, "incidente no encontrado")
    stmt, params = q.select_incident_actions(str(incident_id))
    rows = (await conn.execute(stmt, params)).mappings().all()
    return [IncidentActionOut(**dict(r)) for r in rows]


# [T-2.147.b · D-05] EL ACUSE DEL TÁCTICO, que no es el acuse del SOC.
#
# `POST /incidents/{id}/ack` (incidents_ack.py) mueve el incidente `open→acked` y
# lo firman los roles de MONITOREO. Esto es otro acto: quien recibió el push de un
# pánico dice «lo tengo, voy». Conflarlos costaría en las dos direcciones — un
# brigadista vaciando la cola del SOC desde el teléfono, y el acuse del SOC
# contando como respuesta de la brigada y apagando el escalado de `T-2.147.c` sin
# que nadie hubiera bajado a mirar.
#
# El círculo se DERIVA de `manual_activate`: exactamente el mismo que recibe el
# push en `T-2.147.a`. Que sean la misma lista no es economía, es una invariante —
# si divergieran, alguien despertado sin poder acusar parecería «sin respuesta»
# para siempre y dispararía el escalado al SOC por un fallo de permisos.
TACTICAL_ACK_ROLES: tuple[str, ...] = roles_with_action("manual_activate")

tactical_ack_router = APIRouter(dependencies=[Depends(require_roles(*TACTICAL_ACK_ROLES))])


@tactical_ack_router.post("/incidents/{incident_id}/tactical-ack")
async def tactical_ack(
    incident_id: UUID,
    claims: Claims = Depends(get_claims),
    conn: AsyncConnection = Depends(get_session),
) -> dict[str, object]:
    """La brigada acusa recibo de la alarma. **No cambia el estado del incidente.**

    404 si el incidente no existe o queda fuera del alcance del portador — el
    mismo 404 en los dos casos, sin filtrar la existencia.

    Idempotente por persona: pulsar dos veces devuelve ``already=true`` y no
    escribe una segunda fila. Lo que se mide aguas arriba es «cuántas PERSONAS
    respondieron», no cuántas pulsaciones hubo.
    """
    stmt, params = q.select_incident(str(incident_id))
    row = (await conn.execute(stmt, params)).mappings().first()
    if row is None:
        raise http_error(404, "incidente no encontrado")
    allowed = scope_filter(claims)
    if allowed is not None and str(row["site_id"]) not in allowed:
        raise http_error(404, "incidente no encontrado")

    actor = f"user:{claims.sub}"
    inserted = (
        await conn.execute(
            mobile_q.INSERT_TACTICAL_ACK,
            {
                "incident": str(incident_id),
                "tenant": str(row["tenant_id"]),
                "actor": actor,
                "payload": json.dumps({"role": claims.role, "surface": claims.surface}),
            },
        )
    ).first()
    await audit_async(
        conn,
        tenant_id=str(row["tenant_id"]),
        actor=actor,
        verb="tactical_ack",
        obj=f"incident:{incident_id}",
        meta={"already": inserted is None},
    )
    return {
        "incident_id": str(incident_id),
        "acked": True,
        "already": inserted is None,
        # El estado del incidente NO se toca: lo mueve el SOC, no la brigada.
        "incident_state": row["state"],
    }
