"""GET /catalog/earthquakes — catálogo de referencia SSN/USGS (T-1.48).

Tabla GLOBAL sin tenant (excepción documentada, familia de seismic_events):
cualquier rol web autenticado la lee (RLS ``app_role() IS NOT NULL``); nadie
la escribe vía API (solo seeds). El Triage la muestra claramente separada del
historial del tenant.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.auth.claims import Claims
from takab_api.auth.deps import get_session, require_web_surface
from takab_api.routers._common import http_error
from takab_api.schemas.catalog import CatalogEarthquakeList, CatalogEarthquakeOut

router = APIRouter()

#: [T-9.61 · D-46] Paginado por cursor. Hasta aquí devolvía la tabla entera (13
#: sismos); con el worker `catalog-sync` son cientos.
#:
#: ⚠️ El cursor es el PAR ``(origin_time, ref_id)`` y no la hora sola: el SSN y el USGS
#: citan el mismo sismo al mismo segundo, y con ``origin_time < :t`` el que caía justo
#: detrás del borde de página no volvía nunca. El orden tiene que ser el del par, los
#: dos descendentes, para que la comparación de filas corte en el mismo sitio.
_LIST_SQL = text(
    "SELECT ref_id, catalog_key, origin_time, magnitude::float8 AS magnitude, "
    "place, ST_Y(epicenter::geometry) AS lat, ST_X(epicenter::geometry) AS lon, "
    "depth_km::float8 AS depth_km, source, source_ref, notes, usgs_url, origen "
    "FROM reference_earthquakes "
    "WHERE (CAST(:t AS timestamptz) IS NULL "
    "       OR (origin_time, ref_id) < (CAST(:t AS timestamptz), CAST(:id AS uuid))) "
    "ORDER BY origin_time DESC, ref_id DESC LIMIT :limite"
)

#: Separador del cursor opaco ``<origin_time ISO>~<ref_id>``.
_SEP = "~"

#: El MENOR uuid: con él, un cursor de sólo hora (el formato anterior) corta en
#: ``origin_time < hora``, porque ningún ``ref_id`` es menor.
_UUID_MIN = "00000000-0000-0000-0000-000000000000"


def _lee_cursor(cursor: str | None) -> tuple[datetime | None, str]:
    """``(hora, ref_id)`` del cursor; 422 si no se entiende."""
    if not cursor:
        return None, _UUID_MIN
    hora, _, ref_id = cursor.partition(_SEP)
    try:
        t = datetime.fromisoformat(hora)
        return t, str(UUID(ref_id)) if ref_id else _UUID_MIN
    except ValueError as exc:
        raise http_error(422, "cursor de catálogo inválido") from exc


@router.get("/catalog/earthquakes", response_model=CatalogEarthquakeList)
async def list_reference_earthquakes(
    limit: int = Query(100, ge=1, le=500),
    antes_de: str | None = Query(
        None, description="Cursor opaco: el `siguiente` de la página anterior."
    ),
    _claims: Claims = Depends(require_web_surface),
    conn: AsyncConnection = Depends(get_session),
) -> CatalogEarthquakeList:
    """Sismos de referencia, más recientes primero, de ``limit`` en ``limit``."""
    t, ref_id = _lee_cursor(antes_de)
    rows = (await conn.execute(_LIST_SQL, {"t": t, "id": ref_id, "limite": limit})).mappings().all()
    items = [CatalogEarthquakeOut(**dict(r)) for r in rows]
    # Página llena ⇒ puede haber más. Una página justo del tamaño del resto pide
    # una vuelta más que vuelve vacía: es el precio de no contar la tabla entera.
    ultimo = items[-1] if items else None
    siguiente = (
        f"{ultimo.origin_time.isoformat()}{_SEP}{ultimo.ref_id}"
        if ultimo is not None and len(items) == limit
        else None
    )
    return CatalogEarthquakeList(items=items, siguiente=siguiente)
