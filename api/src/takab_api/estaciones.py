"""[T-7.17] La red de estaciones frente a un incidente: lo medido y lo esperado.

Un pico suelto no dice nada —¿mucho o poco para esta distancia?— y un valor
teórico suelto es una simulación. La tabla los pone uno al lado del otro, por
estación y **en orden de arribo**, que es el orden en que ocurrió.

Tres decisiones que no son de presentación:

* **El ancla se DECLARA.** Los arribos se cuentan desde el origen del sismo
  (`seismic_events.detected_at`) cuando hay evento, y desde la apertura del
  incidente cuando no. Dos tablas con anclas distintas comparadas como si
  midieran lo mismo es un error que no se ve.
* **«Sobre umbral» es el umbral del INMUEBLE**, resuelto con el mismo
  `umbral_de_comparacion` que usan la banda y el dictamen — y con su procedencia
  al lado. Un umbral de fábrica presentado como del edificio es el defecto que
  cerró `T-7.35`.
* **`tier = None` no es `normal`.** Un gabinete que no publicó ninguna transición
  no dijo que estuviera en calma: no dijo nada (regla de oro 7).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import text

from takab_api.forensics import umbral_de_comparacion
from takab_api.replay.plan import Estacion, Sismo, arribo, velocidades
from takab_api.schemas.estaciones import EstacionesOut, EstacionOut
from takab_api.settings import Settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection

#: Orden de severidad de los tiers. `manual_only` NO es «más» que evacuar: es un
#: modo de operación, y ponerlo arriba haría que un gabinete en mantenimiento
#: encabezara la tabla como si fuera el que más sintió.
_RANGO_TIER = {"normal": 0, "watch": 1, "restricted": 2, "evacuate_or_hold": 3, "manual_only": -1}

_INCIDENTE = text("""
SELECT i.incident_id, i.tenant_id, i.site_id, i.opened_at, i.event_id,
       e.detected_at, e.magnitude, e.depth_km, e.meta,
       ST_Y(e.epicenter::geometry) AS lat, ST_X(e.epicenter::geometry) AS lon
  FROM incidents i
  LEFT JOIN seismic_events e ON e.event_id = i.event_id
 WHERE i.incident_id = CAST(:i AS uuid)
""")

#: Las estaciones del cliente: sitio con gabinete no retirado. El «código» del
#: sensor es su `serial`, que es la identidad que el operador reconoce (`SIM101`,
#: `AM.R4F74`). Con un sensor por sitio —la convención de la flota— es
#: exactamente ese; con varios, la tabla nombra uno en vez de meter una lista que
#: no cabe en una celda.
_ESTACIONES = text("""
SELECT s.site_id, s.code AS site_code, s.name AS site_name,
       ST_Y(s.geom::geometry) AS lat, ST_X(s.geom::geometry) AS lon,
       (SELECT se.serial FROM sensors se
         WHERE se.site_id = s.site_id AND se.status <> 'retired'
         ORDER BY se.serial LIMIT 1) AS sensor_code
  FROM sites s
  JOIN gateways g ON g.site_id = s.site_id AND g.status <> 'retired'
 WHERE s.tenant_id = CAST(:t AS uuid)
 GROUP BY s.site_id, s.code, s.name, s.geom
""")

#: Pico del sitio en la ventana y el PRIMER segundo por encima del umbral. Los
#: dos en una sola pasada: dos consultas sobre la misma ventana se desincronizan
#: en cuanto alguien toca una.
_MEDIDO = text("""
SELECT max(wf.pga_g)::float8 AS peak_pga_g,
       (array_agg(wf.ts ORDER BY wf.pga_g DESC NULLS LAST))[1] AS peak_ts,
       min(wf.ts) FILTER (WHERE wf.pga_g >= :umbral) AS primer_ts
  FROM waveform_features_1s_secure wf
 WHERE wf.site_id = CAST(:s AS uuid)
   AND wf.ts >= CAST(:desde AS timestamptz)
   AND wf.ts <  CAST(:hasta AS timestamptz)
""")

_TIER = text("""
SELECT r.new_tier
  FROM rule_evaluations r
 WHERE r.site_id = CAST(:s AS uuid)
   AND r.ts >= CAST(:desde AS timestamptz)
   AND r.ts <  CAST(:hasta AS timestamptz)
""")

_VOTOS = text("""
SELECT se.site_id, bool_or(v.counted) AS counted
  FROM quorum_votes v
  JOIN sensors se ON se.sensor_id = v.sensor_id
 WHERE v.event_id = :e
 GROUP BY se.site_id
""")


async def build_estaciones(
    conn: AsyncConnection, incident_id: str, settings: Settings | None = None
) -> EstacionesOut | None:
    """La tabla por estación, o ``None`` si la RLS no deja ver el incidente."""
    s = settings or Settings()
    fila = (await conn.execute(_INCIDENTE, {"i": incident_id})).first()
    if fila is None:
        return None

    meta = fila.meta or {}
    rep = meta.get("reproduccion")
    # El ancla, declarada: sin ella dos tablas se comparan como si midieran lo mismo.
    ancla_ts = fila.detected_at or fila.opened_at
    ancla = "event" if fila.detected_at is not None else "incident"

    desde = fila.opened_at - timedelta(seconds=s.dictamen_pga_window_pre_s)
    hasta = fila.opened_at + timedelta(seconds=s.dictamen_pga_window_post_s)

    sismo = _sismo_de(fila, meta, s)
    votos = (
        {
            str(r.site_id): r.counted
            for r in (await conn.execute(_VOTOS, {"e": fila.event_id})).all()
        }
        if fila.event_id
        else {}
    )

    items: list[EstacionOut] = []
    for e in (await conn.execute(_ESTACIONES, {"t": str(fila.tenant_id)})).all():
        items.append(
            await _una_estacion(
                conn,
                e,
                sismo=sismo,
                ancla_ts=ancla_ts,
                desde=desde,
                hasta=hasta,
                tenant_id=str(fila.tenant_id),
                opened_at=fila.opened_at,
                counted=votos.get(str(e.site_id)),
            )
        )

    return EstacionesOut(
        incident_id=str(fila.incident_id),
        event_id=fila.event_id,
        reproduccion=bool(rep),
        ancla=ancla,
        ancla_ts=ancla_ts,
        epicentro_lat=None if sismo is None else sismo.lat,
        epicentro_lon=None if sismo is None else sismo.lon,
        magnitude=None if fila.magnitude is None else float(fila.magnitude),
        items=sorted(items, key=_orden_de_arribo),
    )


def _sismo_de(fila, meta: dict, s: Settings) -> Sismo | None:
    """El sismo del plan, si el evento tiene epicentro. `None` si no lo tiene.

    Las velocidades salen del `meta` cuando el evento las lleva escritas (las
    escribe la reproducción, `T-7.14`) y de los ajustes cuando no: reproducir con
    una velocidad y medir contra otra daría un desfase constante que parecería
    error de las estaciones.
    """
    if fila.lat is None or fila.lon is None:
        return None
    v_p = float(meta.get("v_p_km_s") or 0.0)
    v_s = float(meta.get("v_s_km_s") or 0.0)
    if v_p <= 0 or v_s <= 0:
        v_p, v_s = velocidades(s.replay_v_s_km_s)
    return Sismo(
        catalog_key=(meta.get("reproduccion") or {}).get("catalog_key") or "",
        magnitude=float(fila.magnitude or 0.0),
        lat=float(fila.lat),
        lon=float(fila.lon),
        depth_km=None if fila.depth_km is None else float(fila.depth_km),
        v_s_km_s=v_s,
        v_p_km_s=v_p,
    )


async def _una_estacion(
    conn: AsyncConnection,
    e,
    *,
    sismo: Sismo | None,
    ancla_ts: datetime,
    desde: datetime,
    hasta: datetime,
    tenant_id: str,
    opened_at: datetime,
    counted: bool | None,
) -> EstacionOut:
    umbral = await umbral_de_comparacion(
        conn, site_id=str(e.site_id), tenant_id=tenant_id, at=opened_at
    )
    piso = umbral.thresholds.pga_watch_g
    medido = (
        await conn.execute(
            _MEDIDO,
            {"s": str(e.site_id), "desde": desde, "hasta": hasta, "umbral": piso},
        )
    ).first()

    teorico = dist = None
    if sismo is not None:
        a = arribo(sismo, Estacion(str(e.site_id), e.site_code, float(e.lat), float(e.lon)))
        teorico, dist = a.t_s_s, a.epi_km

    tiers = [
        r.new_tier
        for r in (
            await conn.execute(_TIER, {"s": str(e.site_id), "desde": desde, "hasta": hasta})
        ).all()
    ]
    tier = max(tiers, key=lambda t: _RANGO_TIER.get(t, 0)) if tiers else None

    return EstacionOut(
        site_id=str(e.site_id),
        site_code=e.site_code,
        site_name=e.site_name,
        sensor_code=e.sensor_code,
        lat=float(e.lat),
        lon=float(e.lon),
        dist_km=dist,
        t_arribo_teorico_s=teorico,
        t_arribo_medido_s=(
            (medido.primer_ts - ancla_ts).total_seconds()
            if medido is not None and medido.primer_ts is not None
            else None
        ),
        peak_pga_g=None if medido is None else medido.peak_pga_g,
        peak_ts=None if medido is None else medido.peak_ts,
        umbral_pga_g=piso,
        umbral_origen=umbral.origen,
        tier=tier,
        counted=counted,
    )


def _orden_de_arribo(x: EstacionOut) -> tuple:
    """Por cuándo llegó: teórico, medido, distancia y, en último término, código.

    El código es el desempate y no el criterio: ordenar alfabéticamente una tabla
    que narra una secuencia obliga a cada lector a reordenarla mentalmente.
    """
    return (
        x.t_arribo_teorico_s if x.t_arribo_teorico_s is not None else float("inf"),
        x.t_arribo_medido_s if x.t_arribo_medido_s is not None else float("inf"),
        x.dist_km if x.dist_km is not None else float("inf"),
        x.site_code,
    )
