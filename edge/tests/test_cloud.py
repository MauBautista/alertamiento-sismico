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
    cloud.publish("takab/events", event)  # mismo event_id → idempotente
    assert cloud.queued == 1
