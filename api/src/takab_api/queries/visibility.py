"""SQL de los grants de visibilidad (T-1.73).

RLS ``vg_read``/``vg_admin``: el grantee lee los suyos, solo el superadmin escribe.
El upsert usa los índices únicos PARCIALES (grantee,target) y (grantee, ALL).
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncConnection

_COLS = (
    "grant_id, grantee_tenant_id, target_tenant_id, target_all, "
    "can_view_metadata, can_view_data, created_by, created_at, updated_at"
)

_LIST = text(
    f"SELECT {_COLS} FROM visibility_grants "
    "WHERE (CAST(:grantee AS uuid) IS NULL OR grantee_tenant_id = CAST(:grantee AS uuid)) "
    "ORDER BY created_at DESC, grant_id"
)

_UPSERT_SPECIFIC = text(
    "INSERT INTO visibility_grants (grantee_tenant_id, target_tenant_id, target_all, "
    "can_view_metadata, can_view_data, created_by) VALUES "
    "(CAST(:grantee AS uuid), CAST(:target AS uuid), false, :meta, :data, CAST(:by AS uuid)) "
    "ON CONFLICT (grantee_tenant_id, target_tenant_id) WHERE NOT target_all "
    "DO UPDATE SET can_view_metadata = EXCLUDED.can_view_metadata, "
    "can_view_data = EXCLUDED.can_view_data, updated_at = now() "
    f"RETURNING {_COLS}"
)

_UPSERT_ALL = text(
    "INSERT INTO visibility_grants (grantee_tenant_id, target_tenant_id, target_all, "
    "can_view_metadata, can_view_data, created_by) VALUES "
    "(CAST(:grantee AS uuid), NULL, true, :meta, :data, CAST(:by AS uuid)) "
    "ON CONFLICT (grantee_tenant_id) WHERE target_all "
    "DO UPDATE SET can_view_metadata = EXCLUDED.can_view_metadata, "
    "can_view_data = EXCLUDED.can_view_data, updated_at = now() "
    f"RETURNING {_COLS}"
)

_DELETE = text(
    "DELETE FROM visibility_grants WHERE grant_id = CAST(:id AS uuid) "
    "RETURNING grant_id, grantee_tenant_id"
)


async def list_grants(conn: AsyncConnection, grantee: str | None) -> Sequence[Row]:
    """Grants visibles (RLS). ``grantee`` opcional filtra los de un cliente."""
    return (await conn.execute(_LIST, {"grantee": grantee})).all()


async def upsert_grant(
    conn: AsyncConnection,
    *,
    grantee: str,
    target: str | None,
    target_all: bool,
    meta: bool,
    data: bool,
    by: str,
) -> Row:
    """Inserta o actualiza el grant (grantee→target|ALL). Devuelve la fila completa."""
    stmt = _UPSERT_ALL if target_all else _UPSERT_SPECIFIC
    params = {"grantee": grantee, "meta": meta, "data": data, "by": by}
    if not target_all:
        params["target"] = target
    return (await conn.execute(stmt, params)).one()


async def delete_grant(conn: AsyncConnection, grant_id: str) -> Row | None:
    """Borra el grant; devuelve (grant_id, grantee) o None si no existía."""
    return (await conn.execute(_DELETE, {"id": grant_id})).first()
