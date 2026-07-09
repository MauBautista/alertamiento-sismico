"""Routers de dictámenes (T-1.22 · B2): cadena de versiones + firma del inspector.

Lectura = quienes tienen Triage en RBAC §2 (matriz de rutas). La firma es un acto
profesional del inspector: ``SIGN_ROLES`` se DERIVA de ``matrix.ROLE_ACTION_MATRIX``
(``sign_dictamen``), que no se la concede al superadmin pese a su "Total" en Triage §2.
La política ``dictamens_admin`` (DDL) sigue permitiendo el INSERT a la identidad interna
para soporte/operación de DB, pero la API no expone la firma a ese rol.

Firmar = INSERTAR una fila nueva que supersede la última de la cadena (nunca UPDATE;
trigger append-only).
"""

from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.auth.claims import Claims
from takab_api.auth.deps import require_roles
from takab_api.auth.matrix import ROLE_ROUTE_MATRIX, TRIAGE, roles_with_action
from takab_api.queries import dictamens as q
from takab_api.routers._common import http_error, read_session
from takab_api.schemas.dictamens import (
    DICTAMEN_STATUS,
    DictamenList,
    DictamenOut,
    DictamenSignIn,
)

# Roles con Triage (celda ≠ "—" en RBAC §2), derivados de la matriz de rutas.
TRIAGE_ROLES: tuple[str, ...] = tuple(
    sorted(r for r, routes in ROLE_ROUTE_MATRIX.items() if TRIAGE in routes)
)

# Firma del dictamen: derivada de la matriz (acto profesional del inspector). El
# "Total" de superadmin en Triage §2 concede LECTURA, no firma.
SIGN_ROLES: tuple[str, ...] = roles_with_action("sign_dictamen")

_require_triage = require_roles(*TRIAGE_ROLES)
_require_sign = require_roles(*SIGN_ROLES)

router = APIRouter()


@router.get(
    "/incidents/{incident_id}/dictamens",
    response_model=DictamenList,
    dependencies=[Depends(_require_triage)],
)
async def list_dictamens(
    incident_id: UUID,
    conn: AsyncConnection = Depends(read_session),
) -> DictamenList:
    """Cadena de dictámenes del incidente (más reciente primero). 404 si no visible."""
    tenant_stmt, tenant_params = q.select_incident_tenant(str(incident_id))
    if (await conn.execute(tenant_stmt, tenant_params)).first() is None:
        raise http_error(404, "incidente no encontrado")
    stmt, params = q.select_dictamens(str(incident_id))
    rows = (await conn.execute(stmt, params)).mappings().all()
    return DictamenList(items=[DictamenOut(**dict(r)) for r in rows])


@router.post(
    "/incidents/{incident_id}/dictamens",
    response_model=DictamenOut,
    status_code=201,
)
async def sign_dictamen(
    incident_id: UUID,
    body: DictamenSignIn,
    claims: Claims = Depends(_require_sign),
    conn: AsyncConnection = Depends(read_session),
) -> DictamenOut:
    """Firma un dictamen: inserta fila nueva superseeding la última de la cadena."""
    if body.status not in DICTAMEN_STATUS:
        raise http_error(400, "status de dictamen inválido")

    tenant_stmt, tenant_params = q.select_incident_tenant(str(incident_id))
    row = (await conn.execute(tenant_stmt, tenant_params)).first()
    if row is None:
        raise http_error(404, "incidente no encontrado")
    tenant_id = str(row.tenant_id)

    head_stmt, head_params = q.select_chain_head(str(incident_id))
    head = (await conn.execute(head_stmt, head_params)).scalar_one_or_none()
    supersedes = str(head) if head is not None else None

    basis: dict[str, str] = {}
    if body.notes is not None:
        basis["notes"] = body.notes

    ins_stmt, ins_params = q.insert_dictamen(
        tenant_id=tenant_id,
        incident_id=str(incident_id),
        status=body.status,
        basis=json.dumps(basis),
        signed_by=claims.sub,
        supersedes=supersedes,
    )
    created = (await conn.execute(ins_stmt, ins_params)).mappings().one()
    return DictamenOut(**dict(created))
