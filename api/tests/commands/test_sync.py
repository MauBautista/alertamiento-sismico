"""Config sync firmada contra Postgres real (T-1.23 · B9).

Patrón _Scenario (tenant fresco + cleanup); publisher fake. La versión es
MONÓTONA por gateway y la pasada es idempotente (mismo payload ⇒ no republica).
La firma publicada se verifica con la firma propia — la paridad byte-idéntica
con el edge la garantizan los vectores compartidos (test_signing_vectors).
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Iterator

import psycopg
import pytest
from psycopg.rows import dict_row

from takab_api.commands.publisher import PublishError
from takab_api.commands.signing import canonical_payload, sign_config
from takab_api.commands.sync import run_config_sync_pass
from takab_api.settings import Settings

DEFAULT_URL = "postgresql+psycopg://takab:takab_dev@127.0.0.1:5433/takab"
KEY = "clave-sync-test"

EDGE_DOC = {"command_enabled": True, "command_ttl_s": 30.0}


def _dsn() -> str:
    url = os.environ.get("DATABASE_URL", DEFAULT_URL)
    return url.replace("postgresql+psycopg://", "postgresql://")


class _FakePublisher:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.published: list[tuple[str, dict]] = []

    def publish(self, topic: str, payload: bytes) -> None:
        if self.fail:
            raise PublishError("iot caído (simulado)")
        self.published.append((topic, json.loads(payload)))


class _Scenario:
    def __init__(self, conn: psycopg.Connection, tenant: str) -> None:
        self.conn = conn
        self.tenant = tenant
        self.site = str(uuid.uuid4())
        self.gateway = str(uuid.uuid4())
        self.thing = f"gw-sync-{self.gateway[:8]}"

    def seed_gateway(self, *, iot_thing: str | None = None) -> None:
        self.conn.execute(
            "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
            "(%s,%s,%s,'S', ST_SetSRID(ST_MakePoint(-100.9,11.9),4326)::geography)",
            (self.site, self.tenant, f"CS-{self.site[:8]}"),
        )
        self.conn.execute(
            "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, iot_thing) "
            "VALUES (%s,%s,%s,%s,%s)",
            (
                self.gateway,
                self.tenant,
                self.site,
                f"SER-{self.gateway[:8]}",
                iot_thing if iot_thing is not None else self.thing,
            ),
        )
        self.conn.commit()

    def activate_rule_set(self, config: dict, *, version: int = 1) -> None:
        self.conn.execute(
            "INSERT INTO rule_sets (tenant_id, scope_type, scope_id, version, "
            "is_active, config) VALUES (%s,'tenant',%s,%s,true,%s::jsonb)",
            (self.tenant, self.tenant, version, json.dumps(config)),
        )
        self.conn.commit()

    def state(self) -> dict | None:
        return self.conn.execute(
            "SELECT version, payload, sig FROM gateway_config_state WHERE gateway_id = %s",
            (self.gateway,),
        ).fetchone()

    def mine(self, publisher: _FakePublisher) -> list[tuple[str, dict]]:
        return [(t, p) for t, p in publisher.published if t == f"takab/cfg/{self.thing}"]


@pytest.fixture
def scenario() -> Iterator[_Scenario]:
    conn = psycopg.connect(_dsn(), autocommit=False, row_factory=dict_row)
    tenant = str(uuid.uuid4())
    try:
        conn.execute("SET ROLE takab_ingest")
        conn.execute(
            "INSERT INTO tenants (tenant_id, code, name) VALUES (%s,%s,'Sync Test')",
            (tenant, tenant[:8]),
        )
        conn.commit()
        yield _Scenario(conn, tenant)
    finally:
        _cleanup(conn, tenant)
        conn.close()


def _cleanup(conn: psycopg.Connection, tenant: str) -> None:
    conn.rollback()
    conn.execute("RESET ROLE")
    try:
        conn.execute("DELETE FROM gateway_config_state WHERE tenant_id = %s", (tenant,))
        conn.execute("DELETE FROM commands WHERE tenant_id = %s", (tenant,))
        conn.execute("DELETE FROM gateways WHERE tenant_id = %s", (tenant,))
        conn.execute("DELETE FROM rule_sets WHERE tenant_id = %s", (tenant,))
        conn.execute("DELETE FROM sites WHERE tenant_id = %s", (tenant,))
        conn.execute("DELETE FROM tenants WHERE tenant_id = %s", (tenant,))
        conn.commit()
    except psycopg.Error:
        conn.rollback()


def _settings(key: str = KEY) -> Settings:
    return Settings(command_hmac_key=key)


def test_activation_publishes_signed_v1(scenario: _Scenario) -> None:
    scenario.seed_gateway()
    scenario.activate_rule_set({"edge": EDGE_DOC})
    publisher = _FakePublisher()

    published = run_config_sync_pass(scenario.conn, _settings(), publisher)

    assert scenario.gateway in published
    mine = scenario.mine(publisher)
    assert len(mine) == 1
    envelope = mine[0][1]
    assert envelope["kind"] == "config_update"
    assert envelope["version"] == 1
    assert envelope["payload"] == EDGE_DOC
    expected = sign_config(KEY.encode(), canonical_payload(EDGE_DOC), 1)
    assert envelope["sig"] == expected
    state = scenario.state()
    assert state["version"] == 1 and state["payload"] == EDGE_DOC


def test_rerun_without_change_is_idempotent(scenario: _Scenario) -> None:
    scenario.seed_gateway()
    scenario.activate_rule_set({"edge": EDGE_DOC})
    publisher = _FakePublisher()
    run_config_sync_pass(scenario.conn, _settings(), publisher)
    run_config_sync_pass(scenario.conn, _settings(), publisher)
    assert len(scenario.mine(publisher)) == 1
    assert scenario.state()["version"] == 1


def test_config_change_bumps_monotonic_version(scenario: _Scenario) -> None:
    scenario.seed_gateway()
    scenario.activate_rule_set({"edge": EDGE_DOC})
    publisher = _FakePublisher()
    run_config_sync_pass(scenario.conn, _settings(), publisher)

    new_doc = {**EDGE_DOC, "command_ttl_s": 20.0}
    scenario.activate_rule_set({"edge": new_doc}, version=2)
    run_config_sync_pass(scenario.conn, _settings(), publisher)

    mine = scenario.mine(publisher)
    assert [p["version"] for _t, p in mine] == [1, 2]
    assert mine[1][1]["payload"] == new_doc
    assert scenario.state()["version"] == 2


def test_ruleset_without_edge_key_publishes_nothing(scenario: _Scenario) -> None:
    scenario.seed_gateway()
    scenario.activate_rule_set({"quorum": {"min_nodes": 3}})
    publisher = _FakePublisher()
    run_config_sync_pass(scenario.conn, _settings(), publisher)
    assert scenario.mine(publisher) == []
    assert scenario.state() is None


def test_gateway_without_thing_is_skipped(scenario: _Scenario) -> None:
    scenario.seed_gateway(iot_thing=None)  # sin identidad IoT → no comandable
    scenario.conn.execute(
        "UPDATE gateways SET iot_thing = NULL WHERE gateway_id = %s", (scenario.gateway,)
    )
    scenario.conn.commit()
    scenario.activate_rule_set({"edge": EDGE_DOC})
    publisher = _FakePublisher()
    run_config_sync_pass(scenario.conn, _settings(), publisher)
    assert publisher.published == [] or scenario.state() is None


def test_no_key_is_fail_closed(scenario: _Scenario) -> None:
    scenario.seed_gateway()
    scenario.activate_rule_set({"edge": EDGE_DOC})
    publisher = _FakePublisher()
    published = run_config_sync_pass(scenario.conn, _settings(key=""), publisher)
    assert published == []
    assert scenario.mine(publisher) == []


def test_publish_failure_keeps_candidate_for_retry(scenario: _Scenario) -> None:
    """El fallo de publish NO quema versión ni estado: se reintenta después."""
    scenario.seed_gateway()
    scenario.activate_rule_set({"edge": EDGE_DOC})
    failing = _FakePublisher(fail=True)
    assert run_config_sync_pass(scenario.conn, _settings(), failing) == []
    assert scenario.state() is None

    ok = _FakePublisher()
    assert run_config_sync_pass(scenario.conn, _settings(), ok) == [scenario.gateway]
    assert scenario.mine(ok)[0][1]["version"] == 1


def test_expires_stale_pending_commands(scenario: _Scenario) -> None:
    scenario.seed_gateway()
    scenario.conn.execute(
        "INSERT INTO commands (tenant_id, site_id, gateway_id, issued_by, channel, "
        "action, nonce, issued_at, expires_at) "
        "VALUES (%s,%s,%s,%s,'siren','activate','n-sync-exp', now() - interval '2 min', "
        "now() - interval '1 min')",
        (scenario.tenant, scenario.site, scenario.gateway, str(uuid.uuid4())),
    )
    scenario.conn.commit()
    run_config_sync_pass(scenario.conn, _settings(), _FakePublisher())
    row = scenario.conn.execute("SELECT status FROM commands WHERE nonce = 'n-sync-exp'").fetchone()
    assert row["status"] == "expired"
