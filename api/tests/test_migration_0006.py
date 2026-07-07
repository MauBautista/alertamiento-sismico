"""Migración 0006 (T-1.23): ``commands`` + ``gateway_config_state`` + RLS.

- ``commands``: nonce UNIQUE (anti-replay en emisión); el tenant lee/escribe lo
  suyo (la API emite bajo la sesión del usuario); gov_operator NO escribe.
- ``gateway_config_state``: el tenant solo LEE (escribe el worker BYPASSRLS).
Usa el ``seeded``/``use`` del conftest (transaccional, rollback al final).
"""

from __future__ import annotations

import psycopg
import pytest

from conftest import GW_A, SITE_A, SITE_B, TENANT_A, TENANT_B, use

INSERT_COMMAND = (
    "INSERT INTO commands (tenant_id, site_id, gateway_id, issued_by, channel, "
    "action, nonce, expires_at) "
    "VALUES (%s,%s,%s,'9e0aa000-0000-0000-0000-000000000001','siren','activate',"
    "%s, now() + interval '30 seconds')"
)

INSERT_STATE = (
    "INSERT INTO gateway_config_state (gateway_id, tenant_id, version, payload, sig) "
    "VALUES (%s,%s,1,'{}'::jsonb,'x')"
)


def _seed_command(conn: psycopg.Connection, nonce: str = "n-0006-a") -> None:
    conn.execute("RESET ROLE")
    conn.execute(INSERT_COMMAND, (TENANT_A, SITE_A, GW_A, nonce))


def test_nonce_unique(seeded: psycopg.Connection) -> None:
    _seed_command(seeded)
    with pytest.raises(psycopg.errors.UniqueViolation):
        seeded.execute(INSERT_COMMAND, (TENANT_A, SITE_A, GW_A, "n-0006-a"))


def test_rls_tenant_reads_only_its_commands(seeded: psycopg.Connection) -> None:
    _seed_command(seeded)
    use(seeded, "takab_app", tenant=TENANT_B, app_role="soc_operator")
    assert seeded.execute("SELECT count(*) FROM commands").fetchone()[0] == 0
    use(seeded, "takab_app", tenant=TENANT_A, app_role="soc_operator")
    assert seeded.execute("SELECT count(*) FROM commands").fetchone()[0] == 1


def test_rls_tenant_writes_its_own_command(seeded: psycopg.Connection) -> None:
    use(seeded, "takab_app", tenant=TENANT_A, app_role="tenant_admin")
    assert seeded.execute(INSERT_COMMAND, (TENANT_A, SITE_A, GW_A, "n-0006-b")).rowcount == 1


def test_rls_cross_tenant_insert_rejected(seeded: psycopg.Connection) -> None:
    use(seeded, "takab_app", tenant=TENANT_B, app_role="tenant_admin")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        seeded.execute(INSERT_COMMAND, (TENANT_A, SITE_A, GW_A, "n-0006-c"))


def test_rls_gov_operator_cannot_command(seeded: psycopg.Connection) -> None:
    use(seeded, "takab_app", tenant=TENANT_A, app_role="gov_operator")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        seeded.execute(INSERT_COMMAND, (TENANT_A, SITE_A, GW_A, "n-0006-d"))


def test_config_state_tenant_read_only(seeded: psycopg.Connection) -> None:
    seeded.execute("RESET ROLE")
    seeded.execute(INSERT_STATE, (GW_A, TENANT_A))
    use(seeded, "takab_app", tenant=TENANT_A, app_role="tenant_admin")
    assert seeded.execute("SELECT count(*) FROM gateway_config_state").fetchone()[0] == 1
    use(seeded, "takab_app", tenant=TENANT_B, app_role="tenant_admin")
    assert seeded.execute("SELECT count(*) FROM gateway_config_state").fetchone()[0] == 0


def test_config_state_tenant_cannot_write(seeded: psycopg.Connection) -> None:
    use(seeded, "takab_app", tenant=TENANT_A, app_role="tenant_admin")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        seeded.execute(INSERT_STATE, (GW_A, TENANT_A))


def test_site_b_belongs_to_other_tenant_guard(seeded: psycopg.Connection) -> None:
    """Sanity del fixture: SITE_B es de TENANT_B (la RLS de arriba depende de eso)."""
    seeded.execute("RESET ROLE")
    row = seeded.execute(
        "SELECT tenant_id::text FROM sites WHERE site_id = %s", (SITE_B,)
    ).fetchone()
    assert row[0] == TENANT_B
