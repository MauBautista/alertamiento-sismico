"""E2E integrado del motor de incidentes (T-1.19 · Fase 2).

Flujo completo contra Postgres real: se siembran 3 incidentes de sitios
DISTINTOS (como ``takab_ingest``) con arribos de onda P realistas inter-ciudad,
se corre ``run_correlation`` UNA vez y se verifica el grafo de red completo —
1 ``seismic_events`` (source 'local_quorum') + 3 ``quorum_votes`` + los 3
``incidents`` linkeados— y luego una SEGUNDA pasada idempotente (sin cambios).

Es el ensamblaje de B1 (correlación) + B2 (fail-open en la misma txn): distinto
de ``test_engine`` (unidades de correlación) en que ejerce el camino integrado de
punta a punta con la firma pública ``IncidentEngine.run_correlation``.

Siembra por SQL directo bajo ``SET ROLE takab_ingest`` (BYPASSRLS), igual que en
la nube; ``BASE`` en el futuro lejano aísla el escaneo cross-tenant §4.5 de los
datos de otros archivos, y el cleanup purga sólo el grafo de este tenant.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from psycopg.rows import dict_row

from takab_api.incident.engine import IncidentEngine
from takab_api.settings import Settings

V_P = 6.5
# Origen aislado (Pacífico, muy al sur) — lejos de toda flota fixture para que el
# fail-open no abra incidentes sintéticos imborrables en sitios de otros tenants
# (ver nota en test_engine); BASE distinto aísla temporalmente de test_engine.
SRC_LON, SRC_LAT = -98.7, 12.5
BASE = datetime(2031, 3, 10, 9, 0, 0, tzinfo=UTC)  # futuro lejano: aísla el barrido §4.5

DEFAULT_URL = "postgresql+psycopg://takab:takab_dev@127.0.0.1:5433/takab"


def _dsn() -> str:
    url = os.environ.get("DATABASE_URL", DEFAULT_URL)
    return url.replace("postgresql+psycopg://", "postgresql://")


def _arrival(dist_km: float, jitter_s: float = 0.0) -> datetime:
    return BASE + timedelta(seconds=dist_km / V_P + jitter_s)


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    c = psycopg.connect(_dsn(), autocommit=False, row_factory=dict_row)
    tenant = str(uuid.uuid4())
    try:
        c.execute("SET ROLE takab_ingest")  # paridad con la nube (BYPASSRLS)
        c.execute(
            "INSERT INTO tenants (tenant_id, code, name) VALUES (%s,%s,'E2E Test')",
            (tenant, tenant[:8]),
        )
        c.commit()
        c.tenant = tenant  # type: ignore[attr-defined]
        yield c
    finally:
        _cleanup(c, tenant)
        c.close()


def _seed_detection(
    c: psycopg.Connection, tenant: str, dist_km: float, opened_at: datetime, idx: int
) -> None:
    site, sensor, incident = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    c.execute(
        "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
        "(%s,%s,%s,'S', ST_Project("
        "ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography, %s, 0.0)::geography)",
        (site, tenant, f"E{idx}-{site[:4]}", SRC_LON, SRC_LAT, dist_km * 1000.0),
    )
    c.execute(
        "INSERT INTO sensors (sensor_id, tenant_id, site_id, kind, model) "
        "VALUES (%s,%s,%s,'structural','RS4D')",
        (sensor, tenant, site),
    )
    c.execute(
        "INSERT INTO waveform_features_1s (ts, tenant_id, site_id, sensor_id, channel, pga_g) "
        "VALUES (%s,%s,%s,%s,'ENZ',%s)",
        (opened_at, tenant, site, sensor, 0.06 + 0.01 * idx),
    )
    c.execute(
        "INSERT INTO incidents (incident_id, event_uuid, tenant_id, site_id, "
        "opened_at, severity, trigger) VALUES (%s,%s,%s,%s,%s,'warning','local_threshold')",
        (incident, str(uuid.uuid4()), tenant, site, opened_at),
    )


def _cleanup(c: psycopg.Connection, tenant: str) -> None:
    c.rollback()
    c.execute("RESET ROLE")  # el superusuario tiene DELETE; takab_ingest no
    try:
        event_ids = [
            r["event_id"]
            for r in c.execute(
                "SELECT DISTINCT event_id FROM incidents "
                "WHERE tenant_id = %s AND event_id IS NOT NULL",
                (tenant,),
            ).fetchall()
        ]
        if event_ids:
            c.execute("DELETE FROM quorum_votes WHERE event_id = ANY(%s)", (event_ids,))
        c.execute(
            "DELETE FROM incident_actions ia USING incidents i "
            "WHERE ia.incident_id = i.incident_id AND i.tenant_id = %s",
            (tenant,),
        )
        c.execute("DELETE FROM incidents WHERE tenant_id = %s", (tenant,))
        if event_ids:
            c.execute("DELETE FROM seismic_events WHERE event_id = ANY(%s)", (event_ids,))
        c.execute("DELETE FROM waveform_features_1s WHERE tenant_id = %s", (tenant,))
        c.execute("DELETE FROM sensors WHERE tenant_id = %s", (tenant,))
        c.execute("DELETE FROM sites WHERE tenant_id = %s", (tenant,))
        c.execute("DELETE FROM tenants WHERE tenant_id = %s", (tenant,))
        c.commit()
    except psycopg.Error:
        c.rollback()


def _engine() -> IncidentEngine:
    # conn_factory sin uso en run_correlation (sólo el bucle run() lo consume).
    return IncidentEngine(lambda: None, Settings(), lookback_s=300.0)  # type: ignore[arg-type]


def test_three_sites_correlate_end_to_end(conn: psycopg.Connection) -> None:
    """3 detecciones (0/50/100 km) → 1 evento de red + 3 votos + 3 incidentes linkeados."""
    tenant = conn.tenant  # type: ignore[attr-defined]
    for idx, dist in enumerate((0.0, 50.0, 100.0)):
        _seed_detection(conn, tenant, dist, _arrival(dist, jitter_s=0.1 * idx), idx)
    conn.commit()

    created = _engine().run_correlation(conn, now=BASE + timedelta(seconds=120))
    assert len(created) == 1
    event_id = created[0]

    ev = conn.execute(
        "SELECT source, magnitude, epicenter IS NOT NULL AS has_epi "
        "FROM seismic_events WHERE event_id = %s",
        (event_id,),
    ).fetchone()
    assert ev is not None
    assert ev["source"] == "local_quorum"
    assert ev["magnitude"] is None  # sin magnitud en vivo (WR-1 booleano)
    assert ev["has_epi"] is True  # centroide aproximado (no autoritativo)

    votes = conn.execute(
        "SELECT count(*) AS n, count(*) FILTER (WHERE counted) AS counted, "
        "count(*) FILTER (WHERE pga_g > 0) AS positive_pga "
        "FROM quorum_votes WHERE event_id = %s",
        (event_id,),
    ).fetchone()
    assert votes["n"] == 3
    assert votes["counted"] == 3
    assert votes["positive_pga"] == 3  # PGA del pico de waveform_features_1s

    linked = conn.execute(
        "SELECT count(*) AS n FROM incidents WHERE tenant_id = %s AND event_id = %s",
        (tenant, event_id),
    ).fetchone()
    assert linked["n"] == 3


def test_rerun_leaves_graph_unchanged(conn: psycopg.Connection) -> None:
    """Segunda pasada idempotente: sin evento nuevo, sin votos extra, sin re-link."""
    tenant = conn.tenant  # type: ignore[attr-defined]
    for idx, dist in enumerate((0.0, 50.0, 100.0)):
        _seed_detection(conn, tenant, dist, _arrival(dist), idx)
    conn.commit()

    now = BASE + timedelta(seconds=120)
    first = _engine().run_correlation(conn, now=now)
    assert len(first) == 1
    event_id = first[0]

    second = _engine().run_correlation(conn, now=now)
    assert second == []  # todos corroborados (event_id IS NOT NULL)

    n_events = conn.execute(
        "SELECT count(DISTINCT event_id) AS n FROM incidents "
        "WHERE tenant_id = %s AND event_id IS NOT NULL",
        (tenant,),
    ).fetchone()["n"]
    assert n_events == 1
    n_votes = conn.execute(
        "SELECT count(*) AS n FROM quorum_votes WHERE event_id = %s", (event_id,)
    ).fetchone()["n"]
    assert n_votes == 3
