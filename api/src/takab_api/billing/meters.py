"""Pasada de medidores diarios por tenant (T-1.24 · B10).

Computa, para UN día UTC ``[day 00:00, day+1)``, los medidores del criterio:

- **active_sites**: sitios con telemetría ese día (features del sitio ∪
  device_health del gateway → sitio).
- **messages**: filas ingeridas ese día — features + device_health +
  incident_actions (proxy 1-fila≈1-mensaje del pipeline; los heartbeats y
  acks/eventos van por incident_actions/device_health).
- **gb_approx**: ``messages × billing_row_bytes_estimate / 1e9`` —
  APROXIMACIÓN row-count×promedio (plan maestro); calibrar el estimado con
  ``pg_column_size`` real cuando haya volumen de producción.
- **incidents**: incidentes ABIERTOS ese día (``opened_at``).

UPSERT idempotente por PK (tenant, día): re-computar (cron re-ejecutado,
backfill tardío que engordó el día) actualiza en lugar de duplicar. Solo los
tenants con actividad ese día generan renglón. Corre como ``takab_ingest``
(BYPASSRLS, agregación cross-tenant); scheduling dev = cron/`make billing`;
AWS = EventBridge→ECS (TODO prod).
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, time, timedelta

import psycopg

from takab_api.settings import Settings

logger = logging.getLogger("takab_api.billing")

# Sitios con telemetría en la ventana (features por sitio; health vía gateway).
_ACTIVE_SITES_SQL = """
SELECT tenant_id, count(DISTINCT site_id) AS active_sites
FROM (
  SELECT wf.tenant_id, wf.site_id
  FROM waveform_features_1s wf
  WHERE wf.ts >= %(ts_from)s AND wf.ts < %(ts_to)s
  UNION
  SELECT dh.tenant_id, g.site_id
  FROM device_health dh
  JOIN gateways g USING (gateway_id)
  WHERE dh.ts >= %(ts_from)s AND dh.ts < %(ts_to)s
) activity
GROUP BY tenant_id
"""

_FEATURES_SQL = """
SELECT tenant_id, count(*) AS n FROM waveform_features_1s
WHERE ts >= %(ts_from)s AND ts < %(ts_to)s GROUP BY tenant_id
"""

_HEALTH_SQL = """
SELECT tenant_id, count(*) AS n FROM device_health
WHERE ts >= %(ts_from)s AND ts < %(ts_to)s GROUP BY tenant_id
"""

_ACTIONS_SQL = """
SELECT tenant_id, count(*) AS n FROM incident_actions
WHERE ts >= %(ts_from)s AND ts < %(ts_to)s GROUP BY tenant_id
"""

_INCIDENTS_SQL = """
SELECT tenant_id, count(*) AS n FROM incidents
WHERE opened_at >= %(ts_from)s AND opened_at < %(ts_to)s GROUP BY tenant_id
"""

_UPSERT_SQL = """
INSERT INTO billing_meters_daily
  (tenant_id, day, active_sites, messages, gb_approx, incidents, computed_at)
VALUES (%(tenant)s, %(day)s, %(active_sites)s, %(messages)s, %(gb)s, %(incidents)s, %(now)s)
ON CONFLICT (tenant_id, day) DO UPDATE
SET active_sites = EXCLUDED.active_sites,
    messages     = EXCLUDED.messages,
    gb_approx    = EXCLUDED.gb_approx,
    incidents    = EXCLUDED.incidents,
    computed_at  = EXCLUDED.computed_at
"""


def run_billing_pass(
    conn: psycopg.Connection,
    settings: Settings,
    day: date,
    *,
    now: datetime | None = None,
) -> dict[str, dict]:
    """Computa y UPSERTea los medidores del día; devuelve {tenant: medidores}."""
    now = now or datetime.now(tz=UTC)
    ts_from = datetime.combine(day, time.min, tzinfo=UTC)
    window = {"ts_from": ts_from, "ts_to": ts_from + timedelta(days=1)}

    meters: dict[str, dict] = {}

    def _bucket(tenant: str) -> dict:
        return meters.setdefault(tenant, {"active_sites": 0, "messages": 0, "incidents": 0})

    for row in conn.execute(_ACTIVE_SITES_SQL, window).fetchall():
        _bucket(str(row["tenant_id"]))["active_sites"] = row["active_sites"]
    for sql in (_FEATURES_SQL, _HEALTH_SQL, _ACTIONS_SQL):
        for row in conn.execute(sql, window).fetchall():
            _bucket(str(row["tenant_id"]))["messages"] += row["n"]
    for row in conn.execute(_INCIDENTS_SQL, window).fetchall():
        _bucket(str(row["tenant_id"]))["incidents"] = row["n"]

    for tenant, m in meters.items():
        m["gb_approx"] = m["messages"] * settings.billing_row_bytes_estimate / 1e9
        conn.execute(
            _UPSERT_SQL,
            {
                "tenant": tenant,
                "day": day,
                "active_sites": m["active_sites"],
                "messages": m["messages"],
                "gb": m["gb_approx"],
                "incidents": m["incidents"],
                "now": now,
            },
        )
    if meters:
        conn.commit()
        logger.info("billing %s: %d tenants medidos", day.isoformat(), len(meters))
    else:
        conn.rollback()
        logger.info("billing %s: sin actividad", day.isoformat())
    return meters
