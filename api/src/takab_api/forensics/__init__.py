"""Ensamblado forense de un incidente (T-2.40).

Una sola función construye los hechos medidos; la pantalla y el PDF consumen el
MISMO objeto. Si cada uno los recalculara, tarde o temprano el dictamen diría un
número distinto del que el operador vio, y ese es el fallo que ningún revisor perdona.

Este módulo **no emite juicio**. No decide si el edificio se habita —eso es
``dictamen/rules.py``, determinista y versionado— ni interpreta. Solo mide, y cuando
no puede medir, dice por qué.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.felt import felt_band
from takab_api.geo import bearing16, haversine_km
from takab_api.queries import compliance as qc
from takab_api.queries import forensics as q
from takab_api.schemas.compliance import doc_out
from takab_api.schemas.forensics import (
    CatalogDelta,
    CatalogMatch,
    ChannelPeak,
    ForensicsOut,
    QuorumPeer,
    SensorInfo,
    SiteGeo,
)
from takab_api.settings import Settings

_INCIDENT = text(
    """
    SELECT i.incident_id, i.site_id, i.event_id, i.opened_at, i.closed_at,
           i.severity, i.state, i.trigger,
           i.max_pga_g::float8 AS max_pga_g, i.max_pgv_cms::float8 AS max_pgv_cms,
           e.source AS event_source, e.detected_at AS event_detected_at,
           e.magnitude::float8 AS event_magnitude,
           ST_Y(e.epicenter::geometry)::float8 AS epi_lat,
           ST_X(e.epicenter::geometry)::float8 AS epi_lon
    FROM incidents i
    LEFT JOIN seismic_events e ON e.event_id = i.event_id
    WHERE i.incident_id = CAST(:incident_id AS uuid)
    """
)

_COUNTED_VOTES = text("SELECT count(*) FROM quorum_votes WHERE event_id = :event_id AND counted")

# Ventana de coincidencia con el catálogo. 120 s es holgado para el desfase entre el
# origen del sismo y la detección local a cientos de km, y estrecho para no casar dos
# sismos distintos del mismo día.
CATALOG_WINDOW_S = 120.0


async def build_forensics(
    conn: AsyncConnection, incident_id: str, settings: Settings | None = None
) -> ForensicsOut | None:
    """Hechos medidos del incidente, o ``None`` si la RLS no lo deja verlo."""
    s = settings or Settings()
    row = (await conn.execute(_INCIDENT, {"incident_id": incident_id})).first()
    if row is None:
        return None
    inc = dict(row._mapping)
    site_id = str(inc["site_id"])

    # Misma ventana asimétrica que el motor de dictamen: la sacudida llega DESPUÉS de
    # la alerta SASMEX, así que centrarla en la apertura del incidente perdería el pico.
    opened = inc["opened_at"]
    window_from = opened - timedelta(seconds=s.dictamen_pga_window_pre_s)
    window_to = opened + timedelta(seconds=s.dictamen_pga_window_post_s)

    peaks = [
        ChannelPeak(**dict(r._mapping))
        for r in await q.channel_peaks(conn, site_id=site_id, from_ts=window_from, to_ts=window_to)
    ]
    peak_pga = max((c.peak_pga_g for c in peaks if c.peak_pga_g is not None), default=None)
    peak_pgv = max((c.peak_pgv_cms for c in peaks if c.peak_pgv_cms is not None), default=None)
    peak_ts = next(
        (c.peak_ts for c in sorted(peaks, key=lambda c: c.peak_pga_g or -1, reverse=True)),
        None,
    )

    lead_time_s, lead_reason = _lead_time(inc["trigger"], opened, peak_ts)

    site_row = await q.site_geo(conn, site_id)
    site = SiteGeo(**dict(site_row._mapping)) if site_row is not None else None

    sensors = [SensorInfo(**dict(r._mapping)) for r in await q.sensors_of_site(conn, site_id)]
    # Default-deny: sin sensores NO se afirma que el sitio esté calibrado.
    calibrated = bool(sensors) and all(sn.calibration_source is not None for sn in sensors)

    peers: list[QuorumPeer] = []
    station_count = 0
    if inc["event_id"]:
        peers = [QuorumPeer(**dict(r._mapping)) for r in await q.event_peers(conn, inc["event_id"])]
        station_count = (await conn.scalar(_COUNTED_VOTES, {"event_id": inc["event_id"]})) or 0

    catalog, delta = await _catalog(conn, inc)

    return ForensicsOut(
        incident_id=inc["incident_id"],
        site=site,
        window_from=window_from,
        window_to=window_to,
        channels=peaks,
        peak_pga_g=peak_pga,
        peak_pgv_cms=peak_pgv,
        peak_ts=peak_ts,
        # La banda se calcula sobre el pico de la VENTANA; si no hubo features cae al
        # máximo persistido en el incidente, y si tampoco, `unknown`.
        felt_band=felt_band(
            peak_pga if peak_pga is not None else inc["max_pga_g"],
            peak_pgv if peak_pgv is not None else inc["max_pgv_cms"],
        ),
        lead_time_s=lead_time_s,
        lead_time_reason=lead_reason,
        station_count=station_count,
        peers=peers,
        catalog=catalog,
        catalog_delta=delta,
        sensors=sensors,
        calibrated=calibrated,
        # [T-2.82] Lo declarado por el cliente viaja PEGADO a lo medido por TAKAB, pero
        # nunca mezclado: va en su propio bloque, con su procedencia y su deslinde.
        compliance=doc_out(await qc.document_for_incident(conn, incident_id)),
    )


def _lead_time(trigger: str, opened, peak_ts) -> tuple[float | None, str | None]:
    """Tiempo de aviso GANADO: de la alerta al pico de la sacudida.

    Solo tiene sentido con SASMEX. En un incidente disparado por umbral local la
    "alerta" ES la sacudida: el número sería ~0 por construcción y presentarlo como
    tiempo ganado sería una cifra inventada con apariencia de logro.
    """
    if trigger != "sasmex":
        return None, "not_sasmex"
    if peak_ts is None:
        return None, "no_peak"
    delta = (peak_ts - opened).total_seconds()
    if delta < 0:
        # El pico precede a la alerta: no hubo aviso, hubo confirmación posterior.
        return None, "peak_before_alert"
    return delta, None


async def _catalog(
    conn: AsyncConnection, inc: dict
) -> tuple[CatalogMatch | None, CatalogDelta | None]:
    """Contraste con el catálogo de referencia. Ambos ``None`` si no hay coincidencia."""
    detected = inc["event_detected_at"] or inc["opened_at"]
    row = await q.catalog_match(conn, detected_at=detected, window_s=CATALOG_WINDOW_S)
    if row is None:
        return None, None
    match = CatalogMatch(**dict(row._mapping))

    km = bearing = None
    if (
        inc["epi_lat"] is not None
        and inc["epi_lon"] is not None
        and match.lat is not None
        and match.lon is not None
    ):
        km = haversine_km(inc["epi_lat"], inc["epi_lon"], match.lat, match.lon)
        bearing = bearing16(inc["epi_lat"], inc["epi_lon"], match.lat, match.lon)

    return match, CatalogDelta(
        km=km,
        bearing=bearing,
        dt_s=match.dt_s,
        magnitude=match.magnitude if inc["event_magnitude"] is None else None,
    )
