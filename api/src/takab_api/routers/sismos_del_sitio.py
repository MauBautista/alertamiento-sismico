"""[T-9.61 · T-9.66 · D-46] Los sismos del catálogo vistos DESDE un inmueble.

- ``GET /sites/{id}/sismos``              — sismos publicados por USGS cerca del
  inmueble (app móvil), con lo que se ESTIMA que hicieron ahí.
- ``GET /sites/{id}/historial-sismico``   — lo que vivió el inmueble: sus
  incidentes (MEDIDOS) y los sismos que ahí se habrían sentido (ESTIMADOS, MMI ≥
  III), en una sola lista.

Alcance: ``assert_site_access`` (R2), el mismo que los demás ``/sites/{id}/…`` de
``mobile_site.py``; la RLS acota el tenant SIEMPRE, así que un sitio ajeno es 404.

Todo es POSTERIOR al evento (D-46): ni cuenta regresiva ni magnitud preliminar en
vivo. La magnitud aquí es la del catálogo publicado, como en ``/catalog/earthquakes``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.auth.claims import Claims
from takab_api.auth.deps import get_claims, get_session, require_roles
from takab_api.catalogo.en_el_sitio import METODO, estima
from takab_api.queries import mobile as q
from takab_api.schemas.catalog import (
    HistorialIncidente,
    HistorialSismicoOut,
    HistorialSismo,
    SismoCercanoOut,
    SismoEnTuInmuebleEstimado,
    SismosDelSitioOut,
)
from takab_api.shakemap import gmice

router = APIRouter()

#: Los roles móviles con acceso a un sitio (D-42): ocupante, brigadista, inspector
#: y administrador. Los alias heredados entran ya canonizados por ``Claims``.
_require_movil_del_sitio = require_roles("occupant", "brigadista", "inspector", "tenant_admin")

#: [T-9.66] El umbral del historial: III es la primera intensidad que la gente
#: SIENTE dentro de un edificio. Por debajo, el sismo no le pasó al inmueble.
#: Se compara el GRADO que se enseña (`gmice.romano`, al entero más cercano) y no el
#: número crudo: con `≥ 3.0`, una estimación de 2.87 se pintaba «III» en la app y a
#: la vez quedaba fuera del historial, que es contradecirse en la misma pantalla.
GRADO_MINIMO_HISTORIAL = "III"

_ROMANOS = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X")


def _grado_de(romano: str) -> int:
    return _ROMANOS.index(romano) + 1


def _grado(mmi: float) -> int:
    """El grado ENTERO que se enseña: el mismo redondeo que `gmice.romano`."""
    return _grado_de(gmice.romano(mmi))


#: Cota de filas por consulta. El catálogo de M≥4 en la caja de México son unos
#: cientos al año; la cota impide que una ventana absurda traiga la tabla entera.
_MAX_FILAS = 500

_SITIO_SQL = text(
    "SELECT ST_Y(geom::geometry)::float8 AS lat, ST_X(geom::geometry)::float8 AS lon "
    "FROM sites WHERE site_id = CAST(:site AS uuid)"
)

_ESTADO_SQL = text("SELECT estado, ultimo_ok FROM catalog_sync_state WHERE fuente = 'USGS'")

_SISMOS_SQL = text(
    "SELECT catalog_key, origin_time, magnitude::float8 AS magnitude, place, "
    "ST_Y(epicenter::geometry)::float8 AS lat, ST_X(epicenter::geometry)::float8 AS lon, "
    "depth_km::float8 AS depth_km, usgs_url, review_status "
    "FROM reference_earthquakes "
    "WHERE origin_time >= :desde AND magnitude >= :min_mag "
    "  AND (CAST(:source AS text) IS NULL OR source = :source) "
    "ORDER BY origin_time DESC LIMIT :limite"
)

_INCIDENTES_SQL = text(
    "SELECT i.incident_id, i.opened_at, i.severity, i.trigger, i.state AS estado, "
    "c.classification AS clasificacion, i.max_pga_g::float8 AS pga_medida_g "
    "FROM incidents i "
    "LEFT JOIN LATERAL ("
    "  SELECT cc.classification FROM incident_classifications cc "
    "   WHERE cc.incident_id = i.incident_id "
    "     AND NOT EXISTS (SELECT 1 FROM incident_classifications s "
    "                      WHERE s.supersedes_id = cc.classification_id) "
    "   ORDER BY cc.classified_at DESC, cc.classification_id DESC LIMIT 1"
    ") c ON true "
    "WHERE i.site_id = CAST(:site AS uuid) AND i.opened_at >= :desde "
    "ORDER BY i.opened_at DESC LIMIT :limite"
)

#: Los sismos del catálogo que YA son un incidente de ESTE sitio. Dos caminos lo
#: dejan escrito: la consulta por incidente de T-7.25 (``correlacionado``) y el
#: epicentro con el que se vistió el mapa de la sacudida (T-7.24).
_YA_SON_INCIDENTE_SQL = text(
    "SELECT cc.catalog_key AS k FROM catalog_consultations cc "
    "  JOIN incidents i ON i.incident_id = cc.incident_id "
    " WHERE i.site_id = CAST(:site AS uuid) AND cc.outcome = 'correlacionado' "
    "   AND cc.catalog_key IS NOT NULL "
    "UNION "
    "SELECT sm.epicentro->>'catalog_key' AS k FROM incident_shakemap sm "
    "  JOIN incidents i ON i.incident_id = sm.incident_id "
    " WHERE i.site_id = CAST(:site AS uuid) AND sm.epicentro->>'catalog_key' IS NOT NULL"
)


async def _coordenadas(conn: AsyncConnection, site_id: UUID) -> Any:
    return (await conn.execute(_SITIO_SQL, {"site": str(site_id)})).one()


@router.get("/sites/{site_id}/sismos", response_model=SismosDelSitioOut)
async def sismos_del_sitio(
    site_id: UUID,
    dias: int = Query(90, ge=1, le=365),
    min_mag: float = Query(4.0, ge=0.0, le=10.0),
    claims: Claims = Depends(_require_movil_del_sitio),
    conn: AsyncConnection = Depends(get_session),
) -> SismosDelSitioOut:
    """[T-9.61] Sismos publicados por USGS en los últimos ``dias``, más reciente primero.

    Sólo filas de USGS: la respuesta lleva la atribución de USGS, y una del SSN
    bajo ese rótulo citaría mal su fuente.
    """
    await q.assert_site_access(conn, claims, site_id)
    sitio = await _coordenadas(conn, site_id)
    desde = datetime.now(tz=UTC) - timedelta(days=dias)
    filas = (
        (
            await conn.execute(
                _SISMOS_SQL,
                {"desde": desde, "min_mag": min_mag, "source": "USGS", "limite": _MAX_FILAS},
            )
        )
        .mappings()
        .all()
    )
    items = []
    for f in filas:
        e = estima(
            sitio_lat=sitio.lat,
            sitio_lon=sitio.lon,
            lat=f["lat"],
            lon=f["lon"],
            magnitud=f["magnitude"],
            depth_km=f["depth_km"],
        )
        items.append(
            SismoCercanoOut(
                origin_time=f["origin_time"],
                magnitude=f["magnitude"],
                place=f["place"],
                lat=f["lat"],
                lon=f["lon"],
                depth_km=f["depth_km"],
                usgs_url=f["usgs_url"],
                review_status=f["review_status"],
                en_tu_inmueble=SismoEnTuInmuebleEstimado(
                    dist_km=e.dist_km,
                    pga_estimada_g=e.pga_estimada_g,
                    mmi_estimada=e.mmi_estimada,
                    mmi_romano=e.mmi_romano,
                    metodo=METODO,
                ),
            )
        )
    estado = (await conn.execute(_ESTADO_SQL)).first()
    return SismosDelSitioOut(
        items=items,
        # Sin fila = el worker no ha corrido nunca. Se DICE, no se deja vacío.
        actualizado=estado.ultimo_ok if estado else None,
        sync_estado=estado.estado if estado else "nunca",
    )


@router.get("/sites/{site_id}/historial-sismico", response_model=HistorialSismicoOut)
async def historial_sismico(
    site_id: UUID,
    dias: int = Query(365, ge=1, le=3650),
    claims: Claims = Depends(get_claims),
    conn: AsyncConnection = Depends(get_session),
) -> HistorialSismicoOut:
    """[T-9.66] Incidentes del inmueble + sismos que ahí se habrían sentido.

    Una sola ruta para las dos superficies (``BuildingPage`` en la web y la app):
    ``get_claims`` + ``assert_site_access``, como ``/sites/{id}/drills``. El
    alcance lo decide el sitio, no la superficie.
    """
    await q.assert_site_access(conn, claims, site_id)
    sitio = await _coordenadas(conn, site_id)
    desde = datetime.now(tz=UTC) - timedelta(days=dias)
    params = {"site": str(site_id), "desde": desde, "limite": _MAX_FILAS}

    eventos: list[tuple[datetime, HistorialIncidente | HistorialSismo]] = [
        (r["opened_at"], HistorialIncidente(**dict(r)))
        for r in (await conn.execute(_INCIDENTES_SQL, params)).mappings().all()
    ]
    ya_son = {r.k for r in (await conn.execute(_YA_SON_INCIDENTE_SQL, params)).all()}
    sismos = (
        (
            await conn.execute(
                _SISMOS_SQL,
                {"desde": desde, "min_mag": 0.0, "source": None, "limite": _MAX_FILAS},
            )
        )
        .mappings()
        .all()
    )
    for f in sismos:
        if f["catalog_key"] in ya_son:
            continue  # ya va como incidente: una sola vez, como lo que MIDIÓ el sitio
        e = estima(
            sitio_lat=sitio.lat,
            sitio_lon=sitio.lon,
            lat=f["lat"],
            lon=f["lon"],
            magnitud=f["magnitude"],
            depth_km=f["depth_km"],
        )
        if e.mmi_estimada is None or _grado(e.mmi_estimada) < _grado_de(GRADO_MINIMO_HISTORIAL):
            continue
        eventos.append(
            (
                f["origin_time"],
                HistorialSismo(
                    origin_time=f["origin_time"],
                    magnitude=f["magnitude"],
                    place=f["place"],
                    dist_km=e.dist_km,
                    mmi_estimada=e.mmi_estimada,
                    mmi_romano=e.mmi_romano or "",
                    usgs_url=f["usgs_url"],
                ),
            )
        )
    eventos.sort(key=lambda par: par[0], reverse=True)
    return HistorialSismicoOut(eventos=[ev for _, ev in eventos])
