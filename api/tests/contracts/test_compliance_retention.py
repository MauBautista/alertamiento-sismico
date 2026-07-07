"""Contract-test (T-1.24 / blueprint §9): compliance JAMÁS se poda por retención.

Las tablas de evidencia/auditoría son relacionales planas (no hypertables) y
NINGÚN job de Timescale (retención NI compresión) puede apuntarles; además
todas conservan su trigger append-only. Si alguien las convierte en hypertable
o les cuelga una policy, este test truena ANTES de que la poda borre evidencia.
"""

from __future__ import annotations

import psycopg
import pytest

# Blueprint §9: auditoría, evidencia de incidentes y dictámenes, nunca podados.
COMPLIANCE_TABLES = (
    "audit_log",
    "incident_actions",
    "dictamens",
    "evidence_objects",
    "life_checkins",
)


@pytest.mark.parametrize("table", COMPLIANCE_TABLES)
def test_compliance_table_is_not_a_hypertable(conn: psycopg.Connection, table: str) -> None:
    row = conn.execute(
        "SELECT count(*) FROM timescaledb_information.hypertables WHERE hypertable_name = %s",
        (table,),
    ).fetchone()
    assert row[0] == 0, f"{table} se volvió hypertable: la retención podría podarla"


@pytest.mark.parametrize("table", COMPLIANCE_TABLES)
def test_no_timescale_job_targets_compliance_table(conn: psycopg.Connection, table: str) -> None:
    row = conn.execute(
        "SELECT count(*) FROM timescaledb_information.jobs "
        "WHERE hypertable_name = %s "
        "AND proc_name IN ('policy_retention', 'policy_compression')",
        (table,),
    ).fetchone()
    assert row[0] == 0, f"{table} tiene un job de retención/compresión (prohibido §9)"


@pytest.mark.parametrize("table", COMPLIANCE_TABLES)
def test_compliance_table_keeps_append_only_trigger(conn: psycopg.Connection, table: str) -> None:
    row = conn.execute(
        "SELECT count(*) FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
        "WHERE c.relname = %s AND NOT t.tgisinternal "
        "AND t.tgfoid = 'forbid_update_delete'::regproc",
        (table,),
    ).fetchone()
    assert row[0] >= 1, f"{table} perdió su trigger append-only"
