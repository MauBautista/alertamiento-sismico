"""Wiring supervisor→cloud (T-1.17 G6) — health/acks/features/eventos + presencia retained.

Con `FakeMqttTransport` inyectado el supervisor publica por los topics de la flota
(`takab/events|acks|health|features`) y anuncia `{"status":"online"}` retained al
conectar (contraparte del LWT offline). Todo sin AWS ni hardware.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

import pytest
from simulators.mqtt import FakeMqttTransport
from simulators.quake import quake_packets
from simulators.rs4d import RS4DSimulator
from takab_edge.supervisor import (
    ACKS_TOPIC,
    EVENTS_TOPIC,
    FEATURES_TOPIC,
    HEALTH_TOPIC,
    EdgeSupervisor,
)

QUAKE_START = datetime(2026, 7, 6, 12, 0, 0, tzinfo=UTC)


def _wait(predicate, timeout_s: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return bool(predicate())


def _payloads(transport: FakeMqttTransport, topic: str) -> list[dict]:
    return [payload for t, payload in transport.published if t == topic]


@pytest.fixture
def online_supervisor(settings):
    """Supervisor arrancado con transporte fake; el hilo de reconexión conecta solo."""
    transport = FakeMqttTransport()
    sup = EdgeSupervisor(
        settings.model_copy(update={"health_heartbeat_s": 0.05}),
        seedlink_source=None,
        mqtt_transport=transport,
    )
    sup.start()
    assert _wait(lambda: sup.cloud.online)
    try:
        yield sup, transport
    finally:
        sup.stop()


def _feed_quake(sup: EdgeSupervisor) -> None:
    sim = RS4DSimulator(station=sup.settings.station)
    for packet in quake_packets(sim, QUAKE_START):
        sup.seedlink.feed(packet)


def test_quake_publishes_local_event_and_acks(online_supervisor):
    sup, transport = online_supervisor
    _feed_quake(sup)
    assert _wait(lambda: _payloads(transport, EVENTS_TOPIC))
    events = _payloads(transport, EVENTS_TOPIC)
    assert any(e["tier"] == "evacuate_or_hold" for e in events)
    assert all(e["tenant_id"] == sup.settings.tenant_id for e in events)
    acks = _payloads(transport, ACKS_TOPIC)
    # La secuencia evacuate incluye sirena y cierre de gas; cada ACK lleva su event_id.
    assert {a["channel"] for a in acks} >= {"siren", "gas_valve"}
    assert all(a["event_id"] and a["action"] == "activate" for a in acks)


def test_health_snapshots_transition_and_heartbeat(online_supervisor):
    _sup, transport = online_supervisor
    # Transición inicial (startup) Y beacon periódico (heartbeat) llegan a takab/health.
    assert _wait(
        lambda: (
            {s["transition_reason"] for s in _payloads(transport, HEALTH_TOPIC)}
            >= {"startup", "heartbeat"}
        )
    )


def test_features_flow_to_cloud(online_supervisor):
    sup, transport = online_supervisor
    sim = RS4DSimulator(station=sup.settings.station)
    stream = sim.stream(channel="EHZ")
    for _ in range(5):
        sup.seedlink.feed(next(stream))
    feats = _payloads(transport, FEATURES_TOPIC)
    assert len(feats) == 5  # cada Feature1s sale, sin dedup (no llevan event_id)
    assert all(f["channel"] == "EHZ" and f["station"] == sup.settings.station for f in feats)


def test_retained_online_published_on_connect(online_supervisor):
    sup, transport = online_supervisor
    topic = sup.settings.status_topic
    assert topic == f"takab/status/{sup.settings.gateway_id}"  # iot_thing vacío → gateway_id
    assert _wait(lambda: transport.retained.get(topic) == {"status": "online"})


def test_build_real_transport_from_settings(settings, monkeypatch):
    """Con endpoint + los 3 certs, .build() cablea el transporte real (sin conectar)."""
    from takab_edge.cloud import AwsIotMqttTransport

    monkeypatch.setenv("TAKAB_EDGE_HMAC_KEY", "clave-prod-de-prueba")
    cfg = settings.model_copy(
        update={
            "mqtt_endpoint": "ejemplo-ats.iot.us-east-2.amazonaws.com",
            "mqtt_cert_path": "/etc/takab/cert.pem",
            "mqtt_key_path": "/etc/takab/key.pem",
            "mqtt_ca_path": "/etc/takab/AmazonRootCA1.pem",
            "iot_thing": "gw-dev-0001",
        }
    )
    sup = EdgeSupervisor(cfg, seedlink_source=None)
    sup.build()  # sólo ensambla; no conecta
    transport = sup.cloud._transport
    assert isinstance(transport, AwsIotMqttTransport)
    assert transport._client_id == "gw-dev-0001"  # client_id = thing name (convención fija)
    assert transport._status_topic == "takab/status/gw-dev-0001"


def test_cloud_telemetry_topics_capped_from_settings(settings):
    """features/health llevan cota (48 h offline no agotan RAM/disco del Pi);
    eventos y ACKs — evidencia — quedan SIN cota."""
    sup = EdgeSupervisor(
        settings.model_copy(update={"cloud_telemetry_cap": 7}), seedlink_source=None
    )
    sup.build()
    assert sup.cloud._topic_caps == {FEATURES_TOPIC: 7, HEALTH_TOPIC: 7}
    assert EVENTS_TOPIC not in sup.cloud._topic_caps
    assert ACKS_TOPIC not in sup.cloud._topic_caps


def test_no_certs_keeps_offline_behaviour(settings):
    """Sin certs (dev/CI) no hay transporte: el conector encola offline como en T-1.11."""
    sup = EdgeSupervisor(settings, seedlink_source=None)
    sup.build()
    assert sup.cloud._transport is None
    assert sup.cloud.online is False
