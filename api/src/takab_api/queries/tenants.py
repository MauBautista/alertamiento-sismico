"""SQL del catálogo de tenants (T-1.22 · B1).

La política ``tenants_read`` decide la visibilidad por rol: cada quien ve su fila;
los internos TAKAB ven todas. El router restringe además los roles con acceso
(superadmin/support/tenant_admin) según RBAC §2 (columna Multi-Tenant).
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncConnection

_LIST = text(
    "SELECT tenant_id, code, name, isolation_mode, vertical, visibility, "
    "status, plan_code, created_at FROM tenants ORDER BY code, tenant_id"
)


async def list_tenants(conn: AsyncConnection) -> Sequence[Row]:
    """Tenants visibles al request (RLS: propia fila o todas si es interno TAKAB)."""
    return (await conn.execute(_LIST)).all()
