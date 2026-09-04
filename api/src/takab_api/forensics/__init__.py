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

from takab_api import procedencia as pr
from takab_api.felt import felt_band
from takab_api.forensics import correlacion as corr
from takab_api.geo import bearing16, haversine_km
from takab_api.queries import compliance as qc
from takab_api.queries import forensics as q
from takab_api.schemas.compliance import doc_out
from takab_api.schemas.forensics import (
    CatalogCorrelation,
    CatalogCriterion,
    CatalogDelta,
    CatalogDiscard,
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

# [T-5.11] Aquí vivía `CATALOG_WINDOW_S = 120.0`, y era TODO el criterio de
# correlación con el catálogo: el sismo más cercano en el tiempo dentro de esa
# ventana se imprimía como el nuestro en un dictamen firmado. La ventana fija era
# además físicamente incorrecta —el M8.2 de Chiapas llegó a 205 s de su origen—.
# El criterio completo (ventana consciente de la distancia + radio al sitio +
# coherencia magnitud/distancia) vive en `forensics/correlacion.py` con la razón
# escrita de cada número, y sus umbrales en `Settings.correlation_*`.


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

    catalog, delta, correlation = await _catalog(conn, inc, site, s)

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
        catalog_correlation=correlation,
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
    conn: AsyncConnection, inc: dict, site: SiteGeo | None, s: Settings
) -> tuple[CatalogMatch | None, CatalogDelta | None, CatalogCorrelation]:
    """Correlación con el catálogo de referencia — con criterio de IDENTIDAD (T-5.11).

    Devuelve el acierto (si lo hay), su contraste contra el epicentro propio (si
    lo hay) y **siempre** la correlación: qué criterio se aplicó y qué descartó.
    Ese tercer valor es el que permite distinguir «el catálogo no tiene nada» de
    «lo que tiene no es esto», que hasta esta ficha eran el mismo hueco.
    """
    detected = inc["event_detected_at"] or inc["opened_at"]
    criterio = corr.Criterio(
        v_s_km_s=s.correlation_v_s_km_s,
        margen_s=s.correlation_margin_s,
        radio_km=s.correlation_max_km,
        pga_minima_g=s.correlation_min_pga_g,
    )
    # La consulta se acota con un SUPERCONJUNTO de lo que el criterio admite: a
    # ambos lados el retraso máximo, aunque hacia delante el criterio solo tolere
    # el margen de reloj. Recortar en el `WHERE` lo que el criterio habría
    # rechazado le quitaría el motivo al rechazo, y un rechazo sin motivo vuelve
    # a ser el hueco que esta ficha elimina: un evento del catálogo originado
    # DESPUÉS de nuestra detección tiene que poder decirse, no desaparecer.
    tope = timedelta(seconds=criterio.retraso_maximo_s)
    rows = await q.catalog_candidates(
        conn, detected_at=detected, desde=detected - tope, hasta=detected + tope
    )
    filas = [dict(r._mapping) for r in rows]
    resultado = corr.correlaciona(
        [
            corr.Candidato(
                catalog_key=f["catalog_key"],
                origin_time=f["origin_time"],
                magnitude=f["magnitude"],
                lat=f["lat"],
                lon=f["lon"],
                depth_km=f["depth_km"],
            )
            for f in filas
        ],
        detectado_en=detected,
        sitio_lat=site.lat if site else None,
        sitio_lon=site.lon if site else None,
        criterio=criterio,
    )

    correlation = CatalogCorrelation(
        # Consultamos el catálogo y no encontramos nada compatible: eso es un
        # HECHO sobre el evento (probablemente local y pequeño), no una ausencia
        # de datos. `sin_dato_externo` sería mentir sobre no haber preguntado.
        estado=pr.SIN_CORRELACION,
        criterio=CatalogCriterion(
            v_s_km_s=criterio.v_s_km_s,
            margen_s=criterio.margen_s,
            radio_km=criterio.radio_km,
            pga_minima_g=criterio.pga_minima_g,
        ),
        descartes=[
            CatalogDiscard(
                catalog_key=v.catalog_key,
                motivo=v.motivo or "",
                detalle=v.detalle,
                km_al_sitio=v.km_al_sitio,
                retraso_s=v.retraso_s,
                retraso_admisible_s=v.retraso_admisible_s,
                pga_esperada_g=v.pga_esperada_g,
            )
            for v in resultado.descartes
        ],
    )
    if resultado.acierto is None:
        return None, None, correlation

    fila = next(f for f in filas if f["catalog_key"] == resultado.acierto.catalog_key)
    match = CatalogMatch(
        **{k: v for k, v in fila.items() if k in CatalogMatch.model_fields},
        km_al_sitio=resultado.acierto.km_al_sitio,
        rumbo_al_sitio=resultado.acierto.rumbo_al_sitio,
        pga_esperada_g=resultado.acierto.pga_esperada_g,
    )
    # [T-5.10] La cifra externa solo se pinta con procedencia. Casar no la
    # concede: una fila sin hora de consulta ni estado de revisión es un dato que
    # existe y no es citable, y degrada a `sin_dato_externo`.
    correlation.estado = pr.de_fila(fila).estado

    km = bearing = None
    tiene_epicentro_propio = inc["epi_lat"] is not None and inc["epi_lon"] is not None
    if tiene_epicentro_propio and match.lat is not None and match.lon is not None:
        km = haversine_km(inc["epi_lat"], inc["epi_lon"], match.lat, match.lon)
        bearing = bearing16(inc["epi_lat"], inc["epi_lon"], match.lat, match.lon)
    # Sin epicentro propio NO hay contraste, y decir que lo hay prometería una
    # verificación que no ocurrió. La identidad se estableció por ventana, radio
    # y coherencia — que es una afirmación distinta y más modesta.
    correlation.verificacion = corr.CONTRASTADO if km is not None else corr.NO_VERIFICABLE

    return (
        match,
        CatalogDelta(
            km=km,
            bearing=bearing,
            dt_s=match.dt_s,
            magnitude=match.magnitude if inc["event_magnitude"] is None else None,
        ),
        correlation,
    )
