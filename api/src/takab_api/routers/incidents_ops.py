"""Operaciones del operador sobre incidentes (T-1.48): reubicar epicentro y
solicitar dictamen técnico — los dos botones de la Consola C4I que estaban
muertos.

- ``POST /incidents/{id}/epicenter``: la escritura sobre ``seismic_events``
  (dato de RED sin tenant_id) va por la función SECURITY DEFINER
  ``relocate_incident_epicenter`` (migración 0011, precedente gov_ack): guarda
  de rol/tenant/rango, punto previo en ``meta.manual_override``, y sin evento
  linkeado crea ``EVT-MAN-…`` determinista ``source='manual'`` con
  ``magnitude NULL``. El router añade la acción ``epicenter_relocate`` al
  timeline (RLS ``actions_insert``) y audita vía ``audit.py``.

- ``POST /incidents/{id}/dictamen-request``: inserta ``kind='dictamen_request'``
  en el timeline (append-only). 409 si ya hay una solicitud SIN dictamen firmado
  posterior (idempotencia suave: re-solicitar tras la firma sí procede).

Los frames WS salen gratis: los triggers NOTIFY de 0004 cubren el UPDATE de
``incidents`` (link de evento) y todo INSERT en ``incident_actions``.
"""

from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.audit import audit_async
from takab_api.auth.claims import Claims
from takab_api.auth.deps import get_session, require_roles
from takab_api.auth.matrix import roles_with_action
from takab_api.schemas.incidents import (
    DictamenRequestIn,
    EpicenterRelocateIn,
    EpicenterRelocateOut,
    IncidentActionOut,
    LonLat,
)

# Fuente única: la matriz de acciones (RBAC §2 + divergencias documentadas).
_require_relocate = require_roles(*roles_with_action("relocate_epicenter"))
_require_request = require_roles(*roles_with_action("request_dictamen"))

router = APIRouter()

_RELOCATE_SQL = text(
    "SELECT r_event_id, r_created_event, r_prev_lon, r_prev_lat "
    "FROM relocate_incident_epicenter(:id, :lon, :lat)"
)

_INSERT_ACTION_SQL = text(
    "INSERT INTO incident_actions (incident_id, tenant_id, kind, actor, payload) "
    "VALUES (:id, :tenant, :kind, :actor, CAST(:payload AS jsonb)) "
    "RETURNING action_id, incident_id, tenant_id, ts, kind, actor, payload"
)

_INCIDENT_TENANT_SQL = text("SELECT tenant_id, state FROM incidents WHERE incident_id = :id")

# Solicitud "pendiente" = existe un dictamen_request SIN dictamen FIRMADO
# posterior a su ts. El timeline append-only es la única verdad.
_PENDING_REQUEST_SQL = text(
    "SELECT 1 FROM incident_actions a "
    "WHERE a.incident_id = :id AND a.kind = 'dictamen_request' "
    "AND NOT EXISTS ("
    "  SELECT 1 FROM dictamens d "
    "  WHERE d.incident_id = :id AND d.signed_by IS NOT NULL AND d.created_at > a.ts"
    ") LIMIT 1"
)


@router.post("/incidents/{incident_id}/epicenter", response_model=EpicenterRelocateOut)
async def relocate_epicenter(
    incident_id: UUID,
    body: EpicenterRelocateIn,
    claims: Claims = Depends(_require_relocate),
    conn: AsyncConnection = Depends(get_session),
) -> EpicenterRelocateOut:
    """Reubica el epicentro del incidente (creando evento manual si no había)."""
    try:
        row = (
            await conn.execute(_RELOCATE_SQL, {"id": incident_id, "lon": body.lon, "lat": body.lat})
        ).first()
    except DBAPIError as exc:
        msg = str(getattr(exc, "orig", exc))
        if "inexistente" in msg:
            raise HTTPException(status_code=404, detail="incidente no encontrado") from exc
        if "rol sin permiso" in msg:
            raise HTTPException(status_code=403, detail="rol sin acceso a este recurso") from exc
        if "fuera de rango" in msg:
            raise HTTPException(status_code=400, detail="coordenadas fuera de rango") from exc
        raise  # fallo real de DB: no disfrazarlo de 4xx

    previous = (
        LonLat(lon=row.r_prev_lon, lat=row.r_prev_lat)
        if row.r_prev_lon is not None and row.r_prev_lat is not None
        else None
    )
    actor = f"user:{claims.sub}"
    payload = {
        "lon": body.lon,
        "lat": body.lat,
        "prev_lon": row.r_prev_lon,
        "prev_lat": row.r_prev_lat,
        "event_id": row.r_event_id,
        "created_event": row.r_created_event,
        "note": body.note,
    }
    await conn.execute(
        _INSERT_ACTION_SQL,
        {
            "id": incident_id,
            "tenant": claims.tenant_id,
            "kind": "epicenter_relocate",
            "actor": actor,
            "payload": json.dumps(payload),
        },
    )
    await audit_async(
        conn,
        tenant_id=claims.tenant_id,
        actor=actor,
        verb="epicenter_relocate",
        obj=f"incident:{incident_id}",
        meta=payload,
    )
    return EpicenterRelocateOut(
        incident_id=incident_id,
        event_id=row.r_event_id,
        created_event=row.r_created_event,
        epicenter=LonLat(lon=body.lon, lat=body.lat),
        previous=previous,
    )


@router.post(
    "/incidents/{incident_id}/dictamen-request",
    response_model=IncidentActionOut,
    status_code=201,
)
async def request_dictamen(
    incident_id: UUID,
    body: DictamenRequestIn,
    claims: Claims = Depends(_require_request),
    conn: AsyncConnection = Depends(get_session),
) -> IncidentActionOut:
    """Solicita dictamen técnico: acción auditada en el timeline del incidente."""
    row = (await conn.execute(_INCIDENT_TENANT_SQL, {"id": incident_id})).first()
    if row is None:
        raise HTTPException(status_code=404, detail="incidente no encontrado")
    pending = (await conn.execute(_PENDING_REQUEST_SQL, {"id": incident_id})).first()
    if pending is not None:
        raise HTTPException(
            status_code=409,
            detail="ya hay una solicitud de dictamen pendiente para este incidente",
        )

    actor = f"user:{claims.sub}"
    note = body.note.strip() if body.note else None
    action = (
        await conn.execute(
            _INSERT_ACTION_SQL,
            {
                "id": incident_id,
                "tenant": row.tenant_id,
                "kind": "dictamen_request",
                "actor": actor,
                "payload": json.dumps({"note": note, "requested_by": claims.sub}),
            },
        )
    ).first()
    await audit_async(
        conn,
        tenant_id=row.tenant_id,
        actor=actor,
        verb="dictamen_request",
        obj=f"incident:{incident_id}",
        meta={"note": note},
    )
    return IncidentActionOut(
        action_id=action.action_id,
        incident_id=action.incident_id,
        tenant_id=action.tenant_id,
        ts=action.ts,
        kind=action.kind,
        actor=action.actor,
        payload=action.payload,
    )
