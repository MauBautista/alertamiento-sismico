"""Actuación por quórum confirmado contra Postgres real (T-2.32).

Política ratificada 2026-08-03: quórum ≥3 ⇒ la nube emite comandos de actuación
FIRMADOS a los gateways miembro, a nivel evacuación ∩ equipamiento (T-2.31). La
idempotencia vive en ``commands`` (índice parcial 0023). Mismo aislamiento que
``test_engine`` (tenant fresco, BASE en el futuro, origen aislado en el
Pacífico) + gateways sembrados por sitio.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from psycopg.rows import dict_row

from takab_api.commands.keys import StaticKeyProvider
from takab_api.commands.publisher import PublishError
from takab_api.commands.quorum_actuation import (
    QUORUM_ACTOR_UUID,
    run_quorum_actuation_pass,
)
from takab_api.commands.signing import canonical_payload, sign_command
from takab_api.incident.engine import IncidentEngine
from takab_api.settings import Settings

V_P = 6.5
SRC_LON, SRC_LAT = -98.7, 12.7  # aislado (Pacífico); ≠ origen de test_engine
BASE = datetime(2031, 3, 10, 12, 0, 0, tzinfo=UTC)  # fuera del lookback de test_engine
NOW = BASE + timedelta(seconds=120)

DEFAULT_URL = "postgresql+psycopg://takab:takab_dev@127.0.0.1:5433/takab"
KEY = "clave-quorum-act-test"

EQUIP_ALL = {
    "siren": True,
    "strobe": True,
    "gas_valve": True,
    "elevator": True,
    "door_retainer": True,
}


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
        self.things: dict[str, str] = {}  # site_id -> iot_thing

    def seed_sites(self, specs: list[tuple[float, datetime]]) -> list[str]:
        """Sitio+sensor+feature+incidente por (dist_km, opened_at). Devuelve site_ids."""
        sites: list[str] = []
        for i, (dist_km, opened_at) in enumerate(specs):
            site, sensor = str(uuid.uuid4()), str(uuid.uuid4())
            self.conn.execute(
                "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
                "(%s,%s,%s,'S', ST_Project("
                "ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography, %s, 0.0)::geography)",
                (site, self.tenant, f"QA{i}-{site[:4]}", SRC_LON, SRC_LAT, dist_km * 1000.0),
            )
            self.conn.execute(
                "INSERT INTO sensors (sensor_id, tenant_id, site_id, kind, model) "
                "VALUES (%s,%s,%s,'structural','RS4D')",
                (sensor, self.tenant, site),
            )
            self.conn.execute(
                "INSERT INTO waveform_features_1s "
                "(ts, tenant_id, site_id, sensor_id, channel, pga_g) "
                "VALUES (%s,%s,%s,%s,'ENZ',%s)",
                (opened_at, self.tenant, site, sensor, 0.05 + 0.01 * i),
            )
            self.conn.execute(
                "INSERT INTO incidents (incident_id, event_uuid, tenant_id, site_id, "
                "opened_at, severity, trigger) "
                "VALUES (%s,%s,%s,%s,%s,'warning','local_threshold')",
                (str(uuid.uuid4()), str(uuid.uuid4()), self.tenant, site, opened_at),
            )
            sites.append(site)
        self.conn.commit()
        return sites

    def seed_gateway(self, site: str, *, thing: str | None, equipment: dict | None = None) -> str:
        gateway = str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, iot_thing, "
            "equipment) VALUES (%s,%s,%s,%s,%s,%s::jsonb)",
            (
                gateway,
                self.tenant,
                site,
                f"QA-{gateway[:8]}",
                thing,
                json.dumps(equipment if equipment is not None else EQUIP_ALL),
            ),
        )
        if thing:
            self.things[site] = thing
        self.conn.commit()
        return gateway

    def correlate(self) -> str:
        engine = IncidentEngine(lambda: None, Settings(), lookback_s=300.0)  # type: ignore[arg-type]
        created = engine.run_correlation(self.conn, now=NOW)
        assert len(created) == 1
        return created[0]

    def commands(self) -> list[dict]:
        return self.conn.execute(
            "SELECT gateway_id::text AS gateway_id, channel, status, event_id, nonce, "
            "expires_at FROM commands WHERE issued_by = %s AND tenant_id = %s "
            "ORDER BY gateway_id, channel",
            (QUORUM_ACTOR_UUID, self.tenant),
        ).fetchall()


def _arrival(dist_km: float, jitter_s: float = 0.0) -> datetime:
    return BASE + timedelta(seconds=dist_km / V_P + jitter_s)


THREE_SITES = [(0.0, _arrival(0.0)), (5.0, _arrival(5.0, 0.1)), (10.0, _arrival(10.0, -0.1))]


@pytest.fixture
def scenario() -> Iterator[_Scenario]:
    conn = psycopg.connect(_dsn(), autocommit=False, row_factory=dict_row)
    tenant = str(uuid.uuid4())
    try:
        conn.execute("SET ROLE takab_ingest")  # paridad con la nube (BYPASSRLS)
        conn.execute(
            "INSERT INTO tenants (tenant_id, code, name) VALUES (%s,%s,'QuorumAct Test')",
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
        event_ids = [
            r["event_id"]
            for r in conn.execute(
                "SELECT DISTINCT event_id FROM incidents "
                "WHERE tenant_id = %s AND event_id IS NOT NULL",
                (tenant,),
            ).fetchall()
        ]
        conn.execute("DELETE FROM commands WHERE tenant_id = %s", (tenant,))
        if event_ids:
            conn.execute("DELETE FROM quorum_votes WHERE event_id = ANY(%s)", (event_ids,))
        conn.execute("DELETE FROM incidents WHERE tenant_id = %s", (tenant,))
        if event_ids:
            conn.execute("DELETE FROM seismic_events WHERE event_id = ANY(%s)", (event_ids,))
        conn.execute("DELETE FROM waveform_features_1s WHERE tenant_id = %s", (tenant,))
        conn.execute("DELETE FROM sensors WHERE tenant_id = %s", (tenant,))
        conn.execute("DELETE FROM gateways WHERE tenant_id = %s", (tenant,))
        conn.execute("DELETE FROM sites WHERE tenant_id = %s", (tenant,))
        conn.execute("DELETE FROM tenants WHERE tenant_id = %s", (tenant,))
        conn.commit()
    except psycopg.Error:
        conn.rollback()


def _keys(scenario: _Scenario) -> StaticKeyProvider:
    return StaticKeyProvider(dict.fromkeys(scenario.things.values(), KEY))


def _run(scenario: _Scenario, publisher: _FakePublisher, keys=None) -> list[str]:
    return run_quorum_actuation_pass(
        scenario.conn,
        Settings(),
        publisher,
        keys if keys is not None else _keys(scenario),
        now=NOW,
        lookback_s=300.0,
    )


def test_quorum_commands_members_intersected_with_equipment(scenario: _Scenario) -> None:
    """3 sitios asocian ⇒ burst firmado por gateway: 5 canales al completo, 4 al
    sitio sin gas, NADA al gateway sin iot_thing. La firma es la del canal
    regla-8 (verificable byte a byte) y `origin=quorum` viaja DENTRO de ella."""
    sites = scenario.seed_sites(THREE_SITES)
    gw_full = scenario.seed_gateway(sites[0], thing="qa-thing-0")
    gw_nogas = scenario.seed_gateway(
        sites[1], thing="qa-thing-1", equipment={**EQUIP_ALL, "gas_valve": False}
    )
    scenario.seed_gateway(sites[2], thing=None)  # sin identidad IoT → no comandable
    event_id = scenario.correlate()

    publisher = _FakePublisher()
    issued = _run(scenario, publisher)

    assert len(issued) == 9  # 5 + 4
    by_topic: dict[str, list[dict]] = {}
    for topic, envelope in publisher.published:
        by_topic.setdefault(topic, []).append(envelope)
    assert {len(v) for v in by_topic.values()} == {5, 4}
    assert set(by_topic) == {"takab/cmd/qa-thing-0", "takab/cmd/qa-thing-1"}
    channels_nogas = {e["payload"]["channel"] for e in by_topic["takab/cmd/qa-thing-1"]}
    assert "gas_valve" not in channels_nogas and "siren" in channels_nogas

    sample = by_topic["takab/cmd/qa-thing-0"][0]
    assert sample["kind"] == "command"
    assert sample["payload"]["origin"] == "quorum"
    assert sample["payload"]["event_id"] == event_id
    expected = sign_command(
        KEY.encode(), canonical_payload(sample["payload"]), sample["nonce"], sample["ts"]
    )
    assert sample["sig"] == expected

    rows = scenario.commands()
    assert len(rows) == 9
    assert {r["status"] for r in rows} == {"pending"}
    assert {r["event_id"] for r in rows} == {event_id}
    assert all(r["expires_at"] > NOW for r in rows)
    gw_rows = {r["gateway_id"] for r in rows}
    assert gw_rows == {gw_full, gw_nogas}


def test_second_pass_is_idempotent(scenario: _Scenario) -> None:
    sites = scenario.seed_sites(THREE_SITES)
    for i, site in enumerate(sites):
        scenario.seed_gateway(site, thing=f"qa-idem-{i}")
    scenario.correlate()

    publisher = _FakePublisher()
    first = _run(scenario, publisher)
    second = _run(scenario, publisher)

    assert len(first) == 15  # 3 gateways × 5 canales
    assert second == []
    assert len(publisher.published) == 15
    assert len(scenario.commands()) == 15


def test_publish_failure_keeps_candidate_for_retry(scenario: _Scenario) -> None:
    """El evento de red SOBREVIVE al publish fallido (txn separada) y el burst
    sale completo en la siguiente pasada — sin filas fantasma."""
    sites = scenario.seed_sites(THREE_SITES)
    scenario.seed_gateway(sites[0], thing="qa-retry-0")
    event_id = scenario.correlate()

    broken = _FakePublisher(fail=True)
    assert _run(scenario, broken) == []
    assert scenario.commands() == []
    ev = scenario.conn.execute(
        "SELECT source FROM seismic_events WHERE event_id = %s", (event_id,)
    ).fetchone()
    assert ev is not None and ev["source"] == "local_quorum"

    healthy = _FakePublisher()
    assert len(_run(scenario, healthy)) == 5
    assert len(scenario.commands()) == 5


def test_gateway_without_key_is_fail_closed(scenario: _Scenario) -> None:
    sites = scenario.seed_sites(THREE_SITES)
    scenario.seed_gateway(sites[0], thing="qa-key-0")
    scenario.seed_gateway(sites[1], thing="qa-sin-clave")
    scenario.correlate()

    publisher = _FakePublisher()
    issued = run_quorum_actuation_pass(
        scenario.conn,
        Settings(),
        publisher,
        StaticKeyProvider({"qa-key-0": KEY}),  # SOLO el primero tiene clave
        now=NOW,
        lookback_s=300.0,
    )
    assert len(issued) == 5
    assert {t for t, _ in publisher.published} == {"takab/cmd/qa-key-0"}


def test_ledger_index_blocks_duplicate_burst(scenario: _Scenario) -> None:
    """El índice parcial de 0023 convierte un duplicado del actor quórum en
    no-op (ON CONFLICT DO NOTHING), venga de la pasada que venga."""
    sites = scenario.seed_sites(THREE_SITES)
    gw = scenario.seed_gateway(sites[0], thing="qa-dup-0")
    event_id = scenario.correlate()
    _run(scenario, _FakePublisher())

    inserted = scenario.conn.execute(
        "INSERT INTO commands (tenant_id, site_id, gateway_id, issued_by, channel, "
        "action, event_id, nonce, expires_at) "
        "VALUES (%s,%s,%s,%s,'siren','activate',%s,%s,%s) "
        "ON CONFLICT DO NOTHING RETURNING command_id",
        (scenario.tenant, sites[0], gw, QUORUM_ACTOR_UUID, event_id, uuid.uuid4().hex, NOW),
    ).fetchone()
    scenario.conn.commit()
    assert inserted is None  # el ledger lo absorbió
    assert len([r for r in scenario.commands() if r["channel"] == "siren"]) == 1
