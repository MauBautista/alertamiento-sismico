"""SQL del catálogo de sensores (T-1.22 · B1). RLS de ``sensors`` filtra por tenant."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncConnection

_LIST = text(
    "SELECT sensor_id, site_id, gateway_id, zone_id, kind, model, serial, "
    "channels, sample_rate, mount, status "
    "FROM sensors WHERE site_id = :site_id ORDER BY serial NULLS LAST, sensor_id"
)


async def list_sensors(conn: AsyncConnection, site_id: UUID) -> Sequence[Row]:
    """Sensores de un sitio (RLS por tenant; un sitio ajeno devuelve 0 filas)."""
    return (await conn.execute(_LIST, {"site_id": site_id})).all()
