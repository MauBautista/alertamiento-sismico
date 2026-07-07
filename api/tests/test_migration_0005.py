"""Migración 0005 (T-1.21): tabla ``notification_jobs`` + RLS espejo de incidents.

El tenant LEE lo suyo (más ramas internal/gov); NO escribe (los jobs los crea el
worker BYPASSRLS). UNIQUE (incident_id, channel, mode) = idempotencia del enqueue.
Usa el ``seeded``/``use`` del conftest (transaccional: rollback al final).
"""

from __future__ import annotations

import psycopg
import pytest

from conftest import GOV_AGENCY, INC_A, INC_G, TENANT_A, TENANT_B, TENANT_G, use

INSERT_JOB = (
    "INSERT INTO notification_jobs "
    "(tenant_id, incident_id, channel, mode, position, due_at) "
    "VALUES (%s,%s,%s,%s,0,'2026-07-07 12:00:00+00')"
)


def _seed_jobs(conn: psycopg.Connection) -> None:
    """Un job del tenant A (private) y uno del G (gov_shared), como superusuario."""
    conn.execute("RESET ROLE")
    conn.execute(INSERT_JOB, (TENANT_A, INC_A, "webhook", "cascade"))
    conn.execute(INSERT_JOB, (TENANT_G, INC_G, "email", "parallel"))


def test_unique_incident_channel_mode(seeded: psycopg.Connection) -> None:
    _seed_jobs(seeded)
    with pytest.raises(psycopg.errors.UniqueViolation):
        seeded.execute(INSERT_JOB, (TENANT_A, INC_A, "webhook", "cascade"))


def test_rls_tenant_reads_only_its_jobs(seeded: psycopg.Connection) -> None:
    _seed_jobs(seeded)
    use(seeded, "takab_app", tenant=TENANT_A, app_role="soc_operator")
    rows = seeded.execute("SELECT tenant_id::text FROM notification_jobs").fetchall()
    assert [r[0] for r in rows] == [TENANT_A]


def test_rls_other_tenant_sees_nothing(seeded: psycopg.Connection) -> None:
    _seed_jobs(seeded)
    use(seeded, "takab_app", tenant=TENANT_B, app_role="soc_operator")
    assert seeded.execute("SELECT count(*) FROM notification_jobs").fetchone()[0] == 0


def test_rls_gov_sees_gov_shared_only(seeded: psycopg.Connection) -> None:
    _seed_jobs(seeded)
    use(seeded, "takab_app", tenant=GOV_AGENCY, app_role="gov_operator")
    rows = seeded.execute("SELECT tenant_id::text FROM notification_jobs").fetchall()
    assert [r[0] for r in rows] == [TENANT_G]


def test_rls_tenant_cannot_insert(seeded: psycopg.Connection) -> None:
    """Sin policy de escritura de tenant: los jobs los crea SOLO el worker."""
    _seed_jobs(seeded)
    use(seeded, "takab_app", tenant=TENANT_A, app_role="soc_operator")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        seeded.execute(INSERT_JOB, (TENANT_A, INC_A, "sms", "cascade"))


def test_ingest_role_writes_bypassing_rls(seeded: psycopg.Connection) -> None:
    use(seeded, "takab_ingest")
    assert seeded.execute(INSERT_JOB, (TENANT_A, INC_A, "sms", "parallel")).rowcount == 1
    row = seeded.execute(
        "SELECT status, target FROM notification_jobs WHERE incident_id = %s", (INC_A,)
    ).fetchone()
    assert row[0] == "pending"
    assert row[1] == {}
