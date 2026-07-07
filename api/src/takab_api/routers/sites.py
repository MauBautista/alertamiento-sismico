"""GET /sites, GET /sites/{id} — catálogo de sitios (T-1.22 · B1).

Autz (RBAC §2): cualquier rol con superficie web y acceso a alguna vista SOC ve
el catálogo (todos tienen al menos Consola C4I). Los roles móvil-only quedan fuera
(conjunto de rutas vacío). RLS filtra las filas por tenant.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.auth.deps import require_roles, require_web_surface
from takab_api.auth.matrix import ROLE_ROUTE_MATRIX
from takab_api.queries import sites as q
from takab_api.routers._common import http_error, read_session
from takab_api.schemas.sites import SiteDetailOut, SiteOut, ZoneOut

# Roles con al menos una vista web (espejo de RBAC §2 vía matrix.py).
_WEB_ROLES: tuple[str, ...] = tuple(sorted(r for r, routes in ROLE_ROUTE_MATRIX.items() if routes))

router = APIRouter(dependencies=[Depends(require_web_surface), Depends(require_roles(*_WEB_ROLES))])


@router.get("/sites", response_model=list[SiteOut])
async def list_sites(conn: AsyncConnection = Depends(read_session)) -> list[SiteOut]:
    """Sitios del tenant (superadmin/support ven todos vía RLS)."""
    rows = await q.list_sites(conn)
    return [SiteOut(**dict(r._mapping)) for r in rows]


@router.get("/sites/{site_id}", response_model=SiteDetailOut)
async def get_site(site_id: UUID, conn: AsyncConnection = Depends(read_session)) -> SiteDetailOut:
    """Detalle de un sitio con sus zonas. 404 si no existe o no es visible (RLS)."""
    row = await q.get_site(conn, site_id)
    if row is None:
        raise http_error(404, "sitio no encontrado")
    zones = await q.list_zones_for_site(conn, site_id)
    return SiteDetailOut(
        **dict(row._mapping),
        zones=[ZoneOut(**dict(z._mapping)) for z in zones],
    )
