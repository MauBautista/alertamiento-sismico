"""Fail-open del quórum (T-1.19 · B2 · G6). DB propia, fixtures por SQL.

Sitio SIN ENLACE en rango → incidente sintético; fuera de rango / con enlace /
que ya reportó (miembro) / sin gateway → nada; re-run idempotente; señal emitida.
Corre como ``takab_ingest`` (BYPASSRLS), igual que el engine en producción.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

import psycopg
import pytest
from psycopg.rows import dict_row

from takab_api.incident import fail_open as fo
from takab_api.incident.fail_open import handle_fail_open
from takab_api.incident.quorum import QuorumParams

NOW = datetime(2026, 7, 7, 12, 0, 0, tzinfo=UTC)
PARAMS = QuorumParams(min_nodes=3, v_p_km_s=6.5, margin_s=3.0, max_window_s=30.0)
# Alcance = v_P · max_window = 6.5·30 = 195 km. El escaneo de fail-open es
# cross-tenant global (dato de RED, blueprint §4.5), así que el epicentro se ubica
# en una región AISLADA (Bajío, ~León) sin flota committeada de otros archivos
# (p.ej. la mini-flota persistente de test_ingest_registry en ~-98.2/19.04, >400 km):
# el barrido sólo alcanza los sitios sembrados aquí → el test es orden-independiente.
EPICENTER = (-101.13, 21.43)
EVENT_ID = "EVT-B2-FAILOPEN"

TENANT = "10000000-0000-0000-0000-0000000000b2"
SITE_OFF_IN = "20000000-0000-0000-0000-000000000001"
SITE_OFF_OUT = "20000000-0000-0000-0000-000000000002"
SITE_ONLINE = "20000000-0000-0000-0000-000000000003"
SITE_MEMBER = "20000000-0000-0000-0000-000000000004"
SITE_NO_GW = "20000000-0000-0000-0000-000000000005"
GW_OFF_IN = "30000000-0000-0000-0000-000000000001"
GW_OFF_OUT = "30000000-0000-0000-0000-000000000002"
GW_ONLINE = "30000000-0000-0000-0000-000000000003"
GW_MEMBER = "30000000-0000-0000-0000-000000000004"


def _dsn() -> str:
    url = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://takab:takab_dev@127.0.0.1:5433/takab"
    )
    return url.replace("postgresql+psycopg://", "postgresql://")


@pytest.fixture
def dconn() -> psycopg.Connection:
    """Conexión dict_row transaccional (se revierte); rol takab_ingest para las llamadas."""
    c = psycopg.connect(_dsn(), autocommit=False, row_factory=dict_row)
    try:
        yield c
    finally:
        c.rollback()
        c.close()


def _add_site(c: psycopg.Connection, sid: str, code: str, lon: float, lat: float) -> None:
    c.execute(
        "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
        "(%s,%s,%s,'S',ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography)",
        (sid, TENANT, code, lon, lat),
    )


def _add_gw(c: psycopg.Connection, gid: str, sid: str, serial: str, status: str) -> None:
    c.execute(
        "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, status) "
        "VALUES (%s,%s,%s,%s,%s)",
        (gid, TENANT, sid, serial, status),
    )


def _seed(c: psycopg.Connection) -> None:
    c.execute("RESET ROLE")
    c.execute(
        "INSERT INTO tenants (tenant_id, code, name, visibility) VALUES (%s,'B2T','B2','private')",
        (TENANT,),
    )
    _add_site(c, SITE_OFF_IN, "OFFIN", *EPICENTER)
    _add_site(c, SITE_OFF_OUT, "OFFOUT", -95.0, 21.43)  # ~635 km al este: fuera de rango
    _add_site(c, SITE_ONLINE, "ONLINE", *EPICENTER)
    _add_site(c, SITE_MEMBER, "MEMBER", *EPICENTER)
    _add_site(c, SITE_NO_GW, "NOGW", *EPICENTER)
    _add_gw(c, GW_OFF_IN, SITE_OFF_IN, "SER-OFFIN", "offline")
    _add_gw(c, GW_OFF_OUT, SITE_OFF_OUT, "SER-OFFOUT", "offline")
    _add_gw(c, GW_ONLINE, SITE_ONLINE, "SER-ONLINE", "online")
    _add_gw(c, GW_MEMBER, SITE_MEMBER, "SER-MEMBER", "offline")
    # SITE_NO_GW no tiene gateway → no es candidato a fail-open.
    # Heartbeat fresco del gateway online → CON ENLACE (edad 0 <= umbral).
    c.execute(
        "INSERT INTO device_health (ts, tenant_id, gateway_id, reason) "
        "VALUES (%s,%s,%s,'heartbeat')",
        (NOW, TENANT, GW_ONLINE),
    )
    c.execute(
        "INSERT INTO seismic_events (event_id, source, detected_at) VALUES (%s,'local_quorum',%s)",
        (EVENT_ID, NOW),
    )
    c.execute("RESET ROLE")
    c.execute('SET ROLE "takab_ingest"')


def _incident_for_site(c: psycopg.Connection, site_id: str) -> dict | None:
    return c.execute(
        "SELECT incident_id, trigger, state, severity, event_id, opened_at "
        "FROM incidents WHERE site_id = %s AND event_id = %s",
        (site_id, EVENT_ID),
    ).fetchone()


def test_offline_in_range_opens_synthetic_incident(dconn: psycopg.Connection) -> None:
    _seed(dconn)
    created = handle_fail_open(dconn, EVENT_ID, [SITE_MEMBER], EPICENTER, PARAMS, now=NOW)
    assert len(created) == 1
    inc = _incident_for_site(dconn, SITE_OFF_IN)
    assert inc is not None
    assert str(inc["incident_id"]) == created[0]
    assert inc["trigger"] == "quorum"
    assert inc["state"] == "open"
    assert inc["severity"] == "warning"
    assert inc["event_id"] == EVENT_ID
    assert inc["opened_at"] == NOW
    # Traza fail_open en el timeline (fila lista para T-1.21).
    action = dconn.execute(
        "SELECT kind, actor FROM incident_actions WHERE incident_id = %s",
        (created[0],),
    ).fetchone()
    assert action["kind"] == "fail_open"
    assert action["actor"] == "system"


def test_offline_out_of_range_opens_nothing(dconn: psycopg.Connection) -> None:
    _seed(dconn)
    handle_fail_open(dconn, EVENT_ID, [SITE_MEMBER], EPICENTER, PARAMS, now=NOW)
    assert _incident_for_site(dconn, SITE_OFF_OUT) is None


def test_online_site_opens_nothing(dconn: psycopg.Connection) -> None:
    _seed(dconn)
    handle_fail_open(dconn, EVENT_ID, [SITE_MEMBER], EPICENTER, PARAMS, now=NOW)
    assert _incident_for_site(dconn, SITE_ONLINE) is None


def test_member_site_excluded(dconn: psycopg.Connection) -> None:
    _seed(dconn)
    handle_fail_open(dconn, EVENT_ID, [SITE_MEMBER], EPICENTER, PARAMS, now=NOW)
    assert _incident_for_site(dconn, SITE_MEMBER) is None


def test_site_without_gateway_excluded(dconn: psycopg.Connection) -> None:
    _seed(dconn)
    handle_fail_open(dconn, EVENT_ID, [SITE_MEMBER], EPICENTER, PARAMS, now=NOW)
    assert _incident_for_site(dconn, SITE_NO_GW) is None


def test_only_the_offline_in_range_site_qualifies(dconn: psycopg.Connection) -> None:
    _seed(dconn)
    created = handle_fail_open(dconn, EVENT_ID, [SITE_MEMBER], EPICENTER, PARAMS, now=NOW)
    sites = {
        str(r["site_id"])
        for r in dconn.execute(
            "SELECT site_id FROM incidents WHERE event_id = %s", (EVENT_ID,)
        ).fetchall()
    }
    assert sites == {SITE_OFF_IN}
    assert len(created) == 1


def test_empty_members_still_opens_for_offline_site(dconn: psycopg.Connection) -> None:
    _seed(dconn)
    # Sin miembros: el sitio offline en rango sigue calificando (cast uuid[] vacío ok).
    created = handle_fail_open(dconn, EVENT_ID, [], EPICENTER, PARAMS, now=NOW)
    assert _incident_for_site(dconn, SITE_OFF_IN) is not None
    # El sitio "member" ahora también califica (offline en rango, no excluido).
    assert _incident_for_site(dconn, SITE_MEMBER) is not None
    assert len(created) == 2


def test_rerun_is_idempotent(dconn: psycopg.Connection) -> None:
    _seed(dconn)
    first = handle_fail_open(dconn, EVENT_ID, [SITE_MEMBER], EPICENTER, PARAMS, now=NOW)
    second = handle_fail_open(dconn, EVENT_ID, [SITE_MEMBER], EPICENTER, PARAMS, now=NOW)
    assert len(first) == 1
    assert second == []
    count = dconn.execute(
        "SELECT count(*) AS n FROM incidents WHERE site_id = %s AND event_id = %s",
        (SITE_OFF_IN, EVENT_ID),
    ).fetchone()["n"]
    assert count == 1
    # La acción fail_open tampoco se duplica.
    acts = dconn.execute(
        "SELECT count(*) AS n FROM incident_actions WHERE incident_id = %s",
        (first[0],),
    ).fetchone()["n"]
    assert acts == 1


def test_existing_incident_for_event_is_not_duplicated(dconn: psycopg.Connection) -> None:
    _seed(dconn)
    # Ya existe un incidente real ligado al evento para el sitio offline en rango.
    dconn.execute(
        "INSERT INTO incidents (event_uuid, tenant_id, site_id, event_id, opened_at, "
        "severity, state, trigger) VALUES "
        "(gen_random_uuid(), %s, %s, %s, %s, 'critical', 'open', 'local_threshold')",
        (TENANT, SITE_OFF_IN, EVENT_ID, NOW),
    )
    created = handle_fail_open(dconn, EVENT_ID, [SITE_MEMBER], EPICENTER, PARAMS, now=NOW)
    assert created == []


def test_signal_emitted_per_created_incident(
    dconn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(dconn)
    calls: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        fo,
        "_emit_failopen_signal",
        lambda conn, event_id, site_id, incident_id: calls.append((event_id, site_id, incident_id)),
    )
    created = handle_fail_open(dconn, EVENT_ID, [SITE_MEMBER], EPICENTER, PARAMS, now=NOW)
    assert len(calls) == 1
    assert calls[0][0] == EVENT_ID
    assert calls[0][1] == SITE_OFF_IN
    assert calls[0][2] == created[0]


def test_reach_is_capped_against_abusive_window(dconn: psycopg.Connection) -> None:
    """Una ``max_window_s`` absurda (1000 s → alcance sin tope ~6500 km) NO debe
    abrir incidentes sintéticos en sitios lejanos de otros tenants: el radio se
    acota al tope físico (~400 km) (#7)."""
    _seed(dconn)
    abusive = QuorumParams(min_nodes=3, v_p_km_s=6.5, margin_s=3.0, max_window_s=1000.0)
    handle_fail_open(dconn, EVENT_ID, [SITE_MEMBER], EPICENTER, abusive, now=NOW)
    # El sitio a ~635 km queda FUERA del tope pese a la ventana absurda...
    assert _incident_for_site(dconn, SITE_OFF_OUT) is None
    # ...y el sitio en el epicentro sí se cubre (la cobertura cercana no se pierde).
    assert _incident_for_site(dconn, SITE_OFF_IN) is not None


def test_emit_failopen_signal_reaches_channel() -> None:
    """La señal real llega al canal ``takab_failopen`` (seam de T-1.21)."""
    c = psycopg.connect(_dsn(), autocommit=True, row_factory=dict_row)
    try:
        c.execute(f"LISTEN {fo.FAILOPEN_CHANNEL}")
        fo._emit_failopen_signal(c, "EVT-X", "site-x", "inc-x")
        notifs = list(c.notifies(timeout=2.0, stop_after=1))
        assert len(notifs) == 1
        assert notifs[0].channel == fo.FAILOPEN_CHANNEL
        import json

        payload = json.loads(notifs[0].payload)
        assert payload == {"event_id": "EVT-X", "site_id": "site-x", "incident_id": "inc-x"}
    finally:
        c.close()
