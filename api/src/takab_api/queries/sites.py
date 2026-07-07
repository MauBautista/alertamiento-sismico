"""SQL del catálogo de sitios (T-1.22 · B1). RLS de ``sites``/``zones`` filtra por tenant."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncConnection

# geom es geography(Point,4326): se castea a geometry para ST_Y/ST_X (lat/lon).
_COLS = (
    "site_id, tenant_id, code, name, timezone, criticality, "
    "ST_Y(geom::geometry) AS lat, ST_X(geom::geometry) AS lon, "
    "address, building_type, created_at"
)

_LIST = text(f"SELECT {_COLS} FROM sites ORDER BY code, site_id")
_GET = text(f"SELECT {_COLS} FROM sites WHERE site_id = :id")
_ZONES = text(
    "SELECT zone_id, name, level_code FROM zones WHERE site_id = :id ORDER BY name, zone_id"
)


async def list_sites(conn: AsyncConnection) -> Sequence[Row]:
    """Sitios visibles al request (RLS por tenant)."""
    return (await conn.execute(_LIST)).all()


async def get_site(conn: AsyncConnection, site_id: UUID) -> Row | None:
    """Un sitio por id, o ``None`` si no existe/no es visible (RLS)."""
    return (await conn.execute(_GET, {"id": site_id})).first()


async def list_zones_for_site(conn: AsyncConnection, site_id: UUID) -> Sequence[Row]:
    """Zonas de un sitio (RLS por tenant)."""
    return (await conn.execute(_ZONES, {"id": site_id})).all()
