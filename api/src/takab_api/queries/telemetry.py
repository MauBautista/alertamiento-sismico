"""SQL de telemetría (T-1.22 · B3). Dos reglas duras de tenancy, verificadas por
contract-tests estáticos y runtime (``tests/contracts/``):

1. Las features crudas se leen SOLO por la vista ``waveform_features_1s_secure``
   (security_barrier + JOIN a ``sites`` con RLS+FORCE). La hypertable base cruda
   NO se nombra aquí — ``takab_app`` ni siquiera tiene grant sobre ella.
2. Los continuous aggregates ``site_metrics_1{m,h}`` NO llevan RLS; se leen SOLO
   por las vistas ``site_metrics_1{m,h}_secure`` (security_barrier + JOIN a
   ``sites``). El cagg base NO se nombra aquí — ni en esta doc: el contract-test
   escanea TODO literal, docstrings incluidos — y ``takab_app`` tiene el SELECT
   revocado sobre él (migración 0008; auditoría pre-frontend). El JOIN a
   ``sites`` (RLS) dentro de la vista ES el filtro de tenant.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import TextClause, text

# Columnas de la vista segura que alimentan el strip 1 s del SOC.
_FEATURE_COLS = "ts, pga_g, pgv_cms, stalta, clipping"


def select_features(
    *,
    site_id: str,
    from_ts: str,
    to_ts: str,
    channel: str | None,
) -> tuple[TextClause, dict[str, Any]]:
    """Features 1 s de un sitio en ``[from_ts, to_ts)`` (vista segura, orden temporal).

    RLS (vía la vista → ``sites``) decide visibilidad: un ``site_id`` de otro
    tenant devuelve cero filas, no un error.
    """
    where = [
        "site_id = CAST(:site_id AS uuid)",
        "ts >= CAST(:from_ts AS timestamptz)",
        "ts <  CAST(:to_ts AS timestamptz)",
    ]
    params: dict[str, Any] = {"site_id": site_id, "from_ts": from_ts, "to_ts": to_ts}
    if channel is not None:
        where.append("channel = :channel")
        params["channel"] = channel
    sql = (
        f"SELECT {_FEATURE_COLS} FROM waveform_features_1s_secure "
        f"WHERE {' AND '.join(where)} ORDER BY ts ASC"
    )
    return text(sql), params


# Mismo rango, pero SIN colapsar los canales: el strip multicanal (T-1.34) pinta EHZ
# (geófono) y ENZ/ENN/ENE (acelerómetro) por separado. Una sola ida y vuelta: agrupar
# 4 canales en el cliente es más barato que 4 requests con 4 planes de consulta.
_CHANNEL_COLS = "channel, ts, pga_g, pgv_cms, stalta, clipping"


def select_features_by_channel(
    *, site_id: str, from_ts: str, to_ts: str
) -> tuple[TextClause, dict[str, Any]]:
    """Features 1 s de un sitio agrupables por canal (vista segura, orden estable)."""
    sql = (
        f"SELECT {_CHANNEL_COLS} FROM waveform_features_1s_secure "
        "WHERE site_id = CAST(:site_id AS uuid) "
        "  AND ts >= CAST(:from_ts AS timestamptz) "
        "  AND ts <  CAST(:to_ts AS timestamptz) "
        "ORDER BY channel ASC, ts ASC"
    )
    return text(sql), {"site_id": site_id, "from_ts": from_ts, "to_ts": to_ts}


# Se lee por la vista ``*_secure`` (el JOIN a sites con RLS vive DENTRO de la
# vista); el cagg base tiene el SELECT revocado a takab_app (migración 0008).
_METRICS_SQL: dict[str, str] = {
    "1m": (
        "SELECT m.bucket, m.max_pga_g, m.max_pgv_cms "
        "FROM site_metrics_1m_secure m "
        "WHERE m.site_id = CAST(:site_id AS uuid) "
        "AND m.bucket >= CAST(:from_ts AS timestamptz) "
        "AND m.bucket <  CAST(:to_ts AS timestamptz) "
        "ORDER BY m.bucket ASC"
    ),
    "1h": (
        "SELECT m.bucket, m.max_pga_g, m.max_pgv_cms "
        "FROM site_metrics_1h_secure m "
        "WHERE m.site_id = CAST(:site_id AS uuid) "
        "AND m.bucket >= CAST(:from_ts AS timestamptz) "
        "AND m.bucket <  CAST(:to_ts AS timestamptz) "
        "ORDER BY m.bucket ASC"
    ),
}


def select_metrics(
    *,
    bucket: str,
    site_id: str,
    from_ts: str,
    to_ts: str,
) -> tuple[TextClause, dict[str, Any]]:
    """Máximos por bucket de un sitio (cagg 1m o 1h, siempre con JOIN sites)."""
    return (
        text(_METRICS_SQL[bucket]),
        {"site_id": site_id, "from_ts": from_ts, "to_ts": to_ts},
    )


# Estado del mapa: sitios (RLS) + última métrica 1m por sitio + incidente abierto
# por sitio, en UNA sola query. El LATERAL lee la vista ``*_secure`` (el filtro de
# tenant por sites vive dentro de la vista); el cagg base no se nombra.
_MAP_STATE_SQL = """
SELECT s.site_id, s.tenant_id, s.name, s.criticality,
       ST_X(s.geom::geometry) AS lon, ST_Y(s.geom::geometry) AS lat,
       lm.bucket      AS last_bucket,
       lm.max_pga_g   AS max_pga_g,
       lm.max_pgv_cms AS max_pgv_cms,
       li.incident_id AS incident_id,
       li.severity    AS severity,
       li.state       AS state,
       li.opened_at   AS opened_at,
       li.felt_pga_g   AS inc_pga_g,
       li.felt_pgv_cms AS inc_pgv_cms,
       cal.calibrated AS calibrated,
       th.pga_watch_g   AS pga_watch_g,
       th.pga_trip_g    AS pga_trip_g,
       th.pgv_watch_cms AS pgv_watch_cms,
       th.pgv_trip_cms  AS pgv_trip_cms
FROM sites s
LEFT JOIN LATERAL (
    SELECT m.bucket, m.max_pga_g, m.max_pgv_cms
    FROM site_metrics_1m_secure m
    WHERE m.site_id = s.site_id
    ORDER BY m.bucket DESC
    LIMIT 1
) lm ON true
LEFT JOIN LATERAL (
    -- Lo que el edificio LLEGÓ A SENTIR en este incidente = el PICO medido desde
    -- que abrió, no lo que mide ahora. El bucket de 1m de arriba es el "ahora", y
    -- para cuando el operador mira la sacudida ya pasó: usarlo aquí pintaría de
    -- verde un inmueble que se movió 0.567 g (visto en la nube: incidentes por
    -- `local_threshold` con el pico real a NULL y el minuto vivo en ruido de fondo).
    --
    -- `incidents.max_pga_g` es la verdad autoritativa PERO solo la rellena el pase
    -- de dictamen: mientras no corra, viene NULL. Así que se toma el mayor de los
    -- dos hechos medidos. GREATEST ignora los NULL (solo da NULL si TODO es NULL,
    -- y entonces `felt` sale `unknown` — que es lo correcto: no sabemos qué sintió).
    --
    -- El margen hacia atrás NO es un fudge: el bucket de 1 minuto que contiene el
    -- disparo EMPIEZA antes de que el incidente se abra (03:17:00 vs 03:17:13), y
    -- el edge tarda en subirlo. Sin él se pierde justo el minuto que causó el trip.
    SELECT i.incident_id, i.severity, i.state, i.opened_at,
           GREATEST(i.max_pga_g, (
               SELECT max(m.max_pga_g) FROM site_metrics_1m_secure m
                WHERE m.site_id = i.site_id
                  AND m.bucket >= i.opened_at - interval '2 minutes'
           )) AS felt_pga_g,
           GREATEST(i.max_pgv_cms, (
               SELECT max(m.max_pgv_cms) FROM site_metrics_1m_secure m
                WHERE m.site_id = i.site_id
                  AND m.bucket >= i.opened_at - interval '2 minutes'
           )) AS felt_pgv_cms
    FROM incidents i
    WHERE i.site_id = s.site_id AND i.state <> 'closed'
    ORDER BY i.opened_at DESC
    LIMIT 1
) li ON true
LEFT JOIN LATERAL (
    -- Calibrado solo si TODOS los sensores activos declaran su fuente de
    -- respuesta. Sin sensores, bool_and da NULL ⇒ el router lo lee como NO
    -- calibrado (default-deny). Mismo criterio que `select_site_calibrated`.
    SELECT bool_and(sn.calibration_source IS NOT NULL) AS calibrated
    FROM sensors sn
    WHERE sn.site_id = s.site_id AND sn.status = 'active'
) cal ON true
LEFT JOIN LATERAL (
    -- Los MISMOS umbrales que arman los actuadores en el edge: el color del mapa
    -- y la decisión de disparo tienen que contar la misma historia. Scope de
    -- sitio manda sobre el de tenant. Si no hay rule_set (o RLS lo oculta), sale
    -- NULL y el router cae a los default del edge.
    SELECT (rs.config->'edge'->'thresholds'->>'pga_watch_g')::float   AS pga_watch_g,
           (rs.config->'edge'->'thresholds'->>'pga_trip_g')::float    AS pga_trip_g,
           (rs.config->'edge'->'thresholds'->>'pgv_watch_cms')::float AS pgv_watch_cms,
           (rs.config->'edge'->'thresholds'->>'pgv_trip_cms')::float  AS pgv_trip_cms
    FROM rule_sets rs
    WHERE rs.is_active
      AND ((rs.scope_type = 'site'   AND rs.scope_id = s.site_id)
        OR (rs.scope_type = 'tenant' AND rs.scope_id = s.tenant_id))
    ORDER BY (rs.scope_type = 'site') DESC, rs.version DESC
    LIMIT 1
) th ON true
WHERE s.status = 'active'
ORDER BY s.name ASC, s.site_id ASC
"""


def select_map_state() -> tuple[TextClause, dict[str, Any]]:
    """Snapshot del mapa SOC (una query; RLS sobre ``sites`` e ``incidents``)."""
    return text(_MAP_STATE_SQL), {}


# Epicentros de los eventos que tienen incidente ABIERTO. `seismic_events` es de
# alcance RED (no lleva tenant_id — excepción documentada en db/schema.sql), así que
# el aislamiento se consigue ENTRANDO por `incidents`, que sí tiene RLS: solo se ven
# los epicentros de eventos que golpearon a un sitio visible para quien pregunta.
_MAP_EPICENTERS_SQL = """
SELECT DISTINCT
       e.event_id    AS event_id,
       e.source      AS source,
       ST_X(e.epicenter::geometry) AS lon,
       ST_Y(e.epicenter::geometry) AS lat,
       e.magnitude   AS magnitude,
       e.depth_km    AS depth_km,
       e.detected_at AS detected_at,
       -- Corroboración: cuántas estaciones formaron el evento por quórum (T-1.71).
       -- Solo los eventos `local_quorum` llevan `meta.node_count`; los demás (sasmex/
       -- externo) devuelven NULL y la UI no inventa una cuenta.
       (e.meta->>'node_count')::int AS node_count
FROM seismic_events e
JOIN incidents i ON i.event_id = e.event_id
WHERE i.state <> 'closed'
  AND e.epicenter IS NOT NULL
ORDER BY e.detected_at DESC
"""


def select_map_epicenters() -> tuple[TextClause, dict[str, Any]]:
    """Epicentros de los eventos con incidente abierto (aislados vía RLS de ``incidents``)."""
    return text(_MAP_EPICENTERS_SQL), {}


# Un sitio está calibrado solo si TODOS sus sensores activos declaran de dónde salió su
# respuesta instrumental. ``bool_and`` sobre cero filas devuelve NULL (sitio sin
# sensores) — el router lo trata como NO calibrado: default-deny también aquí.
_SITE_CALIBRATED_SQL = """
SELECT bool_and(calibration_source IS NOT NULL) AS calibrated
FROM sensors
WHERE site_id = CAST(:site_id AS uuid) AND status = 'active'
"""


def select_site_calibrated(*, site_id: str) -> tuple[TextClause, dict[str, Any]]:
    """¿Están calibrados TODOS los sensores activos del sitio? (RLS sobre ``sensors``)."""
    return text(_SITE_CALIBRATED_SQL), {"site_id": site_id}
