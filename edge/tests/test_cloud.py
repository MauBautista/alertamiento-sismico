"""cloud — cola offline-first idempotente (nunca bloquea la actuación)."""

from __future__ import annotations

from takab_edge.cloud import CloudConnector
from takab_edge.contracts import AlertSource, Tier, TierDecision


def _event():
    return TierDecision(tier=Tier.EVACUATE_OR_HOLD, source=AlertSource.SASMEX)


def test_publish_offline_queues_without_sending(settings):
    cloud = CloudConnector(settings)
    cloud.start()
    assert cloud.online is False
    assert cloud.publish("takab/events", _event()) is True
    assert cloud.queued == 1
    assert cloud.sent == 0


def test_going_online_flushes_queue(settings):
    cloud = CloudConnector(settings)
    cloud.start()
    cloud.publish("takab/events", _event())
    cloud.set_online(True)
    assert cloud.queued == 0
    assert cloud.sent == 1


def test_duplicate_event_id_is_not_requeued(settings):
    cloud = CloudConnector(settings)
    cloud.start()
    event = _event()
    cloud.publish("takab/events", event)
    cloud.publish("takab/events", event)  # mismo event_id y tier → idempotente
    assert cloud.queued == 1


def test_tier_escalation_is_published_not_deduped(settings):
    # WATCH→EVACUATE del mismo evento (mismo event_id, tier mayor) NO se deduplica:
    # la escalación DEBE salir del edge. Sólo re-publicaciones idénticas se descartan.
    cloud = CloudConnector(settings)
    cloud.start()
    watch = TierDecision(tier=Tier.WATCH, source=AlertSource.THRESHOLD)
    evacuate = TierDecision(
        event_id=watch.event_id, tier=Tier.EVACUATE_OR_HOLD, source=AlertSource.THRESHOLD
    )
    cloud.publish("takab/events", watch)
    cloud.publish("takab/events", evacuate)  # misma id, tier mayor → escala
    assert cloud.queued == 2
    cloud.publish("takab/events", watch)  # re-publicación idéntica → deduped
    assert cloud.queued == 2
