"""SQL del catálogo de sensores (lectura T-1.22 · B1, escritura T-1.32).

RLS de ``sensors`` filtra por tenant. El ``tenant_id`` de un sensor nuevo lo hereda del
sitio padre (lo resuelve el router), no del cuerpo.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncConnection

_COLS = (
    "sensor_id, site_id, gateway_id, zone_id, kind, model, serial, "
    "channels, sample_rate, mount, "
    "ST_Y(geom::geometry) AS lat, ST_X(geom::geometry) AS lon, "
    "status, xmin::text AS row_version"
)

# geom es opcional: un sensor sin coordenadas propias hereda la del sitio en el mapa.
_GEOM = (
    "CASE WHEN CAST(:lat AS float8) IS NULL THEN NULL "
    "ELSE ST_SetSRID(ST_MakePoint(CAST(:lon AS float8), CAST(:lat AS float8)), 4326)::geography "
    "END"
)

_LIST = text(
    f"SELECT {_COLS} FROM sensors WHERE site_id = :site_id ORDER BY serial NULLS LAST, sensor_id"
)
_GET = text(f"SELECT {_COLS} FROM sensors WHERE sensor_id = :id")
_GET_TENANT = text("SELECT tenant_id FROM sensors WHERE sensor_id = :id")

_INSERT = text(
    "INSERT INTO sensors (tenant_id, site_id, gateway_id, zone_id, kind, model, serial, "
    "channels, sample_rate, mount, geom) "
    "VALUES (CAST(:tenant_id AS uuid), :site_id, :gateway_id, :zone_id, :kind, :model, "
    f":serial, :channels, :sample_rate, :mount, {_GEOM}) "
    f"RETURNING {_COLS}"
)

_UPDATE = text(
    "UPDATE sensors SET site_id = :site_id, gateway_id = :gateway_id, zone_id = :zone_id, "
    "kind = :kind, model = :model, serial = :serial, channels = :channels, "
    f"sample_rate = :sample_rate, mount = :mount, geom = {_GEOM}, status = :status "
    "WHERE sensor_id = :id "
    "  AND (CAST(:base_row_version AS text) IS NULL "
    "       OR xmin::text = CAST(:base_row_version AS text)) "
    f"RETURNING {_COLS}"
)

_RETIRE = text(f"UPDATE sensors SET status = 'retired' WHERE sensor_id = :id RETURNING {_COLS}")


async def list_sensors(conn: AsyncConnection, site_id: UUID) -> Sequence[Row]:
    """Sensores de un sitio (RLS por tenant; un sitio ajeno devuelve 0 filas)."""
    return (await conn.execute(_LIST, {"site_id": site_id})).all()


async def get_sensor(conn: AsyncConnection, sensor_id: UUID) -> Row | None:
    """Un sensor por id, o ``None`` si no existe/no es visible (RLS)."""
    return (await conn.execute(_GET, {"id": sensor_id})).first()


async def get_sensor_tenant(conn: AsyncConnection, sensor_id: UUID) -> str | None:
    """Tenant dueño del sensor (``None`` si RLS lo oculta)."""
    row = (await conn.execute(_GET_TENANT, {"id": sensor_id})).first()
    return None if row is None else str(row.tenant_id)


async def insert_sensor(conn: AsyncConnection, *, tenant_id: str, values: dict) -> Row:
    """Inserta el sensor. ``tenant_id`` viene del sitio padre, resuelto por el router."""
    return (await conn.execute(_INSERT, {**values, "tenant_id": tenant_id})).one()


async def update_sensor(
    conn: AsyncConnection, *, sensor_id: UUID, values: dict, base_row_version: str | None
) -> Row | None:
    """Reemplaza el sensor. ``None`` = otro escritor ganó la carrera (⇒ 409)."""
    params = {**values, "id": sensor_id, "base_row_version": base_row_version}
    return (await conn.execute(_UPDATE, params)).first()


async def retire_sensor(conn: AsyncConnection, sensor_id: UUID) -> Row | None:
    """Retiro lógico del sensor. ``None`` si RLS no lo deja tocarlo."""
    return (await conn.execute(_RETIRE, {"id": sensor_id})).first()
