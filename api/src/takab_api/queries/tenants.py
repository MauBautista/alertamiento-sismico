"""SQL del catálogo de tenants (T-1.22 · B1, edición T-2.51).

La política ``tenants_read`` decide la visibilidad por rol: cada quien ve su fila;
los internos TAKAB ven todas. El router restringe además los roles con acceso
(superadmin/support/tenant_admin) según RBAC §2 (columna Multi-Tenant). La
ESCRITURA la gobierna ``tenants_admin`` (``app_role() = 'takab_superadmin'``).

``xmin::text AS row_version`` es el mismo testigo de concurrencia optimista que
usan ``sites`` y ``gateways`` (ver ``queries/sites.py`` para la nota sobre el
wraparound de 32 bits).
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncConnection

_COLS = (
    "tenant_id, code, name, isolation_mode, vertical, visibility, status, plan_code, "
    "xmin::text AS row_version, created_at"
)

_LIST = text(f"SELECT {_COLS} FROM tenants ORDER BY code, tenant_id")

_GET = text(f"SELECT {_COLS} FROM tenants WHERE tenant_id = :id")

# ``visibility``/``status`` no se pasan: nacen con los defaults del schema
# (private/active). El INSERT lo autoriza la RLS ``tenants_admin`` (superadmin).
_INSERT = text(
    "INSERT INTO tenants (code, name, vertical, plan_code, isolation_mode) "
    "VALUES (:code, :name, :vertical, :plan_code, :isolation_mode) "
    f"RETURNING {_COLS}"
)

#: Columnas escribibles por ``update_tenant``. El SET se arma SOLO con estas: el
#: nombre de columna nunca sale del cuerpo del request (no hay superficie de
#: inyección aunque el schema cambiara).
_PATCHABLE = frozenset({"name", "vertical", "plan_code", "status", "visibility"})


async def list_tenants(conn: AsyncConnection) -> Sequence[Row]:
    """Tenants visibles al request (RLS: propia fila o todas si es interno TAKAB)."""
    return (await conn.execute(_LIST)).all()


async def get_tenant(conn: AsyncConnection, tenant_id: UUID) -> Row | None:
    """Un tenant por id, o ``None`` si no existe / RLS lo oculta."""
    return (await conn.execute(_GET, {"id": tenant_id})).first()


async def insert_tenant(conn: AsyncConnection, *, values: dict) -> Row:
    """Inserta un tenant y devuelve la fila completa. ``code`` único ⇒ IntegrityError."""
    return (await conn.execute(_INSERT, values)).one()


async def update_tenant(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    changes: dict,
    base_row_version: str | None,
) -> Row | None:
    """UPDATE parcial. ``None`` = otro escritor ganó la carrera (⇒ 409).

    El guardia de versión va en el WHERE, como en ``sites``/``gateways``: 0 filas
    significa carrera perdida, no inexistencia — el router ya comprobó con ``_GET``
    que la fila existe y es visible.
    """
    unknown = set(changes) - _PATCHABLE
    if unknown:  # pragma: no cover - el schema ya lo impide; defensa en profundidad
        raise ValueError(f"columnas no editables: {sorted(unknown)}")
    if not changes:  # pragma: no cover - el validador del schema ya lo impide
        raise ValueError("update_tenant sin cambios")
    assignments = ", ".join(f"{col} = :{col}" for col in sorted(changes))
    stmt = text(
        f"UPDATE tenants SET {assignments} "
        "WHERE tenant_id = :id "
        "  AND (CAST(:base_row_version AS text) IS NULL "
        "       OR xmin::text = CAST(:base_row_version AS text)) "
        f"RETURNING {_COLS}"
    )
    params = {**changes, "id": tenant_id, "base_row_version": base_row_version}
    return (await conn.execute(stmt, params)).first()
