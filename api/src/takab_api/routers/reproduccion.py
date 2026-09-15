"""GET /incidents/{id}/reproduccion — el plan de arribos de una reproducción (T-7.14).

Lectura pura, sin acción nueva en la matriz: quien ve el incidente ve su plan. La
RLS ya decidió qué incidentes existen para este request, y 404 —no 403— cuando no
es visible, porque un 403 confirmaría que existe.

**404 también cuando el incidente NO es una reproducción**, y eso es deliberado:
esta ruta responde «cuándo llega la onda a cada estación **según el sismo que se
está reproduciendo**». Un incidente real no tiene esa respuesta, y devolver un
plan calculado sobre su epicentro estimado sería presentar una simulación como si
fuera la medición — que es exactamente lo que `meta.reproduccion` existe para
distinguir.

El plan se **recalcula** en cada lectura en vez de guardarse: es una función pura
de datos que ya están en la base (el evento y los sitios), y una copia congelada
se quedaría vieja el día que un sitio se mueva o cambie una velocidad.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.auth.deps import require_web_surface
from takab_api.replay.plan import Estacion, Sismo, plan_de_arribos, velocidades
from takab_api.routers._common import http_error, read_session
from takab_api.schemas.replay import ArriboOut, ReproduccionOut
from takab_api.settings import Settings

router = APIRouter(dependencies=[Depends(require_web_surface)])

_INCIDENTE = text("""
SELECT i.incident_id, i.tenant_id, i.event_id,
       e.magnitude, e.depth_km, e.meta,
       ST_Y(e.epicenter::geometry) AS lat, ST_X(e.epicenter::geometry) AS lon,
       -- [T-7.20] La procedencia sale del CATÁLOGO, no del evento vestido: es la
       -- fuente quien sostiene la cifra, y quien la declara revisada o no.
       c.place, c.source AS catalog_source, c.review_status
  FROM incidents i
  JOIN seismic_events e ON e.event_id = i.event_id
  LEFT JOIN reference_earthquakes c
         ON c.catalog_key = e.meta->'reproduccion'->>'catalog_key'
 WHERE i.incident_id = CAST(:i AS uuid)
""")

_ESTACIONES = text("""
SELECT DISTINCT s.site_id, s.code,
       ST_Y(s.geom::geometry) AS lat, ST_X(s.geom::geometry) AS lon
  FROM sites s
  JOIN gateways g ON g.site_id = s.site_id AND g.status <> 'retired'
 WHERE s.tenant_id = CAST(:t AS uuid)
 ORDER BY s.code
""")


@router.get("/incidents/{incident_id}/reproduccion", response_model=ReproduccionOut)
async def incident_reproduccion(
    incident_id: UUID,
    conn: AsyncConnection = Depends(read_session),
) -> ReproduccionOut:
    """Qué sismo se reproduce y cuándo le llega la onda a cada estación."""
    fila = (await conn.execute(_INCIDENTE, {"i": str(incident_id)})).first()
    if fila is None:
        raise http_error(404, "incidente no encontrado")
    rep = (fila.meta or {}).get("reproduccion")
    if not rep:
        raise http_error(404, "este incidente no es una reproducción")

    settings = Settings()
    v_p_km_s = float((fila.meta or {}).get("v_p_km_s") or 0.0)
    v_s_km_s = float((fila.meta or {}).get("v_s_km_s") or 0.0)
    if v_p_km_s <= 0 or v_s_km_s <= 0:
        # Un evento vestido antes de que las velocidades viajaran en el meta.
        v_p_km_s, v_s_km_s = velocidades(settings.replay_v_s_km_s)

    sismo = Sismo(
        catalog_key=rep["catalog_key"],
        magnitude=float(fila.magnitude or 0.0),
        lat=float(fila.lat),
        lon=float(fila.lon),
        depth_km=None if fila.depth_km is None else float(fila.depth_km),
        v_s_km_s=v_s_km_s,
        v_p_km_s=v_p_km_s,
    )
    estaciones = [
        Estacion(str(r.site_id), r.code, float(r.lat), float(r.lon))
        for r in (await conn.execute(_ESTACIONES, {"t": str(fila.tenant_id)})).all()
    ]
    return ReproduccionOut(
        incident_id=str(incident_id),
        event_id=fila.event_id,
        catalog_key=rep["catalog_key"],
        magnitude=None if fila.magnitude is None else float(fila.magnitude),
        lat=float(fila.lat),
        lon=float(fila.lon),
        depth_km=None if fila.depth_km is None else float(fila.depth_km),
        t0_real=rep["t0_real"],
        t0_demo=rep["t0_demo"],
        place=fila.place,
        catalog_source=fila.catalog_source,
        review_status=fila.review_status,
        v_p_km_s=sismo.v_p_km_s,
        v_s_km_s=sismo.v_s_km_s,
        arrivals=[
            ArriboOut(
                site_id=a.site_id,
                site_code=a.site_code,
                epi_km=a.epi_km,
                hypo_km=a.hypo_km,
                t_p_s=a.t_p_s,
                t_s_s=a.t_s_s,
                pga_g=a.pga_g,
            )
            for a in plan_de_arribos(sismo, estaciones)
        ],
    )
