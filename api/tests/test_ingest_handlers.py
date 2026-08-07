"""Handlers de ingesta (T-1.17, fase B): mapeos, idempotencia, escalada, identidad.

Flota mínima de la convención dev creada con SQL directo (UUIDs alineados a
db/seeds/prod_fleet.sql + sim_fleet.sql); los handlers corren como takab_ingest (BYPASSRLS),
igual que el worker real.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta

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
    handle_feature_batch,
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
# feature_batch → N × waveform_features_1s (T-1.56)
# --------------------------------------------------------------------------


def _batch(features: list[dict], **over: object) -> dict:
    base = {
        "gateway_id": "gw-dev-0001",
        "features": features,
        "batched_at": "2026-07-06T10:00:10+00:00",
    }
    base.update(over)
    return base


def _three_features() -> list[dict]:
    return [
        _feature(window_start=f"2026-07-06T10:00:0{i}+00:00", channel=ch)
        for i, ch in ((0, "ENZ"), (1, "ENZ"), (1, "EHZ"))
    ]


def test_batch_inserta_n_filas_en_la_misma_transaccion(fleet, ctx, meta) -> None:
    assert handle_feature_batch(fleet, _batch(_three_features()), meta, ctx).is_ok
    assert _count(fleet, "SELECT count(*) FROM waveform_features_1s") == 3


def test_batch_reentrega_identica_cero_duplicados(fleet, ctx, meta) -> None:
    """SQS at-least-once / QoS1: el MISMO lote dos veces ⇒ N filas, no 2N."""
    payload = _batch(_three_features())
    assert handle_feature_batch(fleet, payload, meta, ctx).is_ok
    assert handle_feature_batch(fleet, payload, meta, ctx).is_ok
    assert _count(fleet, "SELECT count(*) FROM waveform_features_1s") == 3


def test_batch_gateway_mismatch_rechaza_y_audita(fleet, ctx, meta) -> None:
    res = handle_feature_batch(fleet, _batch(_three_features(), gateway_id="gw-x"), meta, ctx)
    assert res.outcome is Outcome.REJECT
    assert "gateway mismatch" in res.reason
    assert _count(fleet, "SELECT count(*) FROM waveform_features_1s") == 0
    assert _audit_rejects(fleet) == 1


def test_batch_parcialmente_invalido_inserta_validas_y_rechaza(fleet, ctx, meta) -> None:
    """1 station desconocida entre 3: las 2 buenas SE ESCRIBEN (el consumer
    commitea en REJECT con handler_ran=True) y el original va a DLQ con razón."""
    features = _three_features()
    features[1]["station"] = "SIM099"
    res = handle_feature_batch(fleet, _batch(features), meta, ctx)
    assert res.outcome is Outcome.REJECT
    assert "1/3" in res.reason and "SIM099" in res.reason
    assert _count(fleet, "SELECT count(*) FROM waveform_features_1s") == 2
    assert _audit_rejects(fleet) == 1


def test_batch_atribuye_cada_feature_al_sitio_de_su_sensor(fleet_multi, ctx_multi, meta) -> None:
    features = [
        _feature(window_start="2026-07-06T10:00:00+00:00"),
        _feature(window_start="2026-07-06T10:00:00+00:00", station="SIMB02"),
    ]
    assert handle_feature_batch(fleet_multi, _batch(features), meta, ctx_multi).is_ok
    rows = fleet_multi.execute(
        "SELECT sensor_id::text, site_id::text FROM waveform_features_1s ORDER BY sensor_id"
    ).fetchall()
    assert sorted(rows) == sorted([(SENSOR, SITE), (SENSOR_B, SITE_B)])


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
    payload = _health(mqtt_rtt_ms=42.5, ups_runtime_s=4500.0)  # 75 min de autonomía
    assert handle_health_snapshot(fleet, payload, meta, ctx).is_ok
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
    assert row[11] == 75  # ups_runtime_s 4500 s → battery_min_left 75 min (T-2.22)


def test_health_honest_none_fields_persist_as_null(fleet, ctx, meta) -> None:
    """Contrato honesto (T-1.40): «sin dato» viaja como None y aterriza NULL —
    nunca se rellena con un default optimista en la ingesta."""
    payload = _health(
        ntp_offset_s=None, battery_pct=None, cert_days_remaining=None, ups_status="unknown"
    )
    assert handle_health_snapshot(fleet, payload, meta, ctx).is_ok
    row = fleet.execute(
        "SELECT ntp_offset_ms, mqtt_rtt_ms, battery_pct, cert_days_remaining, power_status, "
        "battery_min_left FROM device_health WHERE gateway_id = %s",
        (GW,),
    ).fetchone()
    assert row[0] is None and row[1] is None and row[2] is None and row[3] is None
    assert row[4] == "unknown"
    # T-2.22 aditivo: un payload 1.6.0 SIN `ups_runtime_s` sigue aterrizando NULL.
    assert row[5] is None


def test_health_default_reason_is_heartbeat(fleet, ctx, meta) -> None:
    payload = _health()
    del payload["transition_reason"]
    assert handle_health_snapshot(fleet, payload, meta, ctx).is_ok
    assert fleet.execute("SELECT reason FROM device_health").fetchone()[0] == "heartbeat"


def test_health_double_run_is_idempotent(fleet, ctx, meta) -> None:
    assert handle_health_snapshot(fleet, _health(), meta, ctx).is_ok
    assert handle_health_snapshot(fleet, _health(), meta, ctx).is_ok
    assert _count(fleet, "SELECT count(*) FROM device_health") == 1


def _fw(fleet) -> str | None:
    return fleet.execute("SELECT fw_version FROM gateways WHERE gateway_id = %s", (GW,)).fetchone()[
        0
    ]


def test_health_persiste_la_version_que_declara_el_gabinete(fleet, ctx, meta) -> None:
    """`gateways.fw_version` se llenaba A MANO y se habría quedado obsoleto en el
    siguiente despliegue. Ahora lo declara el propio gabinete en su heartbeat."""
    assert handle_health_snapshot(fleet, _health(fw_version="737dd73"), meta, ctx).is_ok
    assert _fw(fleet) == "737dd73"


def test_health_actualiza_la_version_al_desplegar(fleet, ctx, meta) -> None:
    assert handle_health_snapshot(fleet, _health(fw_version="737dd73"), meta, ctx).is_ok
    payload = _health(fw_version="86ea606")
    payload["captured_at"] = "2026-07-06T10:01:03+00:00"  # otro ts: fila nueva
    assert handle_health_snapshot(fleet, payload, meta, ctx).is_ok
    assert _fw(fleet) == "86ea606"


def test_health_sin_la_clave_no_pisa_la_conocida(fleet, ctx, meta) -> None:
    """CLAVE AUSENTE = «no opino» (contrato pre-1.6.0, que ni siquiera conoce el
    campo). Un edge que no sabe hablar de versiones no puede dejar en blanco la
    ficha de la flota — eso sería castigar a la nube por la vejez del gabinete.

    [T-2.69] Este test y el siguiente eran UNO SOLO, y su docstring justificaba a
    la vez «contrato viejo» y «deploy sin marcar» — dos hechos que el código no
    sabía separar. Se parten a propósito: las expectativas son OPUESTAS.
    """
    assert handle_health_snapshot(fleet, _health(fw_version="737dd73"), meta, ctx).is_ok
    payload = _health()  # sin la clave: contrato viejo
    payload["captured_at"] = "2026-07-06T10:02:03+00:00"
    assert handle_health_snapshot(fleet, payload, meta, ctx).is_ok
    assert _fw(fleet) == "737dd73"


def test_health_con_null_explicito_la_version_pasa_a_sin_dato(fleet, ctx, meta) -> None:
    """NULL EXPLÍCITO = «late y declara que NO SABE qué versión corre».

    Es un HECHO NUEVO, no un silencio: pasa cuando un ``rsync --delete`` a medias,
    un reaprovisionamiento o un archivo ilegible se lleva el ``FW_VERSION`` del
    gabinete. Conservar el valor viejo dejaba `gateways.fw_version` congelado PARA
    SIEMPRE y la consola lo pintaba como actual — exactamente lo que el criterio 3
    de T-2.69 prohíbe por escrito.

    Se puede distinguir porque el edge publica con ``model_dump(mode='json')`` SIN
    ``exclude_none``: la clave viaja con ``null``. Lo protege
    ``edge/tests/test_cloud.py::test_el_heartbeat_publica_la_clave_fw_version_aunque_valga_null``.
    """
    assert handle_health_snapshot(fleet, _health(fw_version="737dd73"), meta, ctx).is_ok
    payload = _health(fw_version=None)  # la clave ESTÁ, y vale null
    payload["captured_at"] = "2026-07-06T10:02:03+00:00"
    assert handle_health_snapshot(fleet, payload, meta, ctx).is_ok
    assert _fw(fleet) is None


def test_health_version_absurda_se_rechaza_sin_tumbar_la_ingesta(fleet, ctx, meta) -> None:
    """El edge ya acota el valor, pero la ingesta no confía en el dispositivo:
    un payload manipulado no escribe basura en la ficha ni rompe el heartbeat."""
    assert handle_health_snapshot(fleet, _health(fw_version="x" * 200), meta, ctx).is_ok
    assert _fw(fleet) is None
    assert _count(fleet, "SELECT count(*) FROM device_health") == 1


def test_health_version_absurda_tampoco_borra_la_conocida(fleet, ctx, meta) -> None:
    """Basura ≠ «no sé». Un payload manipulado no puede BORRAR la versión buena de
    la ficha: eso convertiría el vandalismo en un botón de S/D remoto."""
    assert handle_health_snapshot(fleet, _health(fw_version="737dd73"), meta, ctx).is_ok
    payload = _health(fw_version="x" * 200)
    payload["captured_at"] = "2026-07-06T10:02:03+00:00"
    assert handle_health_snapshot(fleet, payload, meta, ctx).is_ok
    assert _fw(fleet) == "737dd73"


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
# [T-2.65 · B1] El retiro es un acto ADMINISTRATIVO: no lo deshace el aparato
# --------------------------------------------------------------------------


#: Origen de los ts de presencia; `_presencia(n)` es "n segundos después".
TS_PRESENCIA = datetime(2026, 8, 4, 10, 0, 0, tzinfo=UTC)


def _presencia(offset_s: int) -> Meta:
    """Meta de un mensaje del topic de presencia (`takab/status/<thing>`)."""
    return Meta(
        principal="gw-dev-0001",
        topic="takab/status/gw-dev-0001",
        ts_iot=TS_PRESENCIA + timedelta(seconds=offset_s),
    )


def _retire(conn: psycopg.Connection) -> None:
    """Lo que hace la consola al retirar (`queries/fleet.py::set_gateway_status`)."""
    conn.execute("RESET ROLE")
    conn.execute("UPDATE gateways SET status = 'retired' WHERE gateway_id = %s", (GW,))
    use(conn, "takab_ingest")


def _alive_while_retired(conn: psycopg.Connection) -> list[tuple]:
    return conn.execute(
        "SELECT actor, object, meta FROM audit_log "
        "WHERE verb = 'gateway_alive_while_retired' ORDER BY ts"
    ).fetchall()


def test_status_beacon_no_resucita_un_gabinete_retirado(fleet, ctx) -> None:
    """La cadena de 6 pasos que deshacía T-2.65 sola, sin que nadie restaurara.

    1. El operador retira `gw-dev-0001` desde la consola  → status='retired'.
    2. El sync publica el sobre con cloud_admin_state='retired' y el panel del
       gabinete pinta DADO DE BAJA.
    3. El gabinete SIGUE VIVO (premisa de la opción (A) ratificada el 2026-08-05)
       y su sesión MQTT flapea, cosa rutinaria.
    4. Al reconectar publica su beacon de presencia retenido `{"status":"online"}`
       (`edge/cloud/__init__.py::_publish_online`, uno por CONEXIÓN) → IoT Rule
       `takab/status/+` → SQS → aquí.  <-- ESTE es el único eslabón escribible.
    5. El trigger 0027 (`AFTER UPDATE OF status … OLD.status = 'retired'`) despierta
       al worker de config.
    6. El worker publica un sobre FIRMADO v+1 con cloud_admin_state='active' que
       APAGA el cartel del panel.

    Cerrado el paso 4, los pasos 5 y 6 son inalcanzables por construcción: el
    `WHEN` del trigger exige `OLD.status IS DISTINCT FROM NEW.status`, y si el
    beacon no mueve la columna no hay transición que notificar.
    """
    _retire(fleet)

    assert handle_status(fleet, {"status": "online"}, _presencia(30), ctx).is_ok

    assert _gw_status(fleet) == "retired", (
        "el beacon de presencia del propio gabinete deshizo el retiro de la consola: "
        "un mensaje del dispositivo revirtió un acto administrativo"
    )


def test_status_lwt_offline_tampoco_borra_el_retiro(fleet, ctx) -> None:
    """El otro lado del mismo `_STATUS_SQL`: el LWT lo publica el BROKER en cada
    desconexión sucia, así que es aún más frecuente que el beacon. Un gabinete
    retirado que se desconecta seguía cayendo a 'offline' — y con eso dejaba de
    ser fantasma para T-2.60.a y dejaba de ser candidato de aviso para T-2.65.
    """
    _retire(fleet)

    assert handle_status(fleet, {"status": "offline"}, _presencia(30), ctx).is_ok

    assert _gw_status(fleet) == "retired"


def test_status_de_retirado_deja_la_huella_de_que_sigue_vivo(fleet, ctx) -> None:
    """Ignorar el mensaje NO es callarlo: 'retirado + latiendo' es justo la señal
    que T-2.60.a y T-2.65 vigilan.

    Quedan DOS huellas y son distintas:
    - `device_health` (reason='transition'), que es de donde `ops/metrics.py::
      count_ghosts` y la consola sacan "la última vez que se le oyó";
    - una fila en la bitácora append-only por CADA reconexión de un gabinete
      retirado — evidencia de que un mensaje del aparato intentó revertir un acto
      de la consola. Solo el beacon 'online' la escribe: el LWT 'offline' no
      aporta nada sobre "sigue vivo" y duplicaría el volumen en cada flap
      (regla de oro 10: por transición, no por intervalo).
    """
    _retire(fleet)

    assert handle_status(fleet, {"status": "online"}, _presencia(30), ctx).is_ok
    assert handle_status(fleet, {"status": "offline"}, _presencia(31), ctx).is_ok

    salud = fleet.execute(
        "SELECT ts, reason FROM device_health WHERE gateway_id = %s ORDER BY ts", (GW,)
    ).fetchall()
    assert [(r[0], r[1]) for r in salud] == [
        (TS_PRESENCIA + timedelta(seconds=30), "transition"),
        (TS_PRESENCIA + timedelta(seconds=31), "transition"),
    ]

    filas = _alive_while_retired(fleet)
    assert len(filas) == 1, f"una huella por reconexión, no por mensaje: {filas}"
    actor, obj, meta_row = filas[0]
    assert actor == "edge:gw-dev-0001"
    assert obj == f"gateway:{GW}"
    assert meta_row["ignored_status"] == "online"


def test_status_la_huella_del_retirado_es_idempotente(fleet, ctx) -> None:
    """SQS es at-least-once (regla de oro 3): la REENTREGA del mismo beacon no
    puede inflar la bitácora, que es la tabla que nunca se poda (regla 11). El
    mensaje suprimido consume su `status_ts`, así que su copia ya no pasa la
    guarda monotónica. Dos reconexiones DISTINTAS sí son dos hechos distintos.
    """
    _retire(fleet)

    assert handle_status(fleet, {"status": "online"}, _presencia(30), ctx).is_ok
    assert handle_status(fleet, {"status": "online"}, _presencia(30), ctx).is_ok  # reentrega
    assert len(_alive_while_retired(fleet)) == 1

    assert handle_status(fleet, {"status": "online"}, _presencia(90), ctx).is_ok  # reconexión
    assert len(_alive_while_retired(fleet)) == 2
    assert _gw_status(fleet) == "retired"


def test_status_no_deja_huella_cuando_el_gabinete_no_esta_retirado(fleet, ctx) -> None:
    """Sin retiro no hay nada que defender: el camino normal no audita (regla 10)."""
    assert handle_status(fleet, {"status": "online"}, _presencia(30), ctx).is_ok
    assert _gw_status(fleet) == "online"
    assert _alive_while_retired(fleet) == []


def test_status_viejo_de_gabinete_vivo_no_inventa_una_huella_de_retiro(fleet, ctx) -> None:
    """Las DOS razones por las que el UPDATE no aplica son distintas y no se
    confunden: "lo bloqueó el retiro" (se audita) y "llegó viejo" (no).

    Sin las guardas de `_STATUS_RETIRED_SQL` —si bastara con que el gabinete
    exista— cada beacon reordenado por SQS, cosa rutinaria en una cola standard,
    escribiría en la bitácora que un gabinete perfectamente dado de alta "sigue
    vivo estando retirado". Justo en la tabla que nunca se poda (regla 11).
    """
    assert handle_status(fleet, {"status": "online"}, _presencia(30), ctx).is_ok
    assert handle_status(fleet, {"status": "online"}, _presencia(10), ctx).is_ok  # viejo

    assert _gw_status(fleet) == "online"
    assert _alive_while_retired(fleet) == []


def test_status_beacon_asciende_provisioned_a_online(fleet, ctx) -> None:
    """El ALTA normal de un gabinete nuevo no puede romperse: nace 'provisioned'
    (`queries/fleet.py::_INSERT`) y es su primer beacon quien lo pone 'online'.
    """
    assert _gw_status(fleet) == "provisioned"  # default del DDL

    assert handle_status(fleet, {"status": "online"}, _presencia(30), ctx).is_ok

    assert _gw_status(fleet) == "online"


def test_status_degraded_sigue_al_beacon(fleet, ctx) -> None:
    """'degraded' no es administrativo (nadie lo escribe hoy; el DDL lo admite y
    lo derivaría el heartbeat): el beacon lo mueve como a cualquier otro estado.
    """
    fleet.execute("RESET ROLE")
    fleet.execute("UPDATE gateways SET status = 'degraded' WHERE gateway_id = %s", (GW,))
    use(fleet, "takab_ingest")

    assert handle_status(fleet, {"status": "online"}, _presencia(30), ctx).is_ok

    assert _gw_status(fleet) == "online"


def test_status_tras_restaurar_el_gabinete_vuelve_a_seguir_al_beacon(fleet, ctx) -> None:
    """El retiro no es una lápida: restaurar desde la consola devuelve el gabinete
    al flujo normal de presencia. Sin esto, el arreglo dejaría cualquier gabinete
    restaurado congelado en 'provisioned' para siempre.

    Ojo a la guarda monotónica: el beacon suprimido durante el retiro NO avanza
    `metadata->>'status_ts'` (el UPDATE entero no ocurre), así que el primer
    beacon posterior a la restauración sigue siendo "más nuevo" y sí aplica.
    """
    assert handle_status(fleet, {"status": "online"}, _presencia(10), ctx).is_ok
    _retire(fleet)
    assert handle_status(fleet, {"status": "online"}, _presencia(30), ctx).is_ok
    assert _gw_status(fleet) == "retired"

    fleet.execute("RESET ROLE")
    fleet.execute("UPDATE gateways SET status = 'provisioned' WHERE gateway_id = %s", (GW,))
    use(fleet, "takab_ingest")

    assert handle_status(fleet, {"status": "online"}, _presencia(50), ctx).is_ok
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


# --------------------------------------------------------------------------
# [T-2.70] `fw_running`: qué código EJECUTA el gabinete, junto al que TIENE en
# disco. Misma disciplina que `fw_version` (ausente != null != basura), porque
# el hecho que separa a los dos campos es justo el que delata un despliegue a
# medias y no puede depender de un default benigno.
# --------------------------------------------------------------------------


def _fw_run(fleet) -> str | None:
    return fleet.execute("SELECT fw_running FROM gateways WHERE gateway_id = %s", (GW,)).fetchone()[
        0
    ]


def test_health_persiste_por_separado_el_codigo_del_disco_y_el_que_corre(fleet, ctx, meta) -> None:
    """El caso que hasta hoy era INDETECTABLE: `deploy.sh` escribió el código
    nuevo y el reinicio no ocurrió. El gabinete late declarando las dos cosas y
    la nube las guarda SIN fundirlas."""
    payload = _health(fw_version="bbbbbbb")
    payload["fw_running"] = "aaaaaaa"
    assert handle_health_snapshot(fleet, payload, meta, ctx).is_ok
    assert _fw(fleet) == "bbbbbbb", "el disco"
    assert _fw_run(fleet) == "aaaaaaa", "el proceso"


def test_health_sin_la_clave_fw_running_no_pisa_la_conocida(fleet, ctx, meta) -> None:
    """Contrato pre-1.9.0: un edge que no sabe hablar de «qué corre» no opina, y
    su silencio no puede borrar lo que ya se sabía."""
    payload = _health(fw_version="aaaaaaa")
    payload["fw_running"] = "aaaaaaa"
    assert handle_health_snapshot(fleet, payload, meta, ctx).is_ok
    viejo = _health(fw_version="aaaaaaa")  # sin la clave fw_running
    viejo["captured_at"] = "2026-07-06T10:02:03+00:00"
    assert handle_health_snapshot(fleet, viejo, meta, ctx).is_ok
    assert _fw_run(fleet) == "aaaaaaa"


def test_health_con_null_explicito_el_codigo_que_corre_pasa_a_sin_dato(fleet, ctx, meta) -> None:
    """NULL EXPLÍCITO = «late y NO SABE qué está ejecutando». Hecho nuevo, no
    silencio: conservar el valor viejo daría por aplicada una actualización sobre
    un gabinete que ya no puede confirmarla."""
    payload = _health(fw_version="aaaaaaa")
    payload["fw_running"] = "aaaaaaa"
    assert handle_health_snapshot(fleet, payload, meta, ctx).is_ok
    nuevo = _health(fw_version="aaaaaaa")
    nuevo["fw_running"] = None  # la clave ESTÁ, y vale null
    nuevo["captured_at"] = "2026-07-06T10:02:03+00:00"
    assert handle_health_snapshot(fleet, nuevo, meta, ctx).is_ok
    assert _fw_run(fleet) is None


def test_health_fw_running_absurdo_no_borra_lo_conocido(fleet, ctx, meta) -> None:
    """Basura ≠ «no sé»: un payload manipulado no convierte el vandalismo en un
    botón remoto de S/D sobre el criterio de éxito de una actualización."""
    payload = _health(fw_version="aaaaaaa")
    payload["fw_running"] = "aaaaaaa"
    assert handle_health_snapshot(fleet, payload, meta, ctx).is_ok
    malo = _health(fw_version="aaaaaaa")
    malo["fw_running"] = "x" * 200
    malo["captured_at"] = "2026-07-06T10:02:03+00:00"
    assert handle_health_snapshot(fleet, malo, meta, ctx).is_ok
    assert _fw_run(fleet) == "aaaaaaa"
