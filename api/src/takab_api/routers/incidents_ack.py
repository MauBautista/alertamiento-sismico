"""POST /incidents/{id}/ack — único write que T-1.18 necesita para probar tenancy.

El router completo de incidentes es T-1.22; aquí solo el acuse open→acked, que
ejercita RLS por tenant (roles de tenant) y la vía SECURITY DEFINER de gobierno.

Roles con acuse (RBAC §2, Consola C4I ∈ {Total, "Lectura + ack"}) = los que la
matriz marca ``ack_incident``: superadmin, tenant_admin, soc_operator, gov_operator.
``gov_operator`` NO escribe incidentes a nivel de fila (RLS): su única escritura
es ``gov_ack_incident`` (SECURITY DEFINER, valida gov_shared + open→acked + audit).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.audit import audit_async
from takab_api.auth.claims import Claims
from takab_api.auth.deps import get_session, require_roles
from takab_api.auth.matrix import ROLE_ACTION_MATRIX

# Fuente única: los roles con acuse salen de la matriz de acciones (RBAC §2).
ACK_ROLES: tuple[str, ...] = tuple(
    sorted(r for r, actions in ROLE_ACTION_MATRIX.items() if actions["ack_incident"])
)

# Singleton de dependencia (no llamar require_roles en el default del argumento).
_require_ack = require_roles(*ACK_ROLES)

router = APIRouter()


@router.post("/incidents/{incident_id}/ack")
async def ack_incident(
    incident_id: UUID,
    claims: Claims = Depends(_require_ack),
    conn: AsyncConnection = Depends(get_session),
) -> dict[str, str]:
    """Acusa un incidente abierto. 404 si no existe/no visible; 409 si ya no está abierto."""
    if claims.role == "gov_operator":
        await _gov_ack(conn, incident_id)
    else:
        await _tenant_ack(conn, incident_id, claims)
    return {"incident_id": str(incident_id), "state": "acked"}


async def _gov_ack(conn: AsyncConnection, incident_id: UUID) -> None:
    """Acuse de gobierno vía función SECURITY DEFINER; mapea sus RAISE a HTTP.

    Solo los RAISE conocidos de ``gov_ack_incident`` se traducen a 4xx. Un fallo
    real de DB (timeout, deadlock, corte de conexión) NO lleva sus mensajes, así
    que se relanza como 5xx en vez de enmascararse como 404 'no encontrado'.
    """
    try:
        await conn.execute(text("SELECT gov_ack_incident(:id)"), {"id": incident_id})
    except DBAPIError as exc:
        msg = str(getattr(exc, "orig", exc))
        if "transicion" in msg:
            raise HTTPException(status_code=409, detail="el incidente ya no está abierto") from exc
        if "inexistente" in msg or "no es gov_shared" in msg:
            # Para gobierno, un incidente que no existe o no es gov_shared es invisible.
            raise HTTPException(status_code=404, detail="incidente no encontrado") from exc
        # Cualquier otro error es un fallo de servidor real: no lo disfracemos de 404.
        raise


async def _tenant_ack(conn: AsyncConnection, incident_id: UUID, claims: Claims) -> None:
    """Acuse directo (RLS filtra por tenant) + traza en incident_actions y audit_log."""
    row = (
        await conn.execute(
            text("SELECT tenant_id, state FROM incidents WHERE incident_id = :id"),
            {"id": incident_id},
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="incidente no encontrado")
    if row.state != "open":
        raise HTTPException(status_code=409, detail="el incidente ya no está abierto")

    tenant_id = row.tenant_id  # uuid.UUID del incidente visible (== tenant salvo internos)
    actor = f"user:{claims.sub}"
    await conn.execute(
        text("UPDATE incidents SET state = 'acked' WHERE incident_id = :id AND state = 'open'"),
        {"id": incident_id},
    )
    await conn.execute(
        text(
            "INSERT INTO incident_actions (incident_id, tenant_id, kind, actor) "
            "VALUES (:id, :tenant, 'ack', :actor)"
        ),
        {"id": incident_id, "tenant": tenant_id, "actor": actor},
    )
    await audit_async(
        conn,
        tenant_id=tenant_id,
        actor=actor,
        verb="ack",
        obj=f"incident:{incident_id}",
    )
