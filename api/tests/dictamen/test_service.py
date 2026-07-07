"""Pasada de dictamen automático contra Postgres real (T-1.20 · B5).

Patrón de ``tests/incident/test_engine.py``: siembra SQL directa bajo
``SET ROLE takab_ingest`` (paridad con la nube), tenant fresco por test y BASE
en el futuro lejano (2032) para aislar el barrido cross-tenant de los otros
archivos. La limpieza apaga los triggers append-only con
``session_replication_role`` (superusuario) — en producción esas filas son
inmutables por diseño.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from psycopg.rows import dict_row

from takab_api.dictamen.service import run_dictamen_pass
from takab_api.settings import Settings

SRC_LON, SRC_LAT = -99.5, 12.5  # aislado de toda flota fixture (Pacífico)
BASE = datetime(2032, 1, 15, 12, 0, 0, tzinfo=UTC)
NOW = BASE + timedelta(seconds=180)  # siembras a BASE quedan pasadas del settle

DEFAULT_URL = "postgresql+psycopg://takab:takab_dev@127.0.0.1:5433/takab"


def _dsn() -> str:
    url = os.environ.get("DATABASE_URL", DEFAULT_URL)
    return url.replace("postgresql+psycopg://", "postgresql://")


class _Scenario:
    def __init__(self, conn: psycopg.Connection, tenant: str) -> None:
        self.conn = conn
        self.tenant = tenant

    def seed_incident(
        self,
        *,
        severity: str = "warning",
        pga_g: float | None = 0.06,
        opened_at: datetime | None = None,
        event_id: str | None = None,
    ) -> dict:
        """Sitio + sensor estructural + feature (opcional) + incidente."""
        site, sensor = str(uuid.uuid4()), str(uuid.uuid4())
        incident = str(uuid.uuid4())
        ts = opened_at or BASE
        self.conn.execute(
            "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
            "(%s,%s,%s,'S', ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography)",
            (site, self.tenant, f"D-{site[:8]}", SRC_LON, SRC_LAT),
        )
        self.conn.execute(
            "INSERT INTO sensors (sensor_id, tenant_id, site_id, kind, model) "
            "VALUES (%s,%s,%s,'structural','RS4D')",
            (sensor, self.tenant, site),
        )
        if pga_g is not None:
            self.conn.execute(
                "INSERT INTO waveform_features_1s "
                "(ts, tenant_id, site_id, sensor_id, channel, pga_g) "
                "VALUES (%s,%s,%s,%s,'ENZ',%s)",
                (ts, self.tenant, site, sensor, pga_g),
            )
        self.conn.execute(
            "INSERT INTO incidents (incident_id, event_uuid, tenant_id, site_id, "
            "event_id, opened_at, severity, trigger) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,'local_threshold')",
            (incident, str(uuid.uuid4()), self.tenant, site, event_id, ts, severity),
        )
        self.conn.commit()
        return {"incident": incident, "site": site, "sensor": sensor}

    def corroborate(self, incident_id: str, sensor_id: str, *, nodes: int = 3) -> str:
        """Crea el evento de red + ``nodes`` votos y linkea el incidente."""
        event_id = f"EVT-D-{uuid.uuid4().hex[:10]}"
        self.conn.execute(
            "INSERT INTO seismic_events (event_id, source, detected_at) "
            "VALUES (%s, 'local_quorum', %s)",
            (event_id, BASE),
        )
        voters = [sensor_id]
        for _ in range(nodes - 1):
            other_site, other_sensor = str(uuid.uuid4()), str(uuid.uuid4())
            self.conn.execute(
                "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
                "(%s,%s,%s,'S', ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography)",
                (other_site, self.tenant, f"D-{other_site[:8]}", SRC_LON, SRC_LAT),
            )
            self.conn.execute(
                "INSERT INTO sensors (sensor_id, tenant_id, site_id, kind, model) "
                "VALUES (%s,%s,%s,'structural','RS4D')",
                (other_sensor, self.tenant, other_site),
            )
            voters.append(other_sensor)
        for i, voter in enumerate(voters):
            self.conn.execute(
                "INSERT INTO quorum_votes "
                "(event_id, sensor_id, detected_at, pga_g, delta_s, counted) "
                "VALUES (%s,%s,%s,0.05,%s,true)",
                (event_id, voter, BASE + timedelta(seconds=i), float(i)),
            )
        self.conn.execute(
            "UPDATE incidents SET event_id = %s WHERE incident_id = %s",
            (event_id, incident_id),
        )
        self.conn.commit()
        return event_id

    def dictamens(self, incident_id: str) -> list[dict]:
        return self.conn.execute(
            "SELECT dictamen_id, status, basis, signed_by, supersedes_dictamen_id "
            "FROM dictamens WHERE incident_id = %s ORDER BY created_at, dictamen_id",
            (incident_id,),
        ).fetchall()

    def actions(self, incident_id: str) -> list[dict]:
        return self.conn.execute(
            "SELECT kind, actor, payload FROM incident_actions WHERE incident_id = %s ORDER BY ts",
            (incident_id,),
        ).fetchall()

    def sign_head(self, incident_id: str, head_id: str, status: str) -> None:
        self.conn.execute(
            "INSERT INTO dictamens (tenant_id, incident_id, status, basis, "
            "signed_by, supersedes_dictamen_id) "
            "VALUES (%s,%s,%s,'{}'::jsonb,%s,%s)",
            (self.tenant, incident_id, status, str(uuid.uuid4()), head_id),
        )
        self.conn.commit()


@pytest.fixture
def scenario() -> Iterator[_Scenario]:
    conn = psycopg.connect(_dsn(), autocommit=False, row_factory=dict_row)
    tenant = str(uuid.uuid4())
    try:
        conn.execute("SET ROLE takab_ingest")
        conn.execute(
            "INSERT INTO tenants (tenant_id, code, name) VALUES (%s,%s,'Dictamen Test')",
            (tenant, tenant[:8]),
        )
        conn.commit()
        yield _Scenario(conn, tenant)
    finally:
        _cleanup(conn, tenant)
        conn.close()


def _cleanup(conn: psycopg.Connection, tenant: str) -> None:
    """Purga el grafo del tenant. dictamens/incident_actions son append-only:
    el superusuario apaga los triggers de fila vía session_replication_role
    (solo en tests; en producción esas filas son inmutables)."""
    conn.rollback()
    conn.execute("RESET ROLE")
    try:
        conn.execute("SET session_replication_role = 'replica'")
        event_ids = [
            r["event_id"]
            for r in conn.execute(
                "SELECT DISTINCT event_id FROM incidents "
                "WHERE tenant_id = %s AND event_id IS NOT NULL",
                (tenant,),
            ).fetchall()
        ]
        conn.execute("DELETE FROM incident_actions WHERE tenant_id = %s", (tenant,))
        conn.execute("DELETE FROM dictamens WHERE tenant_id = %s", (tenant,))
        conn.execute("DELETE FROM incidents WHERE tenant_id = %s", (tenant,))
        if event_ids:
            conn.execute("DELETE FROM quorum_votes WHERE event_id = ANY(%s)", (event_ids,))
            conn.execute("DELETE FROM seismic_events WHERE event_id = ANY(%s)", (event_ids,))
        conn.execute("DELETE FROM waveform_features_1s WHERE tenant_id = %s", (tenant,))
        conn.execute("DELETE FROM sensors WHERE tenant_id = %s", (tenant,))
        conn.execute("DELETE FROM rule_sets WHERE tenant_id = %s", (tenant,))
        conn.execute("DELETE FROM sites WHERE tenant_id = %s", (tenant,))
        conn.execute("DELETE FROM tenants WHERE tenant_id = %s", (tenant,))
        conn.execute("SET session_replication_role = 'origin'")
        conn.commit()
    except psycopg.Error:
        conn.rollback()


def _run(conn: psycopg.Connection, *, now: datetime = NOW) -> list[str]:
    return run_dictamen_pass(conn, Settings(), now=now, lookback_s=300.0, settle_s=60.0)


# ------------------------------------------------------------------ emisión


def test_emits_preliminary_dictamen(scenario: _Scenario) -> None:
    seeded = scenario.seed_incident(severity="warning", pga_g=0.06)
    created = _run(scenario.conn)

    rows = scenario.dictamens(seeded["incident"])
    assert len(rows) == 1
    row = rows[0]
    assert str(row["dictamen_id"]) in created
    assert row["status"] == "inhabit_monitor"
    assert row["signed_by"] is None  # preliminar automático
    assert row["supersedes_dictamen_id"] is None
    basis = row["basis"]
    assert basis["rule_set_version"]
    assert basis["evidence"]["severity"] == "warning"
    assert basis["evidence"]["pga_g"] == pytest.approx(0.06)

    acts = scenario.actions(seeded["incident"])
    assert [a["kind"] for a in acts] == ["dictamen"]
    assert acts[0]["actor"] == "system"
    assert acts[0]["payload"]["status"] == "inhabit_monitor"


def test_high_pga_yields_no_inhabit(scenario: _Scenario) -> None:
    seeded = scenario.seed_incident(severity="warning", pga_g=0.30)
    _run(scenario.conn)
    rows = scenario.dictamens(seeded["incident"])
    assert rows and rows[0]["status"] == "no_inhabit_inspect"


def test_settle_window_defers_recent_incident(scenario: _Scenario) -> None:
    seeded = scenario.seed_incident(opened_at=NOW - timedelta(seconds=10))
    assert _run(scenario.conn) == []
    assert scenario.dictamens(seeded["incident"]) == []

    # Pasado el settle, el mismo incidente sí recibe su dictamen.
    later = NOW + timedelta(seconds=120)
    assert len(_run(scenario.conn, now=later)) == 1


def test_rerun_is_idempotent(scenario: _Scenario) -> None:
    seeded = scenario.seed_incident()
    first = _run(scenario.conn)
    assert len(first) == 1
    assert _run(scenario.conn) == []
    assert len(scenario.dictamens(seeded["incident"])) == 1
    assert len(scenario.actions(seeded["incident"])) == 1


# ---------------------------------------------------------------- versionado


def test_later_corroboration_supersedes_unsigned_head(scenario: _Scenario) -> None:
    """El quórum llega DESPUÉS del preliminar → corrección = fila nueva."""
    seeded = scenario.seed_incident(severity="info", pga_g=0.01)
    _run(scenario.conn)
    head = scenario.dictamens(seeded["incident"])[0]
    assert head["status"] == "normal_operation"

    scenario.corroborate(seeded["incident"], seeded["sensor"], nodes=3)
    _run(scenario.conn)

    rows = scenario.dictamens(seeded["incident"])
    assert len(rows) == 2
    new = rows[1]
    assert new["status"] == "inhabit_monitor"  # regla de nodos: eleva
    assert new["supersedes_dictamen_id"] == head["dictamen_id"]
    assert new["signed_by"] is None


def test_signed_head_is_never_superseded_automatically(scenario: _Scenario) -> None:
    """El juicio del inspector manda: el servicio jamás corrige un firmado."""
    seeded = scenario.seed_incident(severity="info", pga_g=0.01)
    _run(scenario.conn)
    head = scenario.dictamens(seeded["incident"])[0]
    scenario.sign_head(seeded["incident"], str(head["dictamen_id"]), "normal_operation")

    scenario.corroborate(seeded["incident"], seeded["sensor"], nodes=3)
    assert _run(scenario.conn) == []
    assert len(scenario.dictamens(seeded["incident"])) == 2  # prelim + firma


def test_unchanged_status_does_not_duplicate(scenario: _Scenario) -> None:
    """Corroboración que NO cambia el status calculado → sin fila nueva."""
    seeded = scenario.seed_incident(severity="warning", pga_g=0.06)
    _run(scenario.conn)
    scenario.corroborate(seeded["incident"], seeded["sensor"], nodes=3)
    assert _run(scenario.conn) == []
    assert len(scenario.dictamens(seeded["incident"])) == 1


# -------------------------------------------------------------- rule_sets


def test_rule_set_config_overrides_thresholds(scenario: _Scenario) -> None:
    """config.dictamen del rule_set del tenant sube el umbral de monitoreo."""
    seeded = scenario.seed_incident(severity="info", pga_g=0.10)
    scenario.conn.execute(
        "INSERT INTO rule_sets (tenant_id, scope_type, scope_id, version, "
        "is_active, config) VALUES (%s,'tenant',%s,1,true,%s::jsonb)",
        (
            scenario.tenant,
            scenario.tenant,
            '{"dictamen": {"pga_no_inhabit_g": 0.5, "pga_monitor_g": 0.2}}',
        ),
    )
    scenario.conn.commit()
    _run(scenario.conn)
    rows = scenario.dictamens(seeded["incident"])
    assert rows and rows[0]["status"] == "normal_operation"  # 0.10 < 0.2 configurado
