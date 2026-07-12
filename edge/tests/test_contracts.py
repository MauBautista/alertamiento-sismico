"""Contratos Pydantic: serialización, idempotencia y semántica de etiquetas."""

from __future__ import annotations

import pytest
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


def test_feature_batch_exige_1_a_256_features():
    """T-1.56: lote nunca vacío y ≤256 (≈64 KB « 128 KB, tope de publish de IoT)."""
    from pydantic import ValidationError
    from takab_edge.contracts import Feature1s, FeatureBatch

    def feat() -> Feature1s:
        return Feature1s(
            station="R4F74",
            channel="EHZ",
            window_start=utcnow(),
            pga=0.001,
            pgv=0.01,
            rms=0.5,
            sta_lta=1.0,
        )

    with pytest.raises(ValidationError):
        FeatureBatch(gateway_id="gw-dev-0001", features=[])
    with pytest.raises(ValidationError):
        FeatureBatch(gateway_id="gw-dev-0001", features=[feat() for _ in range(257)])
    ok = FeatureBatch(gateway_id="gw-dev-0001", features=[feat()])
    assert ok.kind == "feature_batch" and len(ok.features) == 1
