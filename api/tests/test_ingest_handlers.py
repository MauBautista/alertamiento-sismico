"""Handlers de ingesta (T-1.17, fase B): mapeos, idempotencia, escalada, identidad.

Flota mínima de la convención dev creada con SQL directo (UUIDs alineados a
db/seeds/prod_fleet.sql + sim_fleet.sql); los handlers corren como takab_ingest (BYPASSRLS),
igual que el worker real.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime

import psycopg
import pytest

from conftest import use
from takab_api.contracts.meta import Meta
from takab_api.ingest.handlers import (
    ACK_KIND,
    GatewayCtx,
    Outcome,
    SensorRef,
    check_identity,
    handle_actuator_ack,
    handle_feature_1s,
    handle_health_snapshot,
    handle_local_event,
    handle_status,
)

# UUIDs fijos de la familia del seed (db/seeds/prod_fleet.sql + sim_fleet.sql, sufijo 00 = dev).
TENANT = "d0000000-0000-0000-0000-000000000001"
SITE = "d1000000-0000-0000-0000-000000000000"
GW = "d2000000-0000-0000-0000-000000000000"
SENSOR = "d3000000-0000-0000-0000-000000000000"
# Segundo sitio/sensor atendido por el MISMO gateway (patrón de los gateways sim).
SITE_B = "d1000000-0000-0000-0000-0000000000b2"
SENSOR_B = "d3000000-0000-0000-0000-0000000000b2"

EVENT_HEX = "3f2504e04f8941d39a0c0305e82c3301"
TS_EVENT = "2026-07-06T10:00:01+00:00"
TS_IOT = datetime(2026, 7, 6, 10, 0, 5, tzinfo=UTC)


@pytest.fixture
def fleet(conn: psycopg.Connection) -> psycopg.Connection:
    """tenant-dev / site-dev / gw-dev-0001 / R4F74 según la convención fija."""
    conn.execute("RESET ROLE")
    conn.execute(
        "INSERT INTO tenants (tenant_id, code, name) VALUES (%s, 'tenant-dev', 'TAKAB Dev') "
        "ON CONFLICT DO NOTHING",
        (TENANT,),
    )
    conn.execute(
        "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
        "(%s, %s, 'site-dev', 'Sitio Dev', "
        "ST_SetSRID(ST_MakePoint(-98.2063, 19.0414), 4326)::geography) "
        "ON CONFLICT DO NOTHING",
        (SITE, TENANT),
    )
    conn.execute(
        "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, iot_thing) VALUES "
        "(%s, %s, %s, 'gw-dev-0001', 'gw-dev-0001') ON CONFLICT DO NOTHING",
        (GW, TENANT, SITE),
    )
    conn.execute(
        "INSERT INTO sensors (sensor_id, tenant_id, site_id, gateway_id, kind, model, serial) "
        "VALUES (%s, %s, %s, %s, 'structural', 'RS4D', 'R4F74') ON CONFLICT DO NOTHING",
        (SENSOR, TENANT, SITE, GW),
    )
    use(conn, "takab_ingest")  # el rol real del worker
    return conn


@pytest.fixture
def fleet_multi(fleet: psycopg.Connection) -> psycopg.Connection:
    """El mismo gateway atiende un SEGUNDO sitio vía su sensor (como los sim)."""
    fleet.execute("RESET ROLE")
    fleet.execute(
        "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
        "(%s, %s, 'site-b', 'Sitio B', "
        "ST_SetSRID(ST_MakePoint(-98.2200, 19.0500), 4326)::geography) "
        "ON CONFLICT DO NOTHING",
        (SITE_B, TENANT),
    )
    fleet.execute(
        "INSERT INTO sensors (sensor_id, tenant_id, site_id, gateway_id, kind, model, serial) "
        "VALUES (%s, %s, %s, %s, 'structural', 'RS4D', 'SIMB02') ON CONFLICT DO NOTHING",
        (SENSOR_B, TENANT, SITE_B, GW),
    )
    use(fleet, "takab_ingest")
    return fleet


@pytest.fixture
def ctx() -> GatewayCtx:
    return GatewayCtx(
        gateway_id=uuid.UUID(GW),
        gateway_serial="gw-dev-0001",
        iot_thing="gw-dev-0001",
        tenant_id=uuid.UUID(TENANT),
        tenant_code="tenant-dev",
        site_id=uuid.UUID(SITE),
        site_code="site-dev",
        sensors={
            "R4F74": SensorRef(
                sensor_id=uuid.UUID(SENSOR), site_id=uuid.UUID(SITE), site_code="site-dev"
            )
        },
    )


@pytest.fixture
def ctx_multi(ctx: GatewayCtx) -> GatewayCtx:
    """ctx del mismo gateway con el sensor del segundo sitio (multi-sitio)."""
    return replace(
        ctx,
        sensors={
            **ctx.sensors,
            "SIMB02": SensorRef(
                sensor_id=uuid.UUID(SENSOR_B), site_id=uuid.UUID(SITE_B), site_code="site-b"
            ),
        },
    )


@pytest.fixture
def meta() -> Meta:
    return Meta(principal="gw-dev-0001", topic="takab/test", ts_iot=TS_IOT)


def _feature(**over: object) -> dict:
    base = {
        "station": "R4F74",
        "channel": "ENZ",
        "window_start": "2026-07-06T10:00:00+00:00",
        "pga": 0.012,
        "pgv": 0.34,
        "rms": 1.5,
        "sta_lta": 2.1,
        "clipping": True,
        "health_score": 0.9,
    }
    base.update(over)
    return base


def _event(**over: object) -> dict:
    base = {
        "event_id": EVENT_HEX,
        "tenant_id": "tenant-dev",
        "site_id": "site-dev",
        "source": "local_threshold",
        "tier": "watch",
        "created_at": TS_EVENT,
    }
    base.update(over)
    return base


def _health(**over: object) -> dict:
    base = {
        "gateway_id": "gw-dev-0001",
        "captured_at": "2026-07-06T10:00:03+00:00",
        "ntp_offset_s": 0.123,
        "seedlink_lag_s": 0.4,
        "packet_loss_pct": 1.5,
        "ups_status": "battery",
        "battery_pct": 87.5,
        "temperature_c": 51.2,
        "cert_days_remaining": 300,
        "relays": [],
        "transition_reason": "ups_to_battery",
    }
    base.update(over)
    return base


def _ack(**over: object) -> dict:
    base = {
        "channel": "siren",
        "action": "activate",
        "event_id": EVENT_HEX,
        "success": True,
        "latency_s": 0.42,
        "executed_at": "2026-07-06T10:00:02.420000+00:00",
        "detail": "",
    }
    base.update(over)
    return base


def _count(conn: psycopg.Connection, sql: str, params: tuple = ()) -> int:
    return conn.execute(sql, params).fetchone()[0]


def _audit_rejects(conn: psycopg.Connection) -> int:
    return _count(conn, "SELECT count(*) FROM audit_log WHERE verb = 'ingest_reject'")


# --------------------------------------------------------------------------
# feature_1s
# --------------------------------------------------------------------------


def test_feature_happy_path_maps_columns(fleet, ctx, meta) -> None:
    assert handle_feature_1s(fleet, _feature(), meta, ctx).is_ok
    row = fleet.execute(
        "SELECT ts, tenant_id, site_id, sensor_id, channel, pga_g, pgv_cms, rms, stalta, "
        "clipping FROM waveform_features_1s WHERE sensor_id = %s",
        (SENSOR,),
    ).fetchone()
    assert row[0] == datetime(2026, 7, 6, 10, 0, 0, tzinfo=UTC)  # window_start → ts
    assert (str(row[1]), str(row[2]), str(row[3])) == (TENANT, SITE, SENSOR)  # del ctx
    assert row[4] == "ENZ"
    assert row[5] == pytest.approx(0.012)  # pga (g) → pga_g
    assert row[6] == pytest.approx(0.34)  # pgv (cm/s) → pgv_cms
    assert row[7] == pytest.approx(1.5)
    assert row[8] == pytest.approx(2.1)  # sta_lta → stalta
    assert row[9] is True


def test_feature_double_run_is_idempotent(fleet, ctx, meta) -> None:
    assert handle_feature_1s(fleet, _feature(), meta, ctx).is_ok
    assert handle_feature_1s(fleet, _feature(), meta, ctx).is_ok
    assert _count(fleet, "SELECT count(*) FROM waveform_features_1s") == 1


def test_feature_unknown_station_rejected_and_audited(fleet, ctx, meta) -> None:
    res = handle_feature_1s(fleet, _feature(station="SIM099"), meta, ctx)
    assert res.outcome is Outcome.REJECT
    assert "station" in res.reason
    assert _count(fleet, "SELECT count(*) FROM waveform_features_1s") == 0
    assert _audit_rejects(fleet) == 1


def test_feature_attributed_to_sensor_site_not_gateway_site(fleet_multi, ctx_multi, meta) -> None:
    """Gateway multi-sitio: la fila lleva el sitio del SENSOR, no el del gateway."""
    assert handle_feature_1s(fleet_multi, _feature(station="SIMB02"), meta, ctx_multi).is_ok
    row = fleet_multi.execute(
        "SELECT site_id, sensor_id FROM waveform_features_1s WHERE sensor_id = %s",
        (SENSOR_B,),
    ).fetchone()
    assert (str(row[0]), str(row[1])) == (SITE_B, SENSOR_B)  # NO el sitio del gateway


# --------------------------------------------------------------------------
# local_event → incidents
# --------------------------------------------------------------------------


def test_event_happy_path_creates_open_incident(fleet, ctx, meta) -> None:
    assert handle_local_event(fleet, _event(), meta, ctx).is_ok
    row = fleet.execute(
        "SELECT tenant_id, site_id, opened_at, severity, state, trigger, summary "
        "FROM incidents WHERE event_uuid = %s",
        (uuid.UUID(EVENT_HEX),),
    ).fetchone()
    assert (str(row[0]), str(row[1])) == (TENANT, SITE)
    assert row[2] == datetime.fromisoformat(TS_EVENT)  # created_at → opened_at
    assert (row[3], row[4], row[5]) == ("watch", "open", "local_threshold")
    assert row[6]["tier"] == "watch"


def test_event_double_run_is_idempotent(fleet, ctx, meta) -> None:
    assert handle_local_event(fleet, _event(), meta, ctx).is_ok
    assert handle_local_event(fleet, _event(), meta, ctx).is_ok
    assert _count(fleet, "SELECT count(*) FROM incidents") == 1
    sev = fleet.execute("SELECT severity FROM incidents").fetchone()[0]
    assert sev == "watch"


def test_event_escalates_but_never_degrades(fleet, ctx, meta) -> None:
    assert handle_local_event(fleet, _event(tier="watch"), meta, ctx).is_ok
    # escalada watch→evacuate_or_hold (sasmex): severity watch→critical
    assert handle_local_event(
        fleet, _event(tier="evacuate_or_hold", source="sasmex"), meta, ctx
    ).is_ok
    row = fleet.execute("SELECT severity, trigger, summary FROM incidents").fetchone()
    assert (row[0], row[1], row[2]["tier"]) == ("critical", "sasmex", "evacuate_or_hold")
    # degradación: volver a mandar watch NO baja severity ni tier
    assert handle_local_event(fleet, _event(tier="watch"), meta, ctx).is_ok
    row = fleet.execute("SELECT severity, trigger, summary FROM incidents").fetchone()
    assert (row[0], row[1], row[2]["tier"]) == ("critical", "sasmex", "evacuate_or_hold")
    assert _count(fleet, "SELECT count(*) FROM incidents") == 1


def test_event_same_severity_higher_tier_updates_summary(fleet, ctx, meta) -> None:
    # evacuate_or_hold y manual_only comparten severity 'critical': el tier
    # mayor por RANK actualiza summary aunque la severity empate.
    assert handle_local_event(fleet, _event(tier="evacuate_or_hold"), meta, ctx).is_ok
    assert handle_local_event(fleet, _event(tier="manual_only", source="manual"), meta, ctx).is_ok
    row = fleet.execute("SELECT severity, summary FROM incidents").fetchone()
    assert (row[0], row[1]["tier"]) == ("critical", "manual_only")


def test_event_bad_event_id_rejected(fleet, ctx, meta) -> None:
    res = handle_local_event(fleet, _event(event_id="no-es-hex"), meta, ctx)
    assert res.outcome is Outcome.REJECT
    assert _count(fleet, "SELECT count(*) FROM incidents") == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [("tenant_id", "tenant-evil"), ("site_id", "site-evil")],
)
def test_event_identity_mismatch_rejected_and_audited(fleet, ctx, meta, field, value) -> None:
    res = handle_local_event(fleet, _event(**{field: value}), meta, ctx)
    assert res.outcome is Outcome.REJECT
    assert field.split("_")[0] in res.reason  # razón específica (tenant/site)
    assert _count(fleet, "SELECT count(*) FROM incidents") == 0
    assert _audit_rejects(fleet) == 1


def test_event_of_secondary_served_site_accepted_and_attributed(fleet_multi, ctx_multi, meta):
    """Un evento de OTRO sitio atendido por el gateway (convención sim: 5 sitios
    por gateway) NO es mismatch y el incidente se atribuye a ESE sitio."""
    assert handle_local_event(fleet_multi, _event(site_id="site-b"), meta, ctx_multi).is_ok
    row = fleet_multi.execute(
        "SELECT site_id FROM incidents WHERE event_uuid = %s", (uuid.UUID(EVENT_HEX),)
    ).fetchone()
    assert str(row[0]) == SITE_B  # el sitio del evento, no el del gateway
    assert _audit_rejects(fleet_multi) == 0


# --------------------------------------------------------------------------
# health_snapshot → device_health
# --------------------------------------------------------------------------


def test_health_happy_path_converts_units(fleet, ctx, meta) -> None:
    assert handle_health_snapshot(fleet, _health(mqtt_rtt_ms=42.5), meta, ctx).is_ok
    row = fleet.execute(
        "SELECT ts, tenant_id, gateway_id, reason, seedlink_lag_s, ntp_offset_ms, cpu_temp_c, "
        "power_status, battery_pct, cert_days_remaining, mqtt_rtt_ms, battery_min_left "
        "FROM device_health WHERE gateway_id = %s",
        (GW,),
    ).fetchone()
    assert row[0] == datetime(2026, 7, 6, 10, 0, 3, tzinfo=UTC)  # captured_at → ts
    assert (str(row[1]), str(row[2])) == (TENANT, GW)
    assert row[3] == "transition"  # transition_reason != 'heartbeat'
    assert row[4] == pytest.approx(0.4)
    assert row[5] == pytest.approx(123.0)  # 0.123 s → 123 ms
    assert row[6] == pytest.approx(51.2)  # temperature_c → cpu_temp_c
    assert row[7] == "battery"  # ups_status → power_status
    assert row[8] == pytest.approx(87.5)
    assert row[9] == 300
    assert row[10] == pytest.approx(42.5)  # RTT del PUBACK real (T-1.40)
    assert row[11] is None  # battery_min_left sigue sin fuente edge → NULL


def test_health_honest_none_fields_persist_as_null(fleet, ctx, meta) -> None:
    """Contrato honesto (T-1.40): «sin dato» viaja como None y aterriza NULL —
    nunca se rellena con un default optimista en la ingesta."""
    payload = _health(
        ntp_offset_s=None, battery_pct=None, cert_days_remaining=None, ups_status="unknown"
    )
    assert handle_health_snapshot(fleet, payload, meta, ctx).is_ok
    row = fleet.execute(
        "SELECT ntp_offset_ms, mqtt_rtt_ms, battery_pct, cert_days_remaining, power_status "
        "FROM device_health WHERE gateway_id = %s",
        (GW,),
    ).fetchone()
    assert row[0] is None and row[1] is None and row[2] is None and row[3] is None
    assert row[4] == "unknown"


def test_health_default_reason_is_heartbeat(fleet, ctx, meta) -> None:
    payload = _health()
    del payload["transition_reason"]
    assert handle_health_snapshot(fleet, payload, meta, ctx).is_ok
    assert fleet.execute("SELECT reason FROM device_health").fetchone()[0] == "heartbeat"


def test_health_double_run_is_idempotent(fleet, ctx, meta) -> None:
    assert handle_health_snapshot(fleet, _health(), meta, ctx).is_ok
    assert handle_health_snapshot(fleet, _health(), meta, ctx).is_ok
    assert _count(fleet, "SELECT count(*) FROM device_health") == 1


def test_health_gateway_mismatch_rejected_and_audited(fleet, ctx, meta) -> None:
    res = handle_health_snapshot(fleet, _health(gateway_id="gw-evil"), meta, ctx)
    assert res.outcome is Outcome.REJECT
    assert "gateway" in res.reason
    assert _count(fleet, "SELECT count(*) FROM device_health") == 0
    assert _audit_rejects(fleet) == 1


# --------------------------------------------------------------------------
# actuator_ack → incident_actions
# --------------------------------------------------------------------------


def test_ack_without_incident_retries(fleet, ctx, meta) -> None:
    res = handle_actuator_ack(fleet, _ack(), meta, ctx)
    assert res.outcome is Outcome.RETRY
    assert _count(fleet, "SELECT count(*) FROM incident_actions") == 0


def test_ack_with_incident_ok_and_mapped(fleet, ctx, meta) -> None:
    assert handle_local_event(fleet, _event(), meta, ctx).is_ok
    assert handle_actuator_ack(fleet, _ack(), meta, ctx).is_ok
    row = fleet.execute(
        "SELECT a.ts, a.kind, a.actor, a.payload, a.tenant_id FROM incident_actions a "
        "JOIN incidents i ON i.incident_id = a.incident_id WHERE i.event_uuid = %s",
        (uuid.UUID(EVENT_HEX),),
    ).fetchone()
    assert row[0] == datetime(2026, 7, 6, 10, 0, 2, 420000, tzinfo=UTC)  # executed_at → ts
    assert row[1] == "siren_on"  # (siren, activate) → kind
    assert row[2] == "edge:gw-dev-0001"
    assert row[3]["success"] is True and row[3]["latency_s"] == pytest.approx(0.42)
    assert str(row[4]) == TENANT


def test_ack_double_run_is_idempotent(fleet, ctx, meta) -> None:
    assert handle_local_event(fleet, _event(), meta, ctx).is_ok
    assert handle_actuator_ack(fleet, _ack(), meta, ctx).is_ok
    assert handle_actuator_ack(fleet, _ack(), meta, ctx).is_ok
    assert _count(fleet, "SELECT count(*) FROM incident_actions") == 1


def test_ack_gas_valve_kind_map(fleet, ctx, meta) -> None:
    assert handle_local_event(fleet, _event(), meta, ctx).is_ok
    assert handle_actuator_ack(fleet, _ack(channel="gas_valve"), meta, ctx).is_ok
    assert (
        fleet.execute(
            "SELECT kind FROM incident_actions WHERE payload->>'channel' = 'gas_valve'"
        ).fetchone()[0]
        == "gas_closed"
    )


def test_ack_incident_of_other_tenant_rejected(fleet, ctx, meta) -> None:
    # incidente con el mismo event_uuid pero de OTRO tenant → REJECT, no cruza
    other_tenant = "d0000000-0000-0000-0000-0000000000ff"
    other_site = "d1000000-0000-0000-0000-0000000000ff"
    fleet.execute("RESET ROLE")
    fleet.execute(
        "INSERT INTO tenants (tenant_id, code, name) VALUES (%s, 'tenant-x', 'X')",
        (other_tenant,),
    )
    fleet.execute(
        "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES (%s, %s, 'site-x', "
        "'X', ST_SetSRID(ST_MakePoint(0, 0), 4326)::geography)",
        (other_site, other_tenant),
    )
    fleet.execute(
        "INSERT INTO incidents (event_uuid, tenant_id, site_id, opened_at, severity, trigger) "
        "VALUES (%s, %s, %s, now(), 'watch', 'manual')",
        (uuid.UUID(EVENT_HEX), other_tenant, other_site),
    )
    use(fleet, "takab_ingest")
    res = handle_actuator_ack(fleet, _ack(), meta, ctx)
    assert res.outcome is Outcome.REJECT
    assert _count(fleet, "SELECT count(*) FROM incident_actions") == 0
    assert _audit_rejects(fleet) == 1


# --------------------------------------------------------------------------
# status (LWT) → gateways.status + device_health
# --------------------------------------------------------------------------


def _gw_status(conn: psycopg.Connection) -> str:
    return conn.execute("SELECT status FROM gateways WHERE gateway_id = %s", (GW,)).fetchone()[0]


def test_status_offline_then_online_updates_gateway(fleet, ctx) -> None:
    meta_1 = Meta(principal="gw-dev-0001", topic="takab/status/gw-dev-0001", ts_iot=TS_IOT)
    meta_2 = Meta(
        principal="gw-dev-0001",
        topic="takab/status/gw-dev-0001",
        ts_iot=datetime(2026, 7, 6, 10, 0, 9, tzinfo=UTC),
    )
    assert handle_status(fleet, {"status": "offline"}, meta_1, ctx).is_ok
    assert _gw_status(fleet) == "offline"
    assert handle_status(fleet, {"status": "online"}, meta_2, ctx).is_ok
    assert _gw_status(fleet) == "online"
    # cada transición deja su fila en device_health con ts = meta_ts_iot
    rows = fleet.execute(
        "SELECT ts, reason FROM device_health WHERE gateway_id = %s ORDER BY ts", (GW,)
    ).fetchall()
    assert [(r[0], r[1]) for r in rows] == [
        (TS_IOT, "transition"),
        (datetime(2026, 7, 6, 10, 0, 9, tzinfo=UTC), "transition"),
    ]


def test_status_same_lwt_redelivered_is_idempotent(fleet, ctx, meta) -> None:
    assert handle_status(fleet, {"status": "online"}, meta, ctx).is_ok
    assert handle_status(fleet, {"status": "online"}, meta, ctx).is_ok
    assert _count(fleet, "SELECT count(*) FROM device_health") == 1


def test_status_stale_message_does_not_regress_gateway_status(fleet, ctx) -> None:
    """SQS standard reordena/reentrega: un mensaje de presencia VIEJO procesado
    después de uno más nuevo NO pisa gateways.status (guarda monotónica por
    meta_ts_iot); uno más nuevo sí lo actualiza."""

    def _meta(second: int) -> Meta:
        return Meta(
            principal="gw-dev-0001",
            topic="takab/status/gw-dev-0001",
            ts_iot=datetime(2026, 7, 6, 10, 0, second, tzinfo=UTC),
        )

    assert handle_status(fleet, {"status": "offline"}, _meta(9), ctx).is_ok  # LWT nuevo
    assert handle_status(fleet, {"status": "online"}, _meta(5), ctx).is_ok  # beacon viejo
    assert _gw_status(fleet) == "offline"  # el gabinete muerto NO aparece vivo
    assert handle_status(fleet, {"status": "online"}, _meta(11), ctx).is_ok  # más nuevo
    assert _gw_status(fleet) == "online"


# --------------------------------------------------------------------------
# check_identity puro (sin DB)
# --------------------------------------------------------------------------


def test_check_identity_ok_for_all_kinds(ctx) -> None:
    assert check_identity(_event(), ctx, "local_event") is None
    assert check_identity(_feature(), ctx, "feature_1s") is None
    assert check_identity(_health(), ctx, "health_snapshot") is None
    assert check_identity(_ack(), ctx, "actuator_ack") is None
    assert check_identity({"status": "online"}, ctx, "status") is None


def test_check_identity_accepts_all_served_sites(ctx_multi) -> None:
    """El site del payload se valida contra TODOS los sitios atendidos (vía
    sensores), no solo contra gateways.site_id."""
    assert check_identity(_event(site_id="site-dev"), ctx_multi, "local_event") is None
    assert check_identity(_event(site_id="site-b"), ctx_multi, "local_event") is None
    mismatch = check_identity(_event(site_id="site-evil"), ctx_multi, "local_event")
    assert mismatch is not None and "site" in mismatch


def test_ack_kind_map_covers_all_channel_action_pairs() -> None:
    channels = {"siren", "strobe", "gas_valve", "elevator", "door_retainer"}
    actions = {"activate", "deactivate"}
    assert set(ACK_KIND) == {(c, a) for c in channels for a in actions}
