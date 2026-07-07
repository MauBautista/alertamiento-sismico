"""cloud — cola durable offline: idempotencia, backfill tras reinicio, cero pérdida/dup."""

from __future__ import annotations

from simulators.mqtt import FakeMqttTransport
from takab_edge.cloud import CloudConnector
from takab_edge.contracts import (
    ActuatorAck,
    ActuatorAction,
    ActuatorChannel,
    AlertSource,
    HealthSnapshot,
    Tier,
    TierDecision,
)


def _decision(event_id: str = "evt-1", tier: Tier = Tier.EVACUATE_OR_HOLD) -> TierDecision:
    return TierDecision(event_id=event_id, tier=tier, source=AlertSource.SASMEX)


def _connector(settings, tmp_path, online: bool = True) -> tuple[CloudConnector, FakeMqttTransport]:
    transport = FakeMqttTransport(online=online)
    cloud = CloudConnector(settings, transport=transport, spool_dir=str(tmp_path))
    return cloud, transport


def test_publish_offline_queues_durably(settings, tmp_path):
    cloud, _ = _connector(settings, tmp_path, online=False)
    cloud.publish("takab/events", _decision())
    assert cloud.queued == 1
    assert cloud.sent == 0
    assert len(list(tmp_path.glob("*.json"))) == 1  # persistido en disco


def test_going_online_flushes_and_clears_spool(settings, tmp_path):
    cloud, transport = _connector(settings, tmp_path)
    cloud.publish("takab/events", _decision())
    cloud.set_online(True)
    assert cloud.queued == 0
    assert cloud.sent == 1
    assert transport.published[0][0] == "takab/events"
    assert list(tmp_path.glob("*.json")) == []  # borrado del spool al confirmar el envío


def test_duplicate_event_id_and_tier_not_requeued(settings, tmp_path):
    cloud, _ = _connector(settings, tmp_path, online=False)
    event = _decision()
    cloud.publish("takab/events", event)
    cloud.publish("takab/events", event)  # mismo event_id y tier → idempotente
    assert cloud.queued == 1


def test_tier_escalation_is_not_deduped(settings, tmp_path):
    cloud, _ = _connector(settings, tmp_path, online=False)
    watch = TierDecision(tier=Tier.WATCH, source=AlertSource.THRESHOLD)
    evacuate = TierDecision(
        event_id=watch.event_id, tier=Tier.EVACUATE_OR_HOLD, source=AlertSource.THRESHOLD
    )
    cloud.publish("takab/events", watch)
    cloud.publish("takab/events", evacuate)  # misma id, tier mayor → escala
    assert cloud.queued == 2


def test_offline_two_hours_then_reconnect_zero_loss_zero_dup(settings, tmp_path):
    cloud, transport = _connector(settings, tmp_path)
    cloud.set_online(True)
    cloud.publish("takab/events", _decision("a"))  # se envía en línea
    transport.go_offline()  # cae la WAN (simula ~2 h sin enlace)
    for eid in ("b", "c", "d"):
        cloud.publish("takab/events", _decision(eid))  # se encolan durables
    assert cloud.queued == 3
    transport.go_online()
    cloud.set_online(True)  # reconecta → backfill
    assert cloud.queued == 0
    ids = transport.event_ids
    assert ids == ["a", "b", "c", "d"]  # orden preservado, cero pérdida
    assert len(ids) == len(set(ids))  # cero duplicado


def test_durable_queue_survives_restart(settings, tmp_path):
    # Publica offline → "reinicia" (nuevo conector, mismo spool) → backfill sin pérdida.
    first, _ = _connector(settings, tmp_path, online=False)
    for eid in ("a", "b"):
        first.publish("takab/events", _decision(eid))
    assert first.queued == 2

    transport = FakeMqttTransport()
    restarted = CloudConnector(settings, transport=transport, spool_dir=str(tmp_path))
    assert restarted.queued == 2  # backfill del spool durable tras el reinicio
    restarted.set_online(True)
    assert restarted.sent == 2
    assert restarted.queued == 0
    assert transport.event_ids == ["a", "b"]


def test_publish_never_blocks_on_transport_error(settings, tmp_path):
    class _Raising(FakeMqttTransport):
        def publish(self, topic, payload, qos=1):
            raise RuntimeError("broker caído")

    transport = _Raising()
    cloud = CloudConnector(settings, transport=transport, spool_dir=str(tmp_path))
    cloud.set_online(True)
    assert cloud.publish("takab/events", _decision()) is True  # nunca lanza al llamador
    assert cloud.queued == 1  # persiste para reintento


def test_publishes_health_and_ack_payloads(settings, tmp_path):
    cloud, transport = _connector(settings, tmp_path)
    cloud.set_online(True)
    cloud.publish("takab/health", HealthSnapshot(gateway_id="gw-1"))
    cloud.publish(
        "takab/acks",
        ActuatorAck(
            channel=ActuatorChannel.SIREN,
            action=ActuatorAction.ACTIVATE,
            event_id="e1",
            success=True,
            latency_s=0.4,
        ),
    )
    assert len(transport.published) == 2


def test_ack_success_transition_same_actuation_not_collapsed(settings, tmp_path):
    # fallo→éxito del MISMO (event_id, channel, action) dentro de un episodio es
    # evidencia DISTINTA: colapsarla dejaría al SOC creyendo que el gas quedó
    # abierto (o cerrado) cuando la realidad es la contraria.
    cloud, transport = _connector(settings, tmp_path)
    cloud.set_online(True)
    for success, latency in ((False, 0.3), (True, 1.2)):
        cloud.publish(
            "takab/acks",
            ActuatorAck(
                channel=ActuatorChannel.GAS_VALVE,
                action=ActuatorAction.ACTIVATE,
                event_id="e1",
                success=success,
                latency_s=latency,
            ),
        )
    assert [p["success"] for _t, p in transport.published] == [False, True]


def test_identical_ack_republished_is_deduped(settings, tmp_path):
    cloud, _ = _connector(settings, tmp_path, online=False)
    ack = ActuatorAck(
        channel=ActuatorChannel.SIREN,
        action=ActuatorAction.ACTIVATE,
        event_id="e1",
        success=True,
        latency_s=0.4,
    )
    cloud.publish("takab/acks", ack)
    cloud.publish("takab/acks", ack)  # re-publicación idéntica (mismo executed_at)
    assert cloud.queued == 1


def test_topic_cap_drops_oldest_telemetry_only(settings, tmp_path):
    # Offline prolongado: la telemetría reponible (health/features) se acota
    # descartando lo MÁS ANTIGUO; los eventos (sin cota) jamás se descartan.
    transport = FakeMqttTransport(online=False)
    cloud = CloudConnector(
        settings,
        transport=transport,
        spool_dir=str(tmp_path),
        topic_caps={"takab/health": 3},
    )
    cloud.publish("takab/events", _decision("evt-1"))  # sin cota
    for i in range(5):
        cloud.publish("takab/health", HealthSnapshot(gateway_id=f"gw-{i}"))
    assert cloud.queued_by_topic("takab/health") == 3
    assert cloud.queued_by_topic("takab/events") == 1
    assert cloud.queued == 4
    assert len(list(tmp_path.glob("*.json"))) == 4  # el spool en disco también se poda
    transport.go_online()
    cloud.set_online(True)
    healths = [p["gateway_id"] for t, p in transport.published if t == "takab/health"]
    assert healths == ["gw-2", "gw-3", "gw-4"]  # sobreviven los más recientes
    assert "evt-1" in transport.event_ids


def test_flush_of_backlog_does_not_block_concurrent_publish(settings, tmp_path):
    # El drenado de un backlog NO retiene el lock entre mensajes: un publish
    # concurrente (hilo SeedLink en plena detección) no se queda esperando.
    import threading

    gate = threading.Event()  # retiene el envío en curso hasta liberarlo
    entered = threading.Event()

    class _Slow(FakeMqttTransport):
        def publish(self, topic, payload, qos=1, retain=False):
            entered.set()
            assert gate.wait(timeout=5.0)
            return super().publish(topic, payload, qos, retain)

    transport = _Slow()
    cloud = CloudConnector(settings, transport=transport, spool_dir=str(tmp_path))
    for eid in ("a", "b", "c"):
        cloud.publish("takab/events", _decision(eid))
    transport.connect()

    flusher = threading.Thread(target=cloud.flush, daemon=True)
    flusher.start()
    assert entered.wait(2.0)  # el flush está BLOQUEADO a mitad de un envío lento

    published = threading.Event()

    def _publish() -> None:
        cloud.publish("takab/events", _decision("d"))
        published.set()

    publisher = threading.Thread(target=_publish, daemon=True)
    publisher.start()
    assert published.wait(2.0), "publish quedó bloqueado por el flush del backlog"

    gate.set()
    publisher.join(timeout=5.0)
    flusher.join(timeout=5.0)
    cloud.flush()  # remata lo que quede
    assert cloud.queued == 0
    assert transport.event_ids == ["a", "b", "c", "d"]  # orden y cero pérdida


def test_distinct_acks_same_event_id_all_published(settings, tmp_path):
    # Varios ACKs del MISMO evento (sirena, gas, ascensor) NO deben colapsar por dedup:
    # se perdería la telemetría de vida ("¿cerró el gas?"). Cada ACK sale.
    cloud, transport = _connector(settings, tmp_path)
    cloud.set_online(True)
    for channel in (ActuatorChannel.SIREN, ActuatorChannel.GAS_VALVE, ActuatorChannel.ELEVATOR):
        cloud.publish(
            "takab/acks",
            ActuatorAck(
                channel=channel,
                action=ActuatorAction.ACTIVATE,
                event_id="e1",
                success=True,
                latency_s=0.1,
            ),
        )
    assert len(transport.published) == 3


def test_publish_never_raises_on_spool_write_failure(settings, tmp_path):
    # Disco lleno / FS de sólo lectura: publish NUNCA propaga (regla de oro 4.2) ni
    # envenena el dedup; el mensaje queda best-effort en memoria.
    cloud, _ = _connector(settings, tmp_path, online=False)

    def _boom(_record):
        raise OSError("disco lleno")

    cloud._spool.append = _boom
    assert cloud.publish("takab/events", _decision()) is True
    assert cloud.queued == 1  # best-effort en memoria, no perdido


def test_reconnect_thread_flushes_on_start(settings, tmp_path):
    import time

    transport = FakeMqttTransport()
    cloud = CloudConnector(settings, transport=transport, spool_dir=str(tmp_path))
    cloud.publish("takab/events", _decision("x"))  # encolado (aún sin conectar)
    assert cloud.queued == 1
    cloud.start()
    try:
        for _ in range(150):  # poll sobre `sent` (última escritura del flush, sin race)
            if cloud.sent >= 1:
                break
            time.sleep(0.02)
        assert cloud.sent == 1  # el hilo de reconexión conectó y vació la cola
        assert cloud.queued == 0
    finally:
        cloud.stop()
