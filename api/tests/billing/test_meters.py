"""Pasada de medidores diarios contra Postgres real (T-1.24 · B10).

Siembra un día completo de actividad (features + health + acciones +
incidentes, con ruido FUERA de la ventana y un segundo tenant) y verifica los
medidores exactos, el aislamiento por tenant y el UPSERT idempotente.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta

import psycopg
import pytest
from psycopg.rows import dict_row

from takab_api.billing.meters import run_billing_pass
from takab_api.settings import Settings

DEFAULT_URL = "postgresql+psycopg://takab:takab_dev@127.0.0.1:5433/takab"
DAY = date(2026, 7, 6)
T0 = datetime(2026, 7, 6, 10, 0, 0, tzinfo=UTC)


def _dsn() -> str:
    url = os.environ.get("DATABASE_URL", DEFAULT_URL)
    return url.replace("postgresql+psycopg://", "postgresql://")


class _Scenario:
    def __init__(self, conn: psycopg.Connection) -> None:
        self.conn = conn
        self.tenants: list[str] = []

    def seed_tenant(self, *, sites: int = 1) -> dict:
        tenant = str(uuid.uuid4())
        self.tenants.append(tenant)
        c = self.conn
        c.execute("RESET ROLE")
        c.execute(
            "INSERT INTO tenants (tenant_id, code, name) VALUES (%s,%s,'Bill Test')",
            (tenant, tenant[:8]),
        )
        out = {"tenant": tenant, "sites": [], "gateways": [], "sensors": []}
        for _ in range(sites):
            site, gw, sensor = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
            c.execute(
                "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
                "(%s,%s,%s,'S', ST_SetSRID(ST_MakePoint(-102.5,10.5),4326)::geography)",
                (site, tenant, f"BL-{site[:8]}"),
            )
            c.execute(
                "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial) "
                "VALUES (%s,%s,%s,%s)",
                (gw, tenant, site, f"SER-{gw[:8]}"),
            )
            c.execute(
                "INSERT INTO sensors (sensor_id, tenant_id, site_id, gateway_id, kind, "
                "model) VALUES (%s,%s,%s,%s,'structural','RS4D')",
                (sensor, tenant, site, gw),
            )
            out["sites"].append(site)
            out["gateways"].append(gw)
            out["sensors"].append(sensor)
        c.commit()
        return out

    def add_features(self, fleet: dict, n: int, *, site_idx: int = 0, offset_s: float = 0) -> None:
        for i in range(n):
            self.conn.execute(
                "INSERT INTO waveform_features_1s (ts, tenant_id, site_id, sensor_id, "
                "channel, pga_g) VALUES (%s,%s,%s,%s,'ENZ',0.01)",
                (
                    T0 + timedelta(seconds=offset_s + i),
                    fleet["tenant"],
                    fleet["sites"][site_idx],
                    fleet["sensors"][site_idx],
                ),
            )
        self.conn.commit()

    def add_health(self, fleet: dict, n: int, *, offset_s: float = 0) -> None:
        for i in range(n):
            self.conn.execute(
                "INSERT INTO device_health (ts, tenant_id, gateway_id, reason) "
                "VALUES (%s,%s,%s,'heartbeat')",
                (T0 + timedelta(seconds=offset_s + 10 * i), fleet["tenant"], fleet["gateways"][0]),
            )
        self.conn.commit()

    def add_incident(self, fleet: dict, *, offset_s: float = 0, actions: int = 0) -> None:
        incident = str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO incidents (incident_id, event_uuid, tenant_id, site_id, "
            "opened_at, severity, trigger) "
            "VALUES (%s,%s,%s,%s,%s,'warning','local_threshold')",
            (
                incident,
                str(uuid.uuid4()),
                fleet["tenant"],
                fleet["sites"][0],
                T0 + timedelta(seconds=offset_s),
            ),
        )
        for i in range(actions):
            self.conn.execute(
                "INSERT INTO incident_actions (incident_id, tenant_id, ts, kind, actor) "
                "VALUES (%s,%s,%s,'siren_on',%s)",
                (
                    incident,
                    fleet["tenant"],
                    T0 + timedelta(seconds=offset_s + 1 + i),
                    f"edge:test-{i}",
                ),
            )
        self.conn.commit()

    def meters_row(self, tenant: str) -> dict | None:
        self.conn.execute("RESET ROLE")
        return self.conn.execute(
            "SELECT active_sites, messages, gb_approx, incidents "
            "FROM billing_meters_daily WHERE tenant_id = %s AND day = %s",
            (tenant, DAY),
        ).fetchone()


@pytest.fixture
def scenario() -> Iterator[_Scenario]:
    conn = psycopg.connect(_dsn(), autocommit=False, row_factory=dict_row)
    sc = _Scenario(conn)
    try:
        yield sc
    finally:
        _cleanup(conn, sc.tenants)
        conn.close()


def _cleanup(conn: psycopg.Connection, tenants: list[str]) -> None:
    conn.rollback()
    conn.execute("RESET ROLE")
    try:
        conn.execute("SET session_replication_role = 'replica'")
        for tenant in tenants:
            for table in (
                "billing_meters_daily",
                "incident_actions",
                "incidents",
                "device_health",
                "waveform_features_1s",
                "sensors",
                "gateways",
                "sites",
                "tenants",
            ):
                conn.execute(
                    f"DELETE FROM {table} WHERE tenant_id = %s",  # noqa: S608
                    (tenant,),
                )
        conn.execute("SET session_replication_role = 'origin'")
        conn.commit()
    except psycopg.Error:
        conn.rollback()


def _run(sc: _Scenario) -> dict:
    sc.conn.execute("SET ROLE takab_ingest")  # paridad con la pasada real
    meters = run_billing_pass(sc.conn, Settings(), DAY)
    sc.conn.execute("RESET ROLE")
    return meters


def test_meters_exact_for_one_day(scenario: _Scenario) -> None:
    fleet = scenario.seed_tenant(sites=2)
    scenario.add_features(fleet, 100, site_idx=0)  # sitio 0 activo
    scenario.add_health(fleet, 5)  # gateway del sitio 0
    scenario.add_incident(fleet, actions=3)
    scenario.add_incident(fleet, offset_s=3600)
    # Ruido FUERA de la ventana (día siguiente): no cuenta.
    scenario.add_features(fleet, 7, site_idx=1, offset_s=86_400 + 60)

    _run(scenario)
    row = scenario.meters_row(fleet["tenant"])

    assert row is not None
    assert row["active_sites"] == 1  # el sitio 1 solo tuvo datos fuera del día
    assert row["messages"] == 100 + 5 + 3  # features + health + actions
    assert row["incidents"] == 2
    expected_gb = 108 * Settings().billing_row_bytes_estimate / 1e9
    assert float(row["gb_approx"]) == pytest.approx(expected_gb)


def test_tenants_are_isolated(scenario: _Scenario) -> None:
    a = scenario.seed_tenant()
    b = scenario.seed_tenant()
    scenario.add_features(a, 10)
    scenario.add_features(b, 20)

    _run(scenario)

    assert scenario.meters_row(a["tenant"])["messages"] == 10
    assert scenario.meters_row(b["tenant"])["messages"] == 20


def test_rerun_is_idempotent_upsert(scenario: _Scenario) -> None:
    fleet = scenario.seed_tenant()
    scenario.add_features(fleet, 10)
    _run(scenario)
    first = scenario.meters_row(fleet["tenant"])

    # Backfill tardío engorda el día → el re-run ACTUALIZA (no duplica).
    scenario.add_features(fleet, 5, offset_s=7200)
    _run(scenario)
    second = scenario.meters_row(fleet["tenant"])

    assert first["messages"] == 10
    assert second["messages"] == 15
    scenario.conn.execute("RESET ROLE")
    count = scenario.conn.execute(
        "SELECT count(*) FROM billing_meters_daily WHERE tenant_id = %s",
        (fleet["tenant"],),
    ).fetchone()["count"]
    assert count == 1  # un solo renglón por (tenant, día)


def test_tenant_without_activity_has_no_row(scenario: _Scenario) -> None:
    fleet = scenario.seed_tenant()  # flota sin datos en el día
    _run(scenario)
    assert scenario.meters_row(fleet["tenant"]) is None
