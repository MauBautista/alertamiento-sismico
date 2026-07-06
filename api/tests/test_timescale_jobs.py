"""TimescaleDB real: jobs conviven con RLS en las hypertables (schema §8).

Verifica el diseño corregido [ANALISIS-00 v1.2]:
  * 3 hypertables + 2 continuous aggregates.
  * device_health / rule_evaluations: RLS ENABLE **sin FORCE** (los jobs corren como
    el owner; con FORCE verían 0 filas). Retención convive con RLS.
  * waveform_features_1s: SIN RLS (tiene caggs) — aislada por la vista.
  * La compresión se trasladó a los caggs.
  * Un job de retención sobre una hypertable con RLS y un refresh de cagg EJECUTAN
    sin error (coexistencia real, no solo declarada).
"""

from __future__ import annotations

import psycopg

from conftest import _dsn


def _scalar(conn: psycopg.Connection, sql: str, args: tuple = ()) -> object:
    return conn.execute(sql, args).fetchone()[0]


def test_hypertables_and_caggs_present(conn: psycopg.Connection) -> None:
    hts = {
        r[0]
        for r in conn.execute(
            "SELECT hypertable_name FROM timescaledb_information.hypertables"
        ).fetchall()
    }
    assert {"waveform_features_1s", "device_health", "rule_evaluations"} <= hts
    caggs = {
        r[0]
        for r in conn.execute(
            "SELECT view_name FROM timescaledb_information.continuous_aggregates"
        ).fetchall()
    }
    assert caggs == {"site_metrics_1m", "site_metrics_1h"}


def test_rls_hypertables_enabled_without_force(conn: psycopg.Connection) -> None:
    for table in ("device_health", "rule_evaluations"):
        enabled = _scalar(conn, "SELECT relrowsecurity FROM pg_class WHERE relname = %s", (table,))
        forced = _scalar(
            conn, "SELECT relforcerowsecurity FROM pg_class WHERE relname = %s", (table,)
        )
        assert enabled is True, f"{table} debe tener RLS"
        assert forced is False, f"{table} NO debe tener FORCE (los jobs son el owner)"


def test_waveform_has_no_rls(conn: psycopg.Connection) -> None:
    # No puede llevar RLS por tener caggs; su aislamiento va por la vista.
    assert (
        _scalar(
            conn,
            "SELECT relrowsecurity FROM pg_class WHERE relname = 'waveform_features_1s'",
        )
        is False
    )
    assert (
        _scalar(
            conn,
            "SELECT count(*) FROM pg_views WHERE viewname = 'waveform_features_1s_secure'",
        )
        == 1
    )


def test_business_tables_have_force(conn: psycopg.Connection) -> None:
    for table in ("incidents", "tenants", "sites", "dictamens"):
        assert (
            _scalar(
                conn,
                "SELECT relforcerowsecurity FROM pg_class WHERE relname = %s",
                (table,),
            )
            is True
        ), f"{table} (tabla de negocio) debe tener FORCE RLS"


def test_retention_jobs_on_rls_hypertables(conn: psycopg.Connection) -> None:
    for table in ("device_health", "rule_evaluations", "waveform_features_1s"):
        n = _scalar(
            conn,
            "SELECT count(*) FROM timescaledb_information.jobs "
            "WHERE proc_name = 'policy_retention' AND hypertable_name = %s",
            (table,),
        )
        assert n == 1, f"{table} debe tener job de retención"


def test_compression_moved_to_caggs(conn: psycopg.Connection) -> None:
    # El crudo NO tiene job de compresión; los caggs SÍ.
    raw = _scalar(
        conn,
        "SELECT count(*) FROM timescaledb_information.jobs "
        "WHERE proc_name = 'policy_compression' AND hypertable_name = 'waveform_features_1s'",
    )
    assert raw == 0
    caggs = _scalar(
        conn,
        "SELECT count(*) FROM timescaledb_information.jobs WHERE proc_name = 'policy_compression'",
    )
    assert caggs == 2, "compresión en site_metrics_1m y site_metrics_1h"


def test_job_runs_on_rls_hypertable() -> None:
    # Coexistencia REAL: ejecutar un job de retención sobre una hypertable con RLS y
    # un refresh de cagg no deben fallar por RLS. (run_job/refresh exigen autocommit.)
    c = psycopg.connect(_dsn(), autocommit=True)
    try:
        jid = c.execute(
            "SELECT job_id FROM timescaledb_information.jobs "
            "WHERE proc_name = 'policy_retention' AND hypertable_name = 'device_health'"
        ).fetchone()[0]
        c.execute("CALL run_job(%s)", (jid,))
        c.execute("CALL refresh_continuous_aggregate('site_metrics_1m', NULL, NULL)")
    finally:
        c.close()
