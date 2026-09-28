"""Operaciones del operador sobre incidentes (T-1.48): reubicar epicentro y
solicitar dictamen técnico — los dos botones de MONITOREO que estaban
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

- ``POST /incidents/{id}/close`` [T-9.40 · D-43]: CIERRE EXPLÍCITO desde la
  consola. Los requisitos se revisan EN ORDEN con la fila bloqueada (``FOR
  UPDATE``) y cada 409 lleva por ``detail`` su CÓDIGO (la web lo traduce):
  ``ya_cerrado`` → ``sin_acuse`` → ``sismo_en_curso`` → ``sin_clasificacion`` →
  ``sin_dictamen``. El tier, la clasificación vigente y la cabeza de la cadena son
  LOS MISMOS fragmentos SQL que usa la pasada del ciclo de vida: la consola no
  puede cerrar por una definición distinta de la que cierra sola.

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
from takab_api.auth.claims import Claims, scope_filter
from takab_api.auth.deps import get_session, require_roles
from takab_api.auth.matrix import roles_with_action
from takab_api.dictamen.sistema import ATIENDE_ESCALADA_SQL
from takab_api.incident.classification import TERMINALES
from takab_api.incident.lifecycle import (
    CABEZA_SQL,
    CLASIFICACION_VIGENTE_SQL,
    TIER_ACTUAL_SQL,
)
from takab_api.incident.transitions import validate_transition
from takab_api.reingreso import en_calma
from takab_api.schemas.incidents import (
    DictamenRequestIn,
    EpicenterRelocateIn,
    EpicenterRelocateOut,
    IncidentActionOut,
    IncidentCloseIn,
    IncidentCloseOut,
    LonLat,
)

# Fuente única: la matriz de acciones (RBAC §2 + divergencias documentadas).
_require_relocate = require_roles(*roles_with_action("relocate_epicenter"))
_require_request = require_roles(*roles_with_action("request_dictamen"))
_require_close = require_roles(*roles_with_action("close_incident"))

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

_INCIDENT_TENANT_SQL = text(
    "SELECT tenant_id, state, site_id FROM incidents WHERE incident_id = :id"
)

# Solicitud "pendiente" = existe un dictamen_request que ninguna firma HUMANA
# posterior atendió. El timeline append-only es la única verdad.
# [D-49 · R3 · R5] El MISMO criterio que la regla 1d del reingreso
# (`ATIENDE_ESCALADA_SQL`): la atiende el inspector o una confirmación de la brigada,
# nunca el VERDE del sistema. Con dos criterios distintos, tras una confirmación el
# reingreso quedaba autorizado y nadie podía volver a escalar (409).
_PENDING_REQUEST_SQL = text(
    "SELECT 1 FROM incident_actions a "
    "WHERE a.incident_id = :id AND a.kind = 'dictamen_request' "
    "AND NOT EXISTS ("
    "  SELECT 1 FROM dictamens d "
    f"  WHERE d.incident_id = :id AND {ATIENDE_ESCALADA_SQL} AND d.created_at > a.ts"
    ") LIMIT 1"
)

#: [T-9.40 · D-43] Todo lo que decide el cierre, leído en UNA sentencia y con la fila
#: BLOQUEADA: dos cierres concurrentes (o el cierre y la pasada del ciclo de vida)
#: se serializan aquí y el segundo ve ``closed``. ``FOR UPDATE`` exige además la
#: política de ESCRITURA de la RLS: un incidente que el portador sólo puede LEER
#: (grant de datos, gobierno) no aparece, y eso es un 404, no un 403 que confirme
#: que existe. Los fragmentos son los de ``incident/lifecycle`` (alias ``i``).
_CLOSE_LOCK_SQL = text(
    f"""
SELECT i.tenant_id, i.site_id, i.state,
       {TIER_ACTUAL_SQL} AS tier,
       {CLASIFICACION_VIGENTE_SQL} AS classification,
       {CABEZA_SQL.format(col="signed_by")} AS head_signed_by,
       {CABEZA_SQL.format(col="signature_kind")} AS head_signature_kind
  FROM incidents i
 WHERE i.incident_id = :id
   FOR UPDATE OF i
"""
)

_CLOSE_UPDATE_SQL = text(
    "UPDATE incidents SET state = 'closed', closed_at = now() "
    "WHERE incident_id = :id RETURNING closed_at"
)

#: [T-9.40 · D-43] Caracteres mínimos (tras ``strip()``) del motivo para cerrar un
#: ``real``/``indeterminado`` sin cabeza firmada. Veinte bastan para una frase con
#: sujeto («el perito firmó en papel») y descartan el «ok» y el «.» de trámite.
MOTIVO_MIN_CHARS = 20


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
    # [F3·r2] La brigada pide el dictamen técnico de SU inmueble: fuera del alcance
    # por inmueble del portador, el incidente no existe para él (404, como el RLS).
    allowed = scope_filter(claims)
    if allowed is not None and str(row.site_id) not in allowed:
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


def _conflicto(codigo: str) -> HTTPException:
    """409 cuyo ``detail`` es el CÓDIGO del requisito que falta (la web lo traduce)."""
    return HTTPException(status_code=409, detail=codigo)


@router.post("/incidents/{incident_id}/close", response_model=IncidentCloseOut)
async def close_incident(
    incident_id: UUID,
    body: IncidentCloseIn,
    claims: Claims = Depends(_require_close),
    conn: AsyncConnection = Depends(get_session),
) -> IncidentCloseOut:
    """[T-9.40 · D-43] Cierra un incidente a propósito, si cumple los requisitos.

    El ORDEN de las comprobaciones es parte del contrato (cada una presupone las
    anteriores): existe → no está cerrado → está acusado → el edificio está en
    calma (D-49 · R1: nada se cierra con el edificio moviéndose) → está
    clasificado → si la clasificación NO es terminal, la CABEZA de la cadena está
    firmada o hay un motivo escrito de al menos ``MOTIVO_MIN_CHARS`` caracteres.

    Un cierre sin cabeza firmada deja, además del ``close``, un audit
    ``cierre_sin_dictamen`` con el motivo: es la fila que un auditor busca.
    """
    row = (await conn.execute(_CLOSE_LOCK_SQL, {"id": incident_id})).first()
    if row is None:
        raise HTTPException(status_code=404, detail="incidente no encontrado")
    # Fuera del alcance por inmueble del portador, el incidente no existe para él.
    allowed = scope_filter(claims)
    if allowed is not None and str(row.site_id) not in allowed:
        raise HTTPException(status_code=404, detail="incidente no encontrado")
    if row.state == "closed":
        raise _conflicto("ya_cerrado")
    if row.state == "open":
        raise _conflicto("sin_acuse")
    if not en_calma(row.tier):
        raise _conflicto("sismo_en_curso")
    if row.classification is None:
        raise _conflicto("sin_clasificacion")

    motivo = body.motivo.strip() if body.motivo and body.motivo.strip() else None
    firmada = row.head_signed_by is not None
    pide_dictamen = row.classification not in TERMINALES
    sin_dictamen = pide_dictamen and not firmada
    if sin_dictamen and (motivo is None or len(motivo) < MOTIVO_MIN_CHARS):
        raise _conflicto("sin_dictamen")

    validate_transition(row.state, "closed")  # acked|in_review → closed: siempre válida
    closed_at = (await conn.execute(_CLOSE_UPDATE_SQL, {"id": incident_id})).scalar_one()

    actor = f"user:{claims.sub}"
    signature_kind = row.head_signature_kind if firmada else None
    detalle: dict[str, object] = {
        "from": row.state,
        "to": "closed",
        "reason": "explicit",
        "classification": row.classification,
        "signature_kind": signature_kind,
    }
    if motivo is not None:
        detalle["motivo"] = motivo
    await conn.execute(
        _INSERT_ACTION_SQL,
        {
            "id": incident_id,
            "tenant": row.tenant_id,
            "kind": "close",
            "actor": actor,
            "payload": json.dumps(detalle),
        },
    )
    await audit_async(
        conn,
        tenant_id=row.tenant_id,
        actor=actor,
        verb="close",
        obj=f"incident:{incident_id}",
        meta=detalle,
    )
    if sin_dictamen:
        await audit_async(
            conn,
            tenant_id=row.tenant_id,
            actor=actor,
            verb="cierre_sin_dictamen",
            obj=f"incident:{incident_id}",
            meta={"motivo": motivo, "classification": row.classification},
        )
    return IncidentCloseOut(
        incident_id=incident_id,
        closed_at=closed_at,
        classification=row.classification,
        signature_kind=signature_kind,
        sin_dictamen=sin_dictamen,
    )
