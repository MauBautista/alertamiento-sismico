"""SQL del catálogo de sitios (lectura T-1.22 · B1, escritura T-1.32).

RLS de ``sites``/``zones`` filtra por tenant. La escritura NO recibe el ``tenant_id``
del cuerpo: se lo pasa el router ya resuelto contra los claims
(``routers._common.resolve_write_tenant``).

``xmin::text AS row_version`` expone el id de transacción de la fila como testigo de
concurrencia optimista. Es un contador de 32 bits que da la vuelta cada ~4 mil
millones de transacciones; una colisión exigiría que la fila NO cambiara en toda una
vuelta completa y que el siguiente escritor cayera exactamente en el mismo xid. El
riesgo es despreciable frente a la alternativa (lost update silencioso).
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncConnection

# geom es geography(Point,4326): se castea a geometry para ST_Y/ST_X (lat/lon).
_COLS = (
    "site_id, tenant_id, code, name, timezone, criticality, "
    "ST_Y(geom::geometry) AS lat, ST_X(geom::geometry) AS lon, "
    "address, building_type, status, xmin::text AS row_version, created_at"
)

_GEOM = "ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography"

_LIST = text(f"SELECT {_COLS} FROM sites WHERE status = 'active' ORDER BY code, site_id")
_LIST_ALL = text(f"SELECT {_COLS} FROM sites ORDER BY code, site_id")
_GET = text(f"SELECT {_COLS} FROM sites WHERE site_id = :id")
_ZONES = text(
    "SELECT zone_id, name, level_code FROM zones WHERE site_id = :id ORDER BY name, zone_id"
)

_INSERT = text(
    "INSERT INTO sites (tenant_id, code, name, timezone, criticality, geom, "
    "address, building_type) "
    "VALUES (CAST(:tenant_id AS uuid), :code, :name, :timezone, :criticality, "
    f"{_GEOM}, :address, :building_type) "
    f"RETURNING {_COLS}"
)

# El guardia de versión va en el WHERE: 0 filas ⇒ alguien más escribió (409). El
# router ya comprobó existencia/visibilidad con _GET, así que 0 filas aquí no es 404.
_UPDATE = text(
    "UPDATE sites SET code = :code, name = :name, timezone = :timezone, "
    f"criticality = :criticality, geom = {_GEOM}, address = :address, "
    "building_type = :building_type, status = :status "
    "WHERE site_id = :id "
    "  AND (CAST(:base_row_version AS text) IS NULL "
    "       OR xmin::text = CAST(:base_row_version AS text)) "
    f"RETURNING {_COLS}"
)

# Retiro lógico e idempotente: retirar dos veces devuelve la misma fila.
_RETIRE = text(f"UPDATE sites SET status = 'retired' WHERE site_id = :id RETURNING {_COLS}")


async def list_sites(conn: AsyncConnection, *, include_retired: bool = False) -> Sequence[Row]:
    """Sitios visibles al request (RLS por tenant). Los retirados solo si se piden."""
    return (await conn.execute(_LIST_ALL if include_retired else _LIST)).all()


async def get_site(conn: AsyncConnection, site_id: UUID) -> Row | None:
    """Un sitio por id, o ``None`` si no existe/no es visible (RLS)."""
    return (await conn.execute(_GET, {"id": site_id})).first()


async def list_zones_for_site(conn: AsyncConnection, site_id: UUID) -> Sequence[Row]:
    """Zonas de un sitio (RLS por tenant)."""
    return (await conn.execute(_ZONES, {"id": site_id})).all()


async def insert_site(conn: AsyncConnection, *, tenant_id: str, values: dict) -> Row:
    """Inserta el sitio. ``tenant_id`` viene resuelto por el router, no por el cuerpo."""
    return (await conn.execute(_INSERT, {**values, "tenant_id": tenant_id})).one()


async def update_site(
    conn: AsyncConnection, *, site_id: UUID, values: dict, base_row_version: str | None
) -> Row | None:
    """Reemplaza el sitio. ``None`` = otro escritor ganó la carrera (⇒ 409)."""
    params = {**values, "id": site_id, "base_row_version": base_row_version}
    return (await conn.execute(_UPDATE, params)).first()


async def retire_site(conn: AsyncConnection, site_id: UUID) -> Row | None:
    """Marca el sitio como ``retired``. ``None`` si RLS no lo deja tocarlo."""
    return (await conn.execute(_RETIRE, {"id": site_id})).first()
