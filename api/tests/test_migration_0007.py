"""Migración 0007 (T-1.24): ``billing_meters_daily`` + RLS.

El tenant LEE solo lo suyo; escribe solo el worker (BYPASSRLS). El PK
(tenant, día) sostiene el UPSERT idempotente de la pasada.
Usa el ``seeded``/``use`` del conftest (transaccional, rollback al final).
"""

from __future__ import annotations

import psycopg
import pytest

from conftest import TENANT_A, TENANT_B, use

INSERT_METER = (
    "INSERT INTO billing_meters_daily (tenant_id, day, active_sites, messages, "
    "gb_approx, incidents) VALUES (%s, '2026-07-06', 2, 86400, 0.013, 3)"
)


def _seed(conn: psycopg.Connection) -> None:
    conn.execute("RESET ROLE")
    conn.execute(INSERT_METER, (TENANT_A,))
    conn.execute(INSERT_METER, (TENANT_B,))


def test_pk_rejects_duplicate_day(seeded: psycopg.Connection) -> None:
    _seed(seeded)
    with pytest.raises(psycopg.errors.UniqueViolation):
        seeded.execute(INSERT_METER, (TENANT_A,))


def test_rls_tenant_reads_only_its_meters(seeded: psycopg.Connection) -> None:
    _seed(seeded)
    use(seeded, "takab_app", tenant=TENANT_A, app_role="tenant_admin")
    rows = seeded.execute("SELECT tenant_id::text FROM billing_meters_daily").fetchall()
    assert [r[0] for r in rows] == [TENANT_A]


def test_rls_tenant_cannot_write(seeded: psycopg.Connection) -> None:
    use(seeded, "takab_app", tenant=TENANT_A, app_role="tenant_admin")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        seeded.execute(INSERT_METER, (TENANT_A,))


def test_ingest_worker_writes(seeded: psycopg.Connection) -> None:
    use(seeded, "takab_ingest")
    assert seeded.execute(INSERT_METER, (TENANT_A,)).rowcount == 1
