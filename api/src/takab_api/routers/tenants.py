"""GET /tenants — catálogo de tenants (T-1.22 · B1).

Autz (RBAC §2 · columna Multi-Tenant): solo roles con acceso a /tenants
(superadmin/support/tenant_admin). superadmin y support ven todas las filas
(internos TAKAB); tenant_admin ve SOLO la suya (RLS ``tenants_read``). gov_operator
y demás roles no llegan aquí (403) aunque RLS les mostrara gov_shared.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.audit import audit_async
from takab_api.auth.claims import Claims
from takab_api.auth.deps import get_claims, require_roles, require_web_surface
from takab_api.auth.matrix import ROLE_ROUTE_MATRIX, TENANTS, roles_with_action
from takab_api.queries import tenants as q
from takab_api.retire_code import retire_code_state, rotate_retire_code
from takab_api.routers._common import INTERNAL_ROLES, http_error, integrity_error, read_session
from takab_api.schemas.retire import RetireCodeRotate, RetireCodeState
from takab_api.schemas.tenants import TenantCreate, TenantOut

# Roles con /tenants en RBAC §2 (vía matrix.py).
_TENANT_ROLES: tuple[str, ...] = tuple(
    sorted(r for r, routes in ROLE_ROUTE_MATRIX.items() if TENANTS in routes)
)

# Alta de clientes: SOLO takab_superadmin (acción ``manage_tenants`` vía matrix.py).
_require_manage_tenants = require_roles(*roles_with_action("manage_tenants"))

# [T-2.36] Rotar el código de retiro: SOLO takab_superadmin. Si el cliente pudiera
# rotar el suyo, el segundo factor volvería a ser el primero (su propia sesión).
_require_manage_retire_code = require_roles(*roles_with_action("manage_retire_code"))

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


# --- Código de retiro (T-2.36) ------------------------------------------------


def _require_own_tenant(claims: Claims, tenant_id: UUID) -> None:
    """Un rol de tenant solo consulta el suyo.

    ``app_retire_code_state`` es SECURITY DEFINER y por definición ignora la RLS: sin
    esta comprobación un ``tenant_admin`` podría preguntar por el estado del código de
    OTRO cliente. Los internos TAKAB sí ven cualquiera (es su superficie de soporte).
    """
    if claims.role not in INTERNAL_ROLES and str(tenant_id) != claims.tenant_id:
        raise http_error(403, "no puedes consultar el código de retiro de otro cliente")


@router.get("/tenants/{tenant_id}/retire-code", response_model=RetireCodeState)
async def get_retire_code_state(
    tenant_id: UUID,
    claims: Claims = Depends(get_claims),
    conn: AsyncConnection = Depends(read_session),
) -> RetireCodeState:
    """¿Tiene este cliente código de retiro configurado? Nunca devuelve el hash.

    La consola lo consulta antes de ofrecer el retiro: sin código el intento sería un
    409 seguro, y ofrecer un botón que siempre falla es lo que veta la regla de oro 7.
    """
    _require_own_tenant(claims, tenant_id)
    state = await retire_code_state(conn, str(tenant_id))
    if state is None:
        return RetireCodeState(tenant_id=tenant_id, configured=False)
    version, rotated_at = state
    return RetireCodeState(
        tenant_id=tenant_id, configured=True, version=version, rotated_at=rotated_at
    )


@router.put("/tenants/{tenant_id}/retire-code", response_model=RetireCodeState)
async def put_retire_code(
    tenant_id: UUID,
    body: RetireCodeRotate,
    claims: Claims = Depends(_require_manage_retire_code),
    conn: AsyncConnection = Depends(read_session),
) -> RetireCodeState:
    """Fija o rota el código de retiro del cliente. SOLO ``takab_superadmin``.

    Rotar invalida el anterior de inmediato: la fila es única por tenant y el
    ``version`` monótono deja constancia de cuántas veces se cambió. El texto en claro
    no se guarda, no se devuelve y no entra en la bitácora — solo el hecho de la
    rotación.
    """
    version, rotated_at = await rotate_retire_code(
        conn, tenant_id=str(tenant_id), code=body.code, rotated_by=claims.sub
    )
    await audit_async(
        conn,
        tenant_id=str(tenant_id),
        actor=f"user:{claims.sub}",
        verb="retire_code_rotate",
        obj=f"tenant:{tenant_id}",
        meta={"version": version},
    )
    return RetireCodeState(
        tenant_id=tenant_id, configured=True, version=version, rotated_at=rotated_at
    )
