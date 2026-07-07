"""GET /tenants — catálogo de tenants (T-1.22 · B1).

Autz (RBAC §2 · columna Multi-Tenant): solo roles con acceso a /tenants
(superadmin/support/tenant_admin). superadmin y support ven todas las filas
(internos TAKAB); tenant_admin ve SOLO la suya (RLS ``tenants_read``). gov_operator
y demás roles no llegan aquí (403) aunque RLS les mostrara gov_shared.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.auth.deps import require_roles, require_web_surface
from takab_api.auth.matrix import ROLE_ROUTE_MATRIX, TENANTS
from takab_api.queries import tenants as q
from takab_api.routers._common import read_session
from takab_api.schemas.tenants import TenantOut

# Roles con /tenants en RBAC §2 (vía matrix.py).
_TENANT_ROLES: tuple[str, ...] = tuple(
    sorted(r for r, routes in ROLE_ROUTE_MATRIX.items() if TENANTS in routes)
)

router = APIRouter(
    dependencies=[Depends(require_web_surface), Depends(require_roles(*_TENANT_ROLES))]
)


@router.get("/tenants", response_model=list[TenantOut])
async def list_tenants(
    conn: AsyncConnection = Depends(read_session),
) -> list[TenantOut]:
    """Tenants visibles al rol (RLS decide: propia fila o todas si es interno)."""
    rows = await q.list_tenants(conn)
    return [TenantOut(**dict(r._mapping)) for r in rows]
