"""GET /catalog/earthquakes — catálogo de referencia SSN/USGS (T-1.48).

Tabla GLOBAL sin tenant (excepción documentada, familia de seismic_events):
cualquier rol web autenticado la lee (RLS ``app_role() IS NOT NULL``); nadie
la escribe vía API (solo seeds). El Triage la muestra claramente separada del
historial del tenant.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.auth.claims import Claims
from takab_api.auth.deps import get_session, require_web_surface
from takab_api.schemas.catalog import CatalogEarthquakeList, CatalogEarthquakeOut

router = APIRouter()

_LIST_SQL = text(
    "SELECT ref_id, catalog_key, origin_time, magnitude::float8 AS magnitude, "
    "place, ST_Y(epicenter::geometry) AS lat, ST_X(epicenter::geometry) AS lon, "
    "depth_km::float8 AS depth_km, source, source_ref, notes "
    "FROM reference_earthquakes ORDER BY origin_time DESC"
)


@router.get("/catalog/earthquakes", response_model=CatalogEarthquakeList)
async def list_reference_earthquakes(
    _claims: Claims = Depends(require_web_surface),
    conn: AsyncConnection = Depends(get_session),
) -> CatalogEarthquakeList:
    """Sismos de referencia, más recientes primero."""
    rows = (await conn.execute(_LIST_SQL)).mappings().all()
    return CatalogEarthquakeList(items=[CatalogEarthquakeOut(**dict(r)) for r in rows])
