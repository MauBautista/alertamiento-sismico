"""GET /sensors?site_id= — sensores de un sitio (T-1.22 · B1).

Misma autz que el catálogo de sitios (rol web + RLS por tenant). Un ``site_id`` de
otro tenant devuelve lista vacía (RLS tapa sus sensores), nunca datos ajenos.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.auth.deps import require_roles, require_web_surface
from takab_api.auth.matrix import ROLE_ROUTE_MATRIX
from takab_api.queries import sensors as q
from takab_api.routers._common import read_session
from takab_api.schemas.sensors import SensorOut

_WEB_ROLES: tuple[str, ...] = tuple(sorted(r for r, routes in ROLE_ROUTE_MATRIX.items() if routes))

router = APIRouter(dependencies=[Depends(require_web_surface), Depends(require_roles(*_WEB_ROLES))])


@router.get("/sensors", response_model=list[SensorOut])
async def list_sensors(
    site_id: UUID, conn: AsyncConnection = Depends(read_session)
) -> list[SensorOut]:
    """Sensores del sitio ``site_id`` (RLS por tenant)."""
    rows = await q.list_sensors(conn, site_id)
    return [SensorOut(**dict(r._mapping)) for r in rows]
