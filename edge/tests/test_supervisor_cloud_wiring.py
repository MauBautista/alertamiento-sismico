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
from simulators.wr1 import WR1Simulator
from takab_edge.contracts import ActuationCause, ActuatorAction, ActuatorChannel
from takab_edge.supervisor import (
    ACKS_TOPIC,
    AUDIT_TOPIC,
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
    # [T-2.32] Aviso instrumental: el EVENTO viaja (alimenta el quórum) pero no
    # hay NINGÚN ack de actuador — nada actuó por una estación sola.
    assert _payloads(transport, ACKS_TOPIC) == []
    # La ruta SASMEX sí actúa: sus ACKs viajan con su event_id (cableado intacto).
    WR1Simulator(sup.gpio).alert()
    assert _wait(lambda: _payloads(transport, ACKS_TOPIC))
    acks = _payloads(transport, ACKS_TOPIC)
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


# --------------------------------------------------------------------------
# [T-2.86.a · criterio 2] La bitácora del gabinete SUBE al volver el enlace
# --------------------------------------------------------------------------
#
# El criterio 1 dejó la constancia en disco; esto prueba el otro extremo. Hasta
# que existieron el topic autorizado, la regla IoT, la tabla y la ingesta, el
# `sink` iba a `None` a propósito: publicar en un topic no autorizado DESCONECTA
# al gabinete en cada publish (producción, 2026-07-12).


@pytest.fixture
def gabinete_con_bitacora_aislada(settings, tmp_path):
    """Supervisor con la bitácora en un directorio PROPIO de este test.

    Sin esto los tests comparten la bitácora de la máquina, y no por descuido:
    `ledger_dir_for` es DERIVADO Y ESTABLE a propósito (T-2.67.b) —jamás un
    `mkdtemp`— porque un directorio nuevo en cada arranque haría que el Pi real
    perdiera la cola pendiente en cada reinicio. La consecuencia en tests es que
    `read_all()` devuelve lo acumulado por todas las corridas anteriores (aquí,
    9.628 filas del 10 de agosto), así que cualquier aserción sobre cuentas
    totales mide el historial de la máquina y no el test.
    """
    transport = FakeMqttTransport()
    sup = EdgeSupervisor(
        settings.model_copy(
            update={"health_heartbeat_s": 0.05, "cloud_spool_dir": str(tmp_path / "spool")}
        ),
        seedlink_source=None,
        mqtt_transport=transport,
    )
    sup.start()
    assert _wait(lambda: sup.cloud.online)
    try:
        yield sup, transport
    finally:
        sup.stop()


def _bitacora(transport: FakeMqttTransport) -> list[dict]:
    return _payloads(transport, AUDIT_TOPIC)


def test_la_bitacora_sube_por_su_topic_con_actor_y_causa(gabinete_con_bitacora_aislada):
    sup, transport = gabinete_con_bitacora_aislada
    sup.ledger.record(
        cause=ActuationCause.SASMEX,
        actor="wr-1",
        channel=ActuatorChannel.GAS_VALVE,
        action=ActuatorAction.ACTIVATE,
        online=False,
    )
    assert sup.ledger.drain() == 1
    filas = _bitacora(transport)
    assert len(filas) == 1, "la constancia no salió por `takab/audit`"
    fila = filas[0]
    # Las dos mitades que `ActuatorAck` no lleva y que un perito pide primero.
    assert fila["cause"] == "sasmex" and fila["actor"] == "wr-1"
    assert fila["online"] is False, "la fila que responde a RO-4.e es la de sin enlace"
    assert fila["record_id"], "sin `record_id` la nube no puede deduplicar la re-subida"


def test_drenar_dos_veces_no_re_sube_lo_ya_confirmado(gabinete_con_bitacora_aislada):
    """La otra mitad de la regla de oro 3, y la que no se ve sin probarla: lo local
    NO se borra al subir —el perito lo lee meses después—, así que lo único que
    impide duplicar es que la marca de agua avance."""
    sup, transport = gabinete_con_bitacora_aislada
    sup.ledger.record(cause=ActuationCause.MANUAL, actor="lan", channel="siren", action="silence")
    assert sup.ledger.drain() == 1
    assert sup.ledger.drain() == 0, "re-drenar volvió a subir lo ya confirmado"
    assert len(_bitacora(transport)) == 1
    # Y lo local sigue entero: subir no es borrar.
    assert len(sup.ledger.read_all()) == 1


def test_sin_enlace_la_bitacora_espera_y_sube_cuando_vuelve(gabinete_con_bitacora_aislada):
    """El caso de la ficha, entero: se actúa a oscuras y la constancia sube después."""
    sup, transport = gabinete_con_bitacora_aislada
    sup.cloud.set_online(False)
    sup.ledger.record(
        cause=ActuationCause.SASMEX,
        actor="wr-1",
        channel=ActuatorChannel.SIREN,
        action=ActuatorAction.ACTIVATE,
    )
    assert sup.ledger.drain() == 0, "sin enlace no puede darse por subida"
    assert _bitacora(transport) == []
    # Y no hace falta llamar a `drain()`: volver el enlace lo dispara solo
    # (`cloud.on_online`), que es el enganche que la ficha pide.
    sup.cloud.set_online(True)
    assert _wait(lambda: len(_bitacora(transport)) == 1), "al volver el enlace no subió sola"


def test_una_fila_rota_se_salta_y_no_ciega_a_las_siguientes(gabinete_con_bitacora_aislada):
    """`drain()` corta al primer fallo —correcto para un enlace caído, donde el
    orden importa—, pero una fila malformada NUNCA va a validar: bloquear
    sacrificaría todo lo que venga detrás por una sola fila. Y saltarla no pierde
    la evidencia, porque lo local no se borra jamás."""
    sup, transport = gabinete_con_bitacora_aislada
    assert sup._subir_fila_de_bitacora({"esto": "no es una fila"}) is True
    sup.ledger.record(cause=ActuationCause.MANUAL, actor="lan", channel="siren", action="silence")
    assert sup.ledger.drain() == 1
    assert len(_bitacora(transport)) == 1, "la fila buena de detrás no llegó a subir"
