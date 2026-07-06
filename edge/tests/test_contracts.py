"""Contratos Pydantic: serialización, idempotencia y semántica de etiquetas."""

from __future__ import annotations

from takab_edge.contracts import (
    ActuatorAck,
    ActuatorAction,
    ActuatorChannel,
    AlertSource,
    Tier,
    TierDecision,
    WaveformPacket,
    new_event_id,
    utcnow,
)


def test_waveform_packet_roundtrip_and_npts():
    packet = WaveformPacket(station="TAKAB", channel="EHZ", starttime=utcnow(), samples=[1, -2, 3])
    dumped = packet.model_dump(mode="json")
    restored = WaveformPacket.model_validate(dumped)
    assert restored.npts == 3
    assert restored.sample_rate == 100.0
    assert restored.samples == [1, -2, 3]


def test_event_id_is_unique_nonce():
    assert new_event_id() != new_event_id()


def test_tier_decision_defaults_event_id():
    decision = TierDecision(tier=Tier.WATCH, source=AlertSource.THRESHOLD)
    assert decision.event_id
    assert decision.tier is Tier.WATCH


def test_actuator_ack_relative_label():
    ack = ActuatorAck(
        channel=ActuatorChannel.SIREN,
        action=ActuatorAction.ACTIVATE,
        event_id="e1",
        success=True,
        latency_s=0.42,
    )
    assert ack.relative_label == "T+0.42s"


def test_all_five_tiers_present():
    assert {t.value for t in Tier} == {
        "normal",
        "watch",
        "restricted",
        "evacuate_or_hold",
        "manual_only",
    }
