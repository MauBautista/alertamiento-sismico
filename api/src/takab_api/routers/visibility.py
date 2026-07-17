"""Grants de visibilidad entre clientes (T-1.73) — POST/GET/DELETE /visibility-grants.

SOLO ``takab_superadmin`` (acción ``manage_visibility``): conceder/revocar visibilidad
cruzada toca la frontera de aislamiento multi-tenant. La RLS ``vg_admin`` lo exige igual.
Un grant AÑADE lectura (metadatos y/o datos); jamás escritura. Cada cambio se audita.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.audit import audit_async
from takab_api.auth.claims import Claims
from takab_api.auth.deps import require_roles, require_web_surface
from takab_api.auth.matrix import roles_with_action
from takab_api.queries import visibility as q
from takab_api.routers._common import http_error, integrity_error, read_session
from takab_api.schemas.visibility import VisibilityGrantCreate, VisibilityGrantOut

# Conceder/revocar visibilidad: SOLO takab_superadmin (vía matrix.py).
_ROLES: tuple[str, ...] = roles_with_action("manage_visibility")
_require_superadmin = require_roles(*_ROLES)

router = APIRouter(dependencies=[Depends(require_web_surface), Depends(_require_superadmin)])


def _out(row) -> VisibilityGrantOut:
    return VisibilityGrantOut(**dict(row._mapping))


@router.get("/visibility-grants", response_model=list[VisibilityGrantOut])
async def list_visibility_grants(
    grantee_tenant_id: UUID | None = None,
    conn: AsyncConnection = Depends(read_session),
) -> list[VisibilityGrantOut]:
    """Lista los grants (el superadmin ve todos). ``grantee_tenant_id`` filtra un cliente."""
    rows = await q.list_grants(conn, str(grantee_tenant_id) if grantee_tenant_id else None)
    return [_out(r) for r in rows]


@router.post("/visibility-grants", response_model=VisibilityGrantOut, status_code=201)
async def upsert_visibility_grant(
    body: VisibilityGrantCreate,
    claims: Claims = Depends(_require_superadmin),
    conn: AsyncConnection = Depends(read_session),
) -> VisibilityGrantOut:
    """Concede (o actualiza) visibilidad del grantee sobre un cliente o TODOS.

    Un tenant inexistente choca contra la FK (400); la forma inválida (target doble/
    vacío, auto-grant, grant vacío) la rechaza el schema (422) antes de la DB.
    """
    try:
        row = await q.upsert_grant(
            conn,
            grantee=str(body.grantee_tenant_id),
            target=str(body.target_tenant_id) if body.target_tenant_id else None,
            target_all=body.target_all,
            meta=body.can_view_metadata,
            data=body.can_view_data,
            by=claims.sub,
        )
    except IntegrityError as exc:
        raise integrity_error(exc) from exc

    await audit_async(
        conn,
        tenant_id=str(body.grantee_tenant_id),
        actor=f"user:{claims.sub}",
        verb="visibility_grant_upsert",
        obj=f"tenant:{body.grantee_tenant_id}",
        meta={
            "target": "ALL" if body.target_all else str(body.target_tenant_id),
            "metadata": body.can_view_metadata,
            "data": body.can_view_data,
        },
    )
    return _out(row)


@router.delete("/visibility-grants/{grant_id}", status_code=204)
async def revoke_visibility_grant(
    grant_id: UUID,
    claims: Claims = Depends(_require_superadmin),
    conn: AsyncConnection = Depends(read_session),
) -> None:
    """Revoca un grant. El revoke es dinámico: aplica en la siguiente consulta del grantee."""
    row = await q.delete_grant(conn, str(grant_id))
    if row is None:
        raise http_error(404, "grant no encontrado")
    await audit_async(
        conn,
        tenant_id=str(row.grantee_tenant_id),
        actor=f"user:{claims.sub}",
        verb="visibility_grant_revoke",
        obj=f"grant:{grant_id}",
        meta={},
    )
