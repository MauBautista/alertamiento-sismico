"""Sembrador de series de tiempo para las pruebas de rendimiento (T-1.22 · G6).

Genera un dataset de ~90 días para ejercitar las queries de dashboard bajo carga
realista (features 1 s, caggs 1m/1h, incidentes) y medir p95 < 200 ms.

- Densidad **1 s** en la ventana reciente (``--dense-hours``) → strip de features.
- Densidad **1 min** desde ``--dense-hours`` hasta ``--days`` atrás → llena los
  buckets de los caggs 1m/1h sin escribir 1 fila/segundo durante 90 días.
- ``refresh_continuous_aggregate`` por chunks semanales (no en transacción).
- ~``--incidents`` incidentes repartidos por sitio (mezcla abierto/cerrado).

El grueso se inserta con ``INSERT … SELECT generate_series`` (server-side, mucho más
rápido que COPY desde el cliente para una malla regular; supersede el "COPY" del plan
por rendimiento — el objetivo es el dataset, no el mecanismo). Idempotente: catálogo
con UUID deterministas (``ON CONFLICT DO NOTHING``); ``--reset`` limpia las series.

Uso directo (contra una DB dedicada ya migrada):

    createdb + alembic upgrade head, luego
    uv run python scripts/seed_timeseries.py \
        --dsn postgresql://takab:takab_dev@127.0.0.1:5433/takab_perf
"""

from __future__ import annotations

import argparse
import uuid
from dataclasses import dataclass

import psycopg

# Namespace fijo → UUIDv5 deterministas para tenants/sites/sensors (idempotencia).
_NS = uuid.UUID("5eed7ab0-0000-4000-8000-000000000000")
_CHANNELS = ("EHZ", "ENZ", "ENN", "ENE")


def _uid(*parts: object) -> str:
    return str(uuid.uuid5(_NS, ":".join(str(p) for p in parts)))


@dataclass(frozen=True)
class SeedResult:
    """IDs representativos para que la suite de perf apunte sus queries."""

    tenant_ids: list[str]
    site_ids: list[str]
    dense_site_id: str  # sitio con densidad 1 s (para la query de features 10 min)


def _to_dsn(url: str) -> str:
    """Acepta el DSN SQLAlchemy (``postgresql+psycopg://``) o el nativo de libpq."""
    return url.replace("postgresql+psycopg://", "postgresql://")


def _seed_catalog(cur: psycopg.Cursor, *, tenants: int, sites: int) -> SeedResult:
    tenant_ids: list[str] = []
    site_ids: list[str] = []
    for t in range(tenants):
        tid = _uid("tenant", t)
        tenant_ids.append(tid)
        # Alterna gov_shared para que la query del mapa cubra ambos regímenes RLS.
        visibility = "gov_shared" if t % 2 == 1 else "private"
        cur.execute(
            "INSERT INTO tenants (tenant_id, code, name, visibility) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (tenant_id) DO NOTHING",
            (tid, f"PERF{t}", f"Perf tenant {t}", visibility),
        )
        for s in range(sites):
            sid = _uid("site", t, s)
            site_ids.append(sid)
            # Malla alrededor de la Ciudad de México.
            lon = -99.30 + 0.02 * s
            lat = 19.30 + 0.02 * t
            cur.execute(
                "INSERT INTO sites (site_id, tenant_id, code, name, geom) "
                "VALUES (%s, %s, %s, %s, "
                "ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography) "
                "ON CONFLICT (site_id) DO NOTHING",
                (sid, tid, f"S{t}-{s}", f"Sitio {t}-{s}", lon, lat),
            )
            cur.execute(
                "INSERT INTO sensors (sensor_id, tenant_id, site_id, kind, model) "
                "VALUES (%s, %s, %s, 'ground', 'RS4D') "
                "ON CONFLICT (sensor_id) DO NOTHING",
                (_uid("sensor", t, s), tid, sid),
            )
    return SeedResult(tenant_ids, site_ids, site_ids[0])


# Expresiones pseudo-aleatorias baratas y deterministas a partir del epoch del bucket.
_FEATURE_VALUES = (
    "0.01 + ((extract(epoch FROM g)::bigint %% 97) / 300.0) AS pga_g, "
    "0.10 + ((extract(epoch FROM g)::bigint %% 89) / 20.0)  AS pgv_cms, "
    "0.05 + ((extract(epoch FROM g)::bigint %% 53) / 50.0)  AS rms, "
    "0.50 + ((extract(epoch FROM g)::bigint %% 41) / 8.0)   AS stalta, "
    "((extract(epoch FROM g)::bigint %% 71))::real          AS energy, "
    "(extract(epoch FROM g)::bigint %% 997 = 0)             AS clipping"
)


def _feature_sql(start_expr: str, stop_expr: str, step: str) -> str:
    """INSERT…SELECT generate_series; los límites son SQL (ints propios, no input)."""
    return (
        "INSERT INTO waveform_features_1s "
        "(ts, tenant_id, site_id, sensor_id, channel, "
        " pga_g, pgv_cms, rms, stalta, energy, clipping) "
        f"SELECT g, %s, %s, %s, %s, {_FEATURE_VALUES} "
        f"FROM generate_series({start_expr}, {stop_expr}, '{step}'::interval) g "
        "ON CONFLICT DO NOTHING"
    )


def _fill_features(
    cur: psycopg.Cursor,
    result: SeedResult,
    *,
    tenants: int,
    sites: int,
    channels: int,
    dense_hours: int,
    days: int,
) -> None:
    """Rellena ``waveform_features_1s`` por (sitio, canal) con generate_series."""
    # Densa a 1 s (features recientes) e histórica a 1 min (alimenta los caggs).
    dense = _feature_sql(f"now() - interval '{dense_hours} hours'", "now()", "1 second")
    sparse = _feature_sql(
        f"now() - interval '{days} days'",
        f"now() - interval '{dense_hours} hours'",
        "1 minute",
    )
    for t in range(tenants):
        tid = result.tenant_ids[t]
        for s in range(sites):
            sid = _uid("site", t, s)
            sensor = _uid("sensor", t, s)
            for c in range(channels):
                channel = _CHANNELS[c % len(_CHANNELS)]
                cur.execute(dense, (tid, sid, sensor, channel))
                cur.execute(sparse, (tid, sid, sensor, channel))


def _seed_incidents(cur: psycopg.Cursor, result: SeedResult, *, incidents: int, days: int) -> None:
    """Reparte incidentes por sitio; ~1 de cada 4 queda abierto (para el mapa)."""
    n_sites = len(result.site_ids)
    for i in range(incidents):
        site_id = result.site_ids[i % n_sites]
        is_open = i % 4 == 0
        state = "open" if is_open else "closed"
        days_ago = i % days  # int propio → seguro en el f-string
        closed = "NULL" if is_open else "now()"
        cur.execute(
            "INSERT INTO incidents (incident_id, event_uuid, tenant_id, site_id, "
            "opened_at, closed_at, severity, state, trigger) VALUES "
            "(gen_random_uuid(), gen_random_uuid(), "
            "(SELECT tenant_id FROM sites WHERE site_id = %s), %s, "
            f"now() - interval '{days_ago} days', {closed}, 'warning', %s, 'sasmex')",
            (site_id, site_id, state),
        )


def _refresh_caggs(conn: psycopg.Connection, *, days: int) -> None:
    """Materializa 1m/1h por chunks semanales (fuera de transacción → autocommit)."""
    conn.autocommit = True
    with conn.cursor() as cur:
        week = 7
        start = days
        while start > 0:
            end = max(start - week, 0)
            for cagg in ("site_metrics_1m", "site_metrics_1h"):
                cur.execute(
                    f"CALL refresh_continuous_aggregate('{cagg}', "
                    f"now() - interval '{start} days', "
                    f"now() - interval '{end} days')"
                )
            start = end
        # Ventana más reciente (últimas 24 h) para el 1m del strip/mapa.
        cur.execute(
            "CALL refresh_continuous_aggregate('site_metrics_1m', now() - interval '1 day', now())"
        )


def seed(
    dsn: str,
    *,
    tenants: int = 2,
    sites: int = 5,
    channels: int = 2,
    dense_hours: int = 12,
    days: int = 90,
    incidents: int = 500,
    reset: bool = False,
) -> SeedResult:
    """Siembra el dataset completo y devuelve IDs representativos."""
    conn = psycopg.connect(_to_dsn(dsn), autocommit=False)
    try:
        with conn.cursor() as cur:
            if reset:
                cur.execute("TRUNCATE waveform_features_1s")
            result = _seed_catalog(cur, tenants=tenants, sites=sites)
            _fill_features(
                cur,
                result,
                tenants=tenants,
                sites=sites,
                channels=channels,
                dense_hours=dense_hours,
                days=days,
            )
            _seed_incidents(cur, result, incidents=incidents, days=days)
        conn.commit()
        _refresh_caggs(conn, days=days)
        return result
    finally:
        conn.close()


def main() -> None:
    ap = argparse.ArgumentParser(description="Siembra series de tiempo para perf.")
    ap.add_argument("--dsn", required=True)
    ap.add_argument("--tenants", type=int, default=2)
    ap.add_argument("--sites", type=int, default=5, help="sitios por tenant")
    ap.add_argument("--channels", type=int, default=2)
    ap.add_argument("--dense-hours", type=int, default=12)
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--incidents", type=int, default=500)
    ap.add_argument("--reset", action="store_true")
    args = ap.parse_args()
    res = seed(
        args.dsn,
        tenants=args.tenants,
        sites=args.sites,
        channels=args.channels,
        dense_hours=args.dense_hours,
        days=args.days,
        incidents=args.incidents,
        reset=args.reset,
    )
    print(  # noqa: T201 — salida informativa del script
        f"sembrado: {len(res.tenant_ids)} tenants, {len(res.site_ids)} sitios; "
        f"dense_site={res.dense_site_id}"
    )


if __name__ == "__main__":
    main()
