"""signal — features 1 s validadas contra ObsPy de referencia (error <1%)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
from simulators.rs4d import RS4DSimulator
from takab_edge.contracts import WaveformPacket
from takab_edge.signal import (
    FeatureExtractor,
    classic_sta_lta,
    compute_features,
    differentiate,
    integrate,
    is_acceleration,
)

START = datetime(2026, 7, 6, 5, 0, 0, tzinfo=UTC)
SR = 100.0
DT = 1.0 / SR


def _max_rel_err(mine: np.ndarray, ref: np.ndarray) -> float:
    mask = np.abs(ref) > 1e-9
    return float((np.abs(mine[mask] - ref[mask]) / np.abs(ref[mask])).max())


# --- Validación de algoritmos contra ObsPy (<1%) ---


def test_classic_sta_lta_matches_obspy():
    from obspy.signal.trigger import classic_sta_lta as obspy_sta_lta

    rng = np.random.default_rng(7)
    x = rng.normal(0.0, 500.0, 2000)
    x[900:960] += 8000.0
    assert _max_rel_err(classic_sta_lta(x, 50, 500), obspy_sta_lta(x, 50, 500)) < 0.01


def test_integrate_matches_obspy():
    from obspy import Trace

    rng = np.random.default_rng(3)
    x = rng.normal(0.0, 100.0, 500)
    tr = Trace(x.copy())
    tr.stats.sampling_rate = SR
    tr.integrate()
    assert np.allclose(integrate(x, DT), tr.data, rtol=1e-6, atol=1e-6)


def test_differentiate_matches_obspy():
    from obspy import Trace

    rng = np.random.default_rng(4)
    x = rng.normal(0.0, 100.0, 500)
    tr = Trace(x.copy())
    tr.stats.sampling_rate = SR
    tr.differentiate()
    assert np.allclose(differentiate(x, DT), tr.data, rtol=1e-6, atol=1e-6)


def test_features_match_obspy_on_synthetic_trace():
    from obspy import Trace
    from obspy.signal.trigger import classic_sta_lta as obspy_sta_lta

    sim = RS4DSimulator(seed=11)
    packets = list(
        sim.stream("ENZ", start=START, seconds=8, event_onset_s=4, event_peak_counts=500_000.0)
    )
    data = np.concatenate([np.asarray(p.samples, dtype=np.float64) for p in packets])
    data = data - data.mean()
    assert _max_rel_err(classic_sta_lta(data, 50, 500), obspy_sta_lta(data, 50, 500)) < 0.01
    tr = Trace(data.copy())
    tr.stats.sampling_rate = SR
    tr.integrate()
    assert np.allclose(integrate(data, DT), tr.data, rtol=1e-6, atol=1e-6)


# --- Features del paquete ---


def test_is_acceleration_by_seed_code():
    assert is_acceleration("ENZ") is True
    assert is_acceleration("ENN") is True
    assert is_acceleration("EHZ") is False


def test_event_packet_raises_pga_pgv_over_quiet():
    sim = RS4DSimulator(seed=5)
    quiet = compute_features(sim.packet("ENZ", START))
    loud = compute_features(sim.packet("ENZ", START, peak_counts=1_000_000.0))
    assert loud.pga > quiet.pga * 5
    assert loud.pgv > quiet.pgv
    assert loud.pga > 0.06  # supera el disparo de hospital (con sensibilidad placeholder)
    assert quiet.pga < 0.04  # el ruido de fondo no dispara


def test_clipping_flagged_and_health_degraded():
    packet = WaveformPacket(
        station="R4F74", channel="ENZ", starttime=START, samples=[0, 9_000_000, 0, -9_000_000]
    )
    feature = compute_features(packet)
    assert feature.clipping is True
    assert feature.health_score == 0.5


def test_dead_channel_has_zero_health():
    packet = WaveformPacket(station="R4F74", channel="EHZ", starttime=START, samples=[1234] * 100)
    feature = compute_features(packet)
    assert feature.rms == 0.0
    assert feature.health_score == 0.0


def test_empty_packet_is_safe():
    feature = compute_features(
        WaveformPacket(station="R4F74", channel="ENZ", starttime=START, samples=[])
    )
    assert feature.pga == 0.0
    assert feature.health_score == 0.0


# --- STA/LTA con contexto rodante entre paquetes ---


def test_sta_lta_uses_rolling_context():
    fx = FeatureExtractor()
    sim = RS4DSimulator(seed=9)
    quiet_sta_lta = 0.0
    for i in range(6):  # ~6 s de ruido → llena el contexto LTA
        quiet_sta_lta = fx.process(sim.packet("EHZ", START + timedelta(seconds=i))).sta_lta
    event = fx.process(sim.packet("EHZ", START + timedelta(seconds=6), peak_counts=1_000_000.0))
    assert event.sta_lta > quiet_sta_lta
    assert event.sta_lta > 3.0  # transitorio claro sobre el ruido de fondo


# --- Robustez (hallazgos de la revisión adversarial) ---


def test_short_packet_is_safe_on_both_channel_kinds():
    # <2 muestras en canal de velocidad reventaba np.gradient; ahora es degenerado seguro.
    for channel in ("EHZ", "ENZ"):  # velocidad y aceleración
        feature = compute_features(
            WaveformPacket(station="R4F74", channel=channel, starttime=START, samples=[42])
        )
        assert feature.pga == 0.0 and feature.health_score == 0.0


def test_context_stays_bounded_even_with_tiny_lta():
    from takab_edge.config import SignalConfig

    # lta_seconds diminuto (round(lta*sr)=0) antes crecía sin límite; ahora se acota.
    fx = FeatureExtractor(SignalConfig(lta_seconds=0.004))
    sim = RS4DSimulator(seed=2)
    for i in range(60):
        fx.process(sim.packet("EHZ", START + timedelta(seconds=i)))
    assert len(fx._context["EHZ"]) <= 100  # nlta floored a nsta+1 (=51), muy por debajo de 60×100


def test_compute_features_pga_on_velocity_matches_obspy():
    from obspy import Trace
    from takab_edge.config import SignalConfig

    cfg = SignalConfig()
    pkt = RS4DSimulator(seed=13).packet("EHZ", START, peak_counts=800_000.0)  # velocidad
    feature = compute_features(pkt, cfg)
    # Referencia ObsPy: PGA = max|d(vel)/dt| / g con la misma sensibilidad.
    native = (
        np.asarray(pkt.samples, dtype=np.float64) - np.mean(pkt.samples)
    ) * cfg.vel_sensitivity_ms_per_count
    tr = Trace(native.copy())
    tr.stats.sampling_rate = SR
    tr.differentiate()
    pga_ref = float(np.abs(tr.data).max()) / 9.80665
    assert abs(feature.pga - pga_ref) / pga_ref < 0.01


# --- live_by_channel (T-1.53, panel LAN) -------------------------------------


def test_live_by_channel_tracks_multiple_channels():
    from takab_edge.signal import FeatureExtractor

    ex = FeatureExtractor()
    ex.process(WaveformPacket(station="R4F74", channel="EHZ", starttime=START, samples=[0, 5] * 50))
    ex.process(WaveformPacket(station="R4F74", channel="ENZ", starttime=START, samples=[0, 7] * 50))

    live = ex.live_by_channel()
    assert set(live) == {"EHZ", "ENZ"}
    feature, received_at = live["ENZ"]
    assert feature.channel == "ENZ"
    assert received_at.tzinfo is not None  # reloj de pared UTC del Pi, no del Shake
    # `.last` sigue funcionando (contrato previo intacto)
    assert ex.last is not None and ex.last.channel == "ENZ"


def test_live_by_channel_returns_copy():
    from takab_edge.signal import FeatureExtractor

    ex = FeatureExtractor()
    ex.process(WaveformPacket(station="R4F74", channel="EHZ", starttime=START, samples=[0, 5] * 50))
    snapshot = ex.live_by_channel()
    snapshot.clear()  # mutar la copia no toca el estado interno
    assert set(ex.live_by_channel()) == {"EHZ"}
