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
       li.opened_at   AS opened_at
FROM sites s
LEFT JOIN LATERAL (
    SELECT m.bucket, m.max_pga_g, m.max_pgv_cms
    FROM site_metrics_1m_secure m
    WHERE m.site_id = s.site_id
    ORDER BY m.bucket DESC
    LIMIT 1
) lm ON true
LEFT JOIN LATERAL (
    SELECT i.incident_id, i.severity, i.state, i.opened_at
    FROM incidents i
    WHERE i.site_id = s.site_id AND i.state <> 'closed'
    ORDER BY i.opened_at DESC
    LIMIT 1
) li ON true
WHERE s.status = 'active'
ORDER BY s.name ASC, s.site_id ASC
"""


def select_map_state() -> tuple[TextClause, dict[str, Any]]:
    """Snapshot del mapa SOC (una query; RLS sobre ``sites`` e ``incidents``)."""
    return text(_MAP_STATE_SQL), {}


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
