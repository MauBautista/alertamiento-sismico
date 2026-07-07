"""SQL de telemetría (T-1.22 · B3). Dos reglas duras de tenancy, verificadas por
contract-tests estáticos y runtime (``tests/contracts/``):

1. Las features crudas se leen SOLO por la vista ``waveform_features_1s_secure``
   (security_barrier + JOIN a ``sites`` con RLS+FORCE). La hypertable base cruda
   NO se nombra aquí — ``takab_app`` ni siquiera tiene grant sobre ella.
2. Los continuous aggregates ``site_metrics_1m|1h`` NO llevan RLS; por eso todo
   statement que los toque incluye ``JOIN sites`` en el MISMO string — el JOIN a
   ``sites`` (RLS) ES el filtro de tenant. Nunca se exponen sueltos.
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


# Un string COMPLETO por bucket: cada uno menciona su cagg Y su ``JOIN sites`` en
# el mismo literal (el contract-test estático lo exige token a token). El JOIN a
# sites (RLS) es lo que restringe las filas del cagg al tenant del request.
_METRICS_SQL: dict[str, str] = {
    "1m": (
        "SELECT m.bucket, m.max_pga_g, m.max_pgv_cms "
        "FROM site_metrics_1m m JOIN sites s ON s.site_id = m.site_id "
        "WHERE m.site_id = CAST(:site_id AS uuid) "
        "AND m.bucket >= CAST(:from_ts AS timestamptz) "
        "AND m.bucket <  CAST(:to_ts AS timestamptz) "
        "ORDER BY m.bucket ASC"
    ),
    "1h": (
        "SELECT m.bucket, m.max_pga_g, m.max_pgv_cms "
        "FROM site_metrics_1h m JOIN sites s ON s.site_id = m.site_id "
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
# por sitio, en UNA sola query. El cagg del LATERAL lleva su propio ``JOIN sites``
# (redundante con la correlación a ``s`` ya filtrado por RLS, pero es defensa en
# profundidad y cumple la regla dura literalmente: el cagg jamás sin JOIN sites).
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
    FROM site_metrics_1m m JOIN sites s2 ON s2.site_id = m.site_id
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
ORDER BY s.name ASC, s.site_id ASC
"""


def select_map_state() -> tuple[TextClause, dict[str, Any]]:
    """Snapshot del mapa SOC (una query; RLS sobre ``sites`` e ``incidents``)."""
    return text(_MAP_STATE_SQL), {}
