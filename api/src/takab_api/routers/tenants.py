"""GET /tenants — catálogo de tenants (T-1.22 · B1).

Autz (RBAC §2 · columna Multi-Tenant): solo roles con acceso a /tenants
(superadmin/support/tenant_admin). superadmin y support ven todas las filas
(internos TAKAB); tenant_admin ve SOLO la suya (RLS ``tenants_read``). gov_operator
y demás roles no llegan aquí (403) aunque RLS les mostrara gov_shared.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.audit import audit_async
from takab_api.auth.claims import Claims
from takab_api.auth.deps import require_roles, require_web_surface
from takab_api.auth.matrix import ROLE_ROUTE_MATRIX, TENANTS, roles_with_action
from takab_api.queries import tenants as q
from takab_api.routers._common import integrity_error, read_session
from takab_api.schemas.tenants import TenantCreate, TenantOut

# Roles con /tenants en RBAC §2 (vía matrix.py).
_TENANT_ROLES: tuple[str, ...] = tuple(
    sorted(r for r, routes in ROLE_ROUTE_MATRIX.items() if TENANTS in routes)
)

# Alta de clientes: SOLO takab_superadmin (acción ``manage_tenants`` vía matrix.py).
_require_manage_tenants = require_roles(*roles_with_action("manage_tenants"))

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


@router.post("/tenants", response_model=TenantOut, status_code=201)
async def create_tenant(
    body: TenantCreate,
    claims: Claims = Depends(_require_manage_tenants),
    conn: AsyncConnection = Depends(read_session),
) -> TenantOut:
    """Da de alta un cliente. ``code`` es único global ⇒ 409. Solo takab_superadmin.

    La escritura la autoriza la RLS ``tenants_admin`` (app_role='takab_superadmin');
    el endpoint la restringe además con la acción ``manage_tenants`` para no pintar el
    botón a roles que la DB rechazaría (regla de oro 7).
    """
    values = {
        "code": body.code,
        "name": body.name,
        "vertical": body.vertical,
        "plan_code": body.plan_code,
        "isolation_mode": body.isolation_mode,
    }
    try:
        row = await q.insert_tenant(conn, values=values)
    except IntegrityError as exc:
        raise integrity_error(exc) from exc

    await audit_async(
        conn,
        tenant_id=str(row.tenant_id),
        actor=f"user:{claims.sub}",
        verb="tenant_create",
        obj=f"tenant:{row.tenant_id}",
        meta={"code": body.code, "plan_code": body.plan_code},
    )
    return TenantOut(**dict(row._mapping))
