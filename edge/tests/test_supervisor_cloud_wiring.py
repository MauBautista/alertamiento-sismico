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
from takab_edge.telemetry import FEATURES_BATCH_TOPIC

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


def test_features_de_tier_normal_se_acumulan_y_salen_en_lote(online_supervisor):
    """T-1.56: el ruido de fondo (tier normal) NO publica 1 Hz — se batchea."""
    sup, transport = online_supervisor
    sim = RS4DSimulator(station=sup.settings.station)
    stream = sim.stream(channel="EHZ")
    for _ in range(5):
        sup.seedlink.feed(next(stream))
    assert _payloads(transport, FEATURES_TOPIC) == []  # nada individual en reposo
    assert sup.telemetry.pending == 5
    sup.telemetry.flush_pending()
    # El publish NO es síncrono: sale por el hilo del CloudConnector. Aser­tar de
    # inmediato pasaba en local y fallaba en CI (máquina lenta) — flake real, visto
    # el 2026-07-14. Los tests hermanos ya esperaban; este se había saltado el _wait.
    assert _wait(lambda: _payloads(transport, FEATURES_BATCH_TOPIC))
    batches = _payloads(transport, FEATURES_BATCH_TOPIC)
    assert len(batches) == 1  # 5 features → UN publish (ancla del costo)
    assert batches[0]["gateway_id"] == sup.settings.gateway_id
    feats = batches[0]["features"]
    assert len(feats) == 5
    assert all(f["channel"] == "EHZ" and f["station"] == sup.settings.station for f in feats)


def test_escalacion_drena_el_lote_antes_del_1hz(online_supervisor):
    """El contexto pre-evento acumulado sale ANTES del primer feature individual."""
    sup, transport = online_supervisor
    sim = RS4DSimulator(station=sup.settings.station)
    stream = sim.stream(channel="EHZ")
    for _ in range(3):
        sup.seedlink.feed(next(stream))  # reposo → se acumulan
    assert sup.telemetry.pending == 3
    _feed_quake(sup)  # escala el tier → flush + 1 Hz individual

    def _topics() -> list[str]:
        return [t for t, _p in transport.published if t in (FEATURES_TOPIC, FEATURES_BATCH_TOPIC)]

    # Igual que arriba: el publish viaja por el hilo del cloud, hay que esperarlo.
    assert _wait(lambda: FEATURES_BATCH_TOPIC in _topics() and FEATURES_TOPIC in _topics())
    topics = _topics()
    assert topics.index(FEATURES_BATCH_TOPIC) < topics.index(FEATURES_TOPIC)


def test_sasmex_drena_el_acumulado_sin_feature(online_supervisor):
    """La escalación por gpio (WR-1) también dispara el flush del lote."""
    sup, transport = online_supervisor
    sim = RS4DSimulator(station=sup.settings.station)
    stream = sim.stream(channel="EHZ")
    for _ in range(4):
        sup.seedlink.feed(next(stream))
    assert sup.telemetry.pending == 4
    sup.gpio.simulate_sasmex(True)
    assert _wait(lambda: _payloads(transport, FEATURES_BATCH_TOPIC))
    assert sup.telemetry.pending == 0


def test_modo_prueba_protege_local_sin_publicar_a_la_nube(online_supervisor):
    """[T-1.69] Modo prueba del WR-1: el reflejo suena en LOCAL pero la nube NO
    recibe evento (sin incidente, sin correo). Así se prueba el WR-1 sin ruido."""
    sup, transport = online_supervisor
    sup.gpio.arm_test_mode(100.0)
    sup.gpio.simulate_sasmex(active=True)  # WR-1 en prueba: reflejo + rules (síncrono)
    assert sup.gpio.siren_sounding is True  # protección LOCAL intacta (la sirena suena)
    time.sleep(0.5)  # margen para cualquier publish asíncrono
    assert _payloads(transport, EVENTS_TOPIC) == []  # sin evento ⇒ sin incidente ⇒ sin correo
    assert _payloads(transport, ACKS_TOPIC) == []


def test_al_expirar_el_modo_prueba_vuelve_a_publicar(online_supervisor):
    sup, transport = online_supervisor
    sup.gpio.arm_test_mode(0.0)  # ventana nula ⇒ ya expirado
    sup.gpio.simulate_sasmex(active=True)
    assert _wait(lambda: _payloads(transport, EVENTS_TOPIC))  # vuelve a alertar a la nube


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
    eventos y ACKs — evidencia — quedan SIN cota. El topic batch (T-1.56) lleva
    cota DERIVADA (cap // batch_max): misma cota en features-equivalentes."""
    sup = EdgeSupervisor(
        settings.model_copy(update={"cloud_telemetry_cap": 7, "cloud_features_batch_max": 3}),
        seedlink_source=None,
    )
    sup.build()
    assert sup.cloud._topic_caps == {
        FEATURES_TOPIC: 7,
        HEALTH_TOPIC: 7,
        FEATURES_BATCH_TOPIC: 2,  # 7 // 3
    }
    assert EVENTS_TOPIC not in sup.cloud._topic_caps
    assert ACKS_TOPIC not in sup.cloud._topic_caps


def test_no_certs_keeps_offline_behaviour(settings):
    """Sin certs (dev/CI) no hay transporte: el conector encola offline como en T-1.11."""
    sup = EdgeSupervisor(settings, seedlink_source=None)
    sup.build()
    assert sup.cloud._transport is None
    assert sup.cloud.online is False
