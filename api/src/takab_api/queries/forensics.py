"""SQL forense de un incidente (T-2.40): los hechos medidos, en un solo lugar.

Esta consulta alimenta LA PANTALLA y EL PDF. Es deliberado: dos rutas distintas para
los mismos números terminarían discrepando, y un dictamen que no coincide con lo que
el operador vio en la consola es peor que no tener dictamen.

⚠️ **La superficie de lectura usa la VISTA SEGURA, nunca la hypertable base.** La API
corre como ``takab_app`` bajo la RLS del request; la vista ``*_secure`` es
``security_barrier`` con JOIN a ``sites``, que es lo único que impide leer la
telemetría de otro cliente desde HTTP. El contract-test
``tests/contracts/test_waveform_view.py`` falla el build si este módulo nombra la
tabla base, y su allowlist NO debe ampliarse: los cuatro módulos que sí la leen son
internos de red con BYPASSRLS, no endpoints.

La ventana es la misma que usa el motor de dictamen: ``[opened_at − pga_window_pre_s,
opened_at + pga_window_post_s]``. Es asimétrica porque la sacudida llega DESPUÉS de la
alerta SASMEX — buscar el pico centrado en la apertura del incidente lo perdería.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncConnection

# Pico por canal en la ventana. `array_agg ... ORDER BY pga_g DESC` da el INSTANTE del
# pico, que es lo que permite calcular el tiempo de aviso ganado.
_CHANNEL_PEAKS = text(
    """
    SELECT wf.channel,
           max(wf.pga_g)::float8   AS peak_pga_g,
           max(wf.pgv_cms)::float8 AS peak_pgv_cms,
           max(wf.rms)::float8     AS peak_rms,
           max(wf.stalta)::float8  AS peak_stalta,
           sum(wf.energy)::float8  AS energy_sum,
           bool_or(wf.clipping)    AS clipped,
           count(*)                AS samples,
           (array_agg(wf.ts ORDER BY wf.pga_g DESC NULLS LAST))[1] AS peak_ts
    FROM waveform_features_1s_secure wf
    WHERE wf.site_id = CAST(:site_id AS uuid)
      AND wf.ts >= CAST(:from_ts AS timestamptz)
      AND wf.ts <  CAST(:to_ts   AS timestamptz)
    GROUP BY wf.channel
    ORDER BY wf.channel
    """
)

# Sensores del sitio. `calibration_source` decide si el PGA está en unidades físicas o
# es relativo — un dictamen que no lo diga estaría afirmando gravedades que no midió.
_SENSORS = text(
    """
    SELECT sensor_id, kind, model, serial, channels, sample_rate, mount,
           calibration_source, status
    FROM sensors
    WHERE site_id = CAST(:site_id AS uuid) AND status <> 'retired'
    ORDER BY kind, model, sensor_id
    """
)

# CANDIDATOS del catálogo SSN de referencia. Es el ÚNICO contraste externo
# disponible: sirve para decir "la red estimó X, el catálogo dice Y", no para
# corregir nada.
#
# [T-5.11] Esta consulta ya NO elige. Antes traía UNA fila —la más cercana en el
# tiempo— y esa fila SE IMPRIMÍA: el criterio de identidad era «estar dentro de
# ±120 s», y con eso un sismo de otro continente se firmaba como nuestro. Ahora
# devuelve TODO lo que cae en la ventana y quien decide es
# `forensics/correlacion.py`, en Python, porque el criterio necesita la ley de
# atenuación (ATTEN-LAW v1) y meterla en SQL habría creado un tercer espejo de
# una física que ya vive en `geo.py`.
#
# **Las cotas son un SUPERCONJUNTO del criterio, nunca al revés.** Es deliberado
# y no una holgura: si la consulta recortara algo que el criterio habría
# rechazado, ese rechazo perdería su motivo y volvería a ser el hueco que esta
# ficha existe para eliminar. Aquí solo se acota lo que NINGÚN criterio podría
# aceptar (más lejos en el tiempo que el evento más lejano admisible), y de
# rechazar se encarga `correlacion.py`, que además deja dicho por qué.
# `LIMIT` acota el peor caso —una ventana ancha sobre un feed vivo—; el orden
# por cercanía temporal garantiza que lo que se recorta es lo más improbable.
_CATALOG_CANDIDATES = text(
    """
    SELECT catalog_key, origin_time, place, source, source_ref,
           -- numeric ⇒ Decimal en Python, y la ley de atenuación es float:
           -- sin el cast explota al multiplicar, y solo contra la base de verdad.
           magnitude::float8 AS magnitude,
           depth_km::float8  AS depth_km,
           consulted_at, review_status, provider_event_id,
           ST_Y(epicenter::geometry)::float8 AS lat,
           ST_X(epicenter::geometry)::float8 AS lon,
           abs(EXTRACT(EPOCH FROM (origin_time - CAST(:detected_at AS timestamptz))))::float8
               AS dt_s
    FROM reference_earthquakes
    WHERE origin_time >= CAST(:desde AS timestamptz)
      AND origin_time <= CAST(:hasta AS timestamptz)
    ORDER BY dt_s ASC
    LIMIT :limite
    """
)

_SITE_GEO = text(
    """
    SELECT code, name, criticality, building_type, address,
           ST_Y(geom::geometry)::float8 AS lat,
           ST_X(geom::geometry)::float8 AS lon
    FROM sites WHERE site_id = CAST(:site_id AS uuid)
    """
)

# Sitios que votaron en el quórum, con su geometría: son los vértices del croquis.
# LEFT JOIN + RLS ⇒ una estación de otra red devuelve nulos, que es el hecho.
_EVENT_PEERS = text(
    """
    SELECT qv.sensor_id, qv.delta_s::float8 AS delta_s, qv.pga_g::float8 AS pga_g,
           qv.counted, st.code AS site_code,
           ST_Y(st.geom::geometry)::float8 AS lat,
           ST_X(st.geom::geometry)::float8 AS lon
    FROM quorum_votes qv
    LEFT JOIN sensors sn ON sn.sensor_id = qv.sensor_id
    LEFT JOIN sites st ON st.site_id = sn.site_id
    WHERE qv.event_id = :event_id
    ORDER BY qv.delta_s NULLS LAST, qv.sensor_id
    """
)

# Serie por segundo y canal para las trazas. Acotada a la misma ventana del incidente.
_SERIES = text(
    """
    SELECT wf.ts, wf.channel,
           wf.pga_g::float8   AS pga_g,
           wf.pgv_cms::float8 AS pgv_cms,
           wf.rms::float8     AS rms,
           wf.energy::float8  AS energy,
           wf.stalta::float8  AS stalta,
           wf.clipping
    FROM waveform_features_1s_secure wf
    WHERE wf.site_id = CAST(:site_id AS uuid)
      AND wf.ts >= CAST(:from_ts AS timestamptz)
      AND wf.ts <  CAST(:to_ts   AS timestamptz)
    ORDER BY wf.channel, wf.ts
    """
)


async def channel_peaks(
    conn: AsyncConnection, *, site_id: str, from_ts: datetime, to_ts: datetime
) -> Sequence[Row]:
    """Pico por canal en la ventana del incidente."""
    return (
        await conn.execute(_CHANNEL_PEAKS, {"site_id": site_id, "from_ts": from_ts, "to_ts": to_ts})
    ).all()


async def series(
    conn: AsyncConnection, *, site_id: str, from_ts: datetime, to_ts: datetime
) -> Sequence[Row]:
    """Serie de 1 Hz por canal (envolvente de pico, NO forma de onda cruda)."""
    return (
        await conn.execute(_SERIES, {"site_id": site_id, "from_ts": from_ts, "to_ts": to_ts})
    ).all()


async def sensors_of_site(conn: AsyncConnection, site_id: str) -> Sequence[Row]:
    """Sensores activos del sitio, con su procedencia de calibración."""
    return (await conn.execute(_SENSORS, {"site_id": site_id})).all()


async def catalog_candidates(
    conn: AsyncConnection,
    *,
    detected_at: datetime,
    desde: datetime,
    hasta: datetime,
    limite: int = 50,
) -> Sequence[Row]:
    """Sismos del catálogo cuyo origen cae en ``[desde, hasta]``, por cercanía temporal.

    **Candidatos, no aciertos.** Quién de ellos ES el nuestro lo decide el
    criterio de `forensics.correlacion`; esta función no filtra por distancia ni
    por magnitud a propósito, para que el descarte quede registrado con su motivo
    en vez de desaparecer dentro de un `WHERE`.
    """
    return (
        await conn.execute(
            _CATALOG_CANDIDATES,
            {"detected_at": detected_at, "desde": desde, "hasta": hasta, "limite": limite},
        )
    ).all()


async def site_geo(conn: AsyncConnection, site_id: str) -> Row | None:
    """Ficha geográfica del sitio (RLS por tenant)."""
    return (await conn.execute(_SITE_GEO, {"site_id": site_id})).first()


async def event_peers(conn: AsyncConnection, event_id: str) -> Sequence[Row]:
    """Estaciones que votaron en el quórum, con geometría cuando la RLS la permite."""
    return (await conn.execute(_EVENT_PEERS, {"event_id": event_id})).all()
