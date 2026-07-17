"""SQL del catálogo de tenants (T-1.22 · B1).

La política ``tenants_read`` decide la visibilidad por rol: cada quien ve su fila;
los internos TAKAB ven todas. El router restringe además los roles con acceso
(superadmin/support/tenant_admin) según RBAC §2 (columna Multi-Tenant).
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncConnection

_COLS = "tenant_id, code, name, isolation_mode, vertical, visibility, status, plan_code, created_at"

_LIST = text(f"SELECT {_COLS} FROM tenants ORDER BY code, tenant_id")

# ``visibility``/``status`` no se pasan: nacen con los defaults del schema
# (private/active). El INSERT lo autoriza la RLS ``tenants_admin`` (superadmin).
_INSERT = text(
    "INSERT INTO tenants (code, name, vertical, plan_code, isolation_mode) "
    "VALUES (:code, :name, :vertical, :plan_code, :isolation_mode) "
    f"RETURNING {_COLS}"
)


async def list_tenants(conn: AsyncConnection) -> Sequence[Row]:
    """Tenants visibles al request (RLS: propia fila o todas si es interno TAKAB)."""
    return (await conn.execute(_LIST)).all()


async def insert_tenant(conn: AsyncConnection, *, values: dict) -> Row:
    """Inserta un tenant y devuelve la fila completa. ``code`` único ⇒ IntegrityError."""
    return (await conn.execute(_INSERT, values)).one()
