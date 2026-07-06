"""signal — features 1 s (placeholder T-1.6): amplitud, clipping y health."""

from __future__ import annotations

from datetime import UTC, datetime

from simulators.rs4d import RS4DSimulator
from takab_edge.contracts import WaveformPacket
from takab_edge.signal import _CLIP_COUNT, compute_features

START = datetime(2026, 1, 1, tzinfo=UTC)


def test_quiet_packet_has_low_pga():
    sim = RS4DSimulator(seed=3)
    feature = compute_features(sim.packet("ENZ", START))
    assert feature.pga < 0.040  # bajo la banda de cautela de hospital
    assert feature.clipping is False
    assert feature.health_score == 1.0


def test_event_packet_has_high_pga():
    sim = RS4DSimulator(seed=3)
    feature = compute_features(sim.packet("ENZ", START, peak_counts=200_000.0))
    assert feature.pga > 0.060  # sobre la banda de disparo


def test_clipping_flagged_and_health_degraded():
    packet = WaveformPacket(
        station="TAKAB", channel="ENZ", starttime=START, samples=[0, _CLIP_COUNT, 0]
    )
    feature = compute_features(packet)
    assert feature.clipping is True
    assert feature.health_score == 0.5


def test_empty_packet_is_safe():
    packet = WaveformPacket(station="TAKAB", channel="ENZ", starttime=START, samples=[])
    feature = compute_features(packet)
    assert feature.pga == 0.0
    assert feature.health_score == 0.0
