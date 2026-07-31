"""WaveformRing (T-2.15) — ring de muestras en RAM + serve incremental decimado.

Contrato CONGELADO en §5.1 de la spec del panel: cursor global, `reset` cuando el
cursor ya no sirve, decimación min/max con pares APLANADOS (longitud siempre par),
`gap_before` como corte honesto — jamás empalmar tramos discontinuos.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from takab_edge.contracts import WaveformPacket
from takab_edge.signal.waveform import WaveformRing

T0 = datetime(2026, 7, 30, 12, 0, 0, tzinfo=UTC)
SR = 100.0


def _packet(channel: str, index: int, npts: int = 100, amplitude: int = 10) -> WaveformPacket:
    """Paquete contiguo #index (1 s a 100 sps por defecto), muestras deterministas."""
    return WaveformPacket(
        station="R4F74",
        channel=channel,
        starttime=T0 + timedelta(seconds=index * npts / SR),
        sample_rate=SR,
        samples=[amplitude * ((index * npts + i) % 3 - 1) for i in range(npts)],
    )


def _feed_seconds(ring: WaveformRing, channel: str, seconds: int) -> None:
    for i in range(seconds):
        ring.append(_packet(channel, i))


def test_ring_caps_at_60s_by_samples_and_drops_oldest():
    ring = WaveformRing(window_s=60.0)
    _feed_seconds(ring, "EHZ", 75)  # 75 s a 100 sps: 15 s deben caerse
    served = ring.serve(since=None, channels=None, max_points=6000)
    assert served["reset"] is True
    samples = served["channels"]["EHZ"]["samples"]
    assert served["channels"]["EHZ"]["encoding"] == "raw"
    assert len(samples) <= 60 * 100  # tope POR MUESTRAS, no por reloj
    # Lo servido es el TRAMO MÁS NUEVO: su primer timestamp ya avanzó desde T0.
    first_at = datetime.fromisoformat(served["channels"]["EHZ"]["first_sample_at"])
    assert first_at >= T0 + timedelta(seconds=15)


def test_minmax_decimation_preserves_single_sample_impulse():
    """Criterio TASKS: un impulso de UNA muestra sobrevive a la decimación."""
    ring = WaveformRing(window_s=60.0)
    spike = 8_000_000
    for i in range(60):
        packet = _packet("ENZ", i, amplitude=1)
        if i == 37:
            packet.samples[13] = spike
        ring.append(packet)
    served = ring.serve(since=None, channels=None, max_points=100)
    section = served["channels"]["ENZ"]
    assert section["encoding"] == "minmax"
    assert served["decimation"] > 1
    assert max(section["samples"]) == spike  # el pico NO se aplana
    assert served["sample_rate"] == SR / served["decimation"]


def test_minmax_samples_length_is_always_even():
    ring = WaveformRing(window_s=60.0)
    # 7 paquetes de 97 muestras: 679 muestras — ni redondo ni múltiplo del factor.
    for i in range(7):
        ring.append(_packet("ENN", i, npts=97))
    served = ring.serve(since=None, channels=None, max_points=50)
    samples = served["channels"]["ENN"]["samples"]
    assert served["channels"]["ENN"]["encoding"] == "minmax"
    assert len(samples) % 2 == 0
    assert len(samples) <= 2 * 50


def test_consecutive_incremental_serves_reconstruct_without_gaps_or_dups():
    ring = WaveformRing(window_s=60.0)
    expected: list[int] = []
    cursor = None
    rebuilt: list[int] = []
    for i in range(10):
        packet = _packet("EHZ", i)
        expected.extend(packet.samples)
        ring.append(packet)
        served = ring.serve(since=cursor, channels=["EHZ"], max_points=6000)
        cursor = served["cursor"]
        if i == 0:
            assert served["reset"] is True  # primera petición: ventana completa
        else:
            assert served["reset"] is False
        section = served["channels"]["EHZ"]
        assert section["encoding"] == "raw"
        rebuilt.extend(section["samples"])
    assert rebuilt == expected  # ni huecos ni duplicados
    # Tick sin muestras nuevas: cursor estable y canales vacíos (el cliente no redibuja).
    idle = ring.serve(since=cursor, channels=["EHZ"], max_points=6000)
    assert idle["cursor"] == cursor
    assert idle["reset"] is False
    assert idle["channels"] == {}


def test_expired_cursor_returns_full_window_with_reset():
    """Pestaña dormida: su `since` ya se cayó del ring ⇒ redibuja, no empalma."""
    ring = WaveformRing(window_s=60.0)
    _feed_seconds(ring, "EHZ", 5)
    stale = ring.serve(since=None, channels=None, max_points=6000)["cursor"]
    for i in range(5, 80):  # 75 s más: el tramo del cursor viejo ya no existe
        ring.append(_packet("EHZ", i))
    served = ring.serve(since=stale, channels=None, max_points=6000)
    assert served["reset"] is True
    assert len(served["channels"]["EHZ"]["samples"]) <= 60 * 100


def test_cursor_from_previous_process_life_resets():
    """Cursor de OTRA vida del proceso (reinicio del server): mayor que el gc actual."""
    ring = WaveformRing(window_s=60.0)
    _feed_seconds(ring, "EHZ", 3)
    served = ring.serve(since=999_999_999, channels=None, max_points=6000)
    assert served["reset"] is True
    assert len(served["channels"]["EHZ"]["samples"]) == 300


def test_gap_detected_via_next_starttime_sets_gap_before():
    ring = WaveformRing(window_s=60.0)
    ring.append(_packet("EHZ", 0))
    cursor = ring.serve(since=None, channels=None, max_points=6000)["cursor"]
    # El paquete 5 llega tras un hueco de 4 s del sensor (1..4 nunca llegaron).
    ring.append(_packet("EHZ", 5))
    served = ring.serve(since=cursor, channels=None, max_points=6000)
    section = served["channels"]["EHZ"]
    assert section["gap_before"] is True  # corte honesto: jamás empalmar
    assert len(section["samples"]) == 100  # SOLO el tramo tras el hueco
    first_at = datetime.fromisoformat(section["first_sample_at"])
    assert first_at == T0 + timedelta(seconds=5)


def test_channels_filter_and_max_points_clamped():
    ring = WaveformRing(window_s=60.0)
    for channel in ("EHZ", "ENZ", "ENN", "ENE"):
        ring.append(_packet(channel, 0))
    only = ring.serve(since=None, channels=["ENZ"], max_points=6000)
    assert set(only["channels"]) == {"ENZ"}
    # max_points fuera de rango cae al clamp [50, 6000], jamás 400 al kiosco.
    tiny = ring.serve(since=None, channels=["EHZ"], max_points=1)
    assert len(tiny["channels"]["EHZ"]["samples"]) <= 2 * 50
    huge = ring.serve(since=None, channels=["EHZ"], max_points=10_000_000)
    assert len(huge["channels"]["EHZ"]["samples"]) == 100  # raw: cabe completo


def test_empty_ring_serves_honest_empty():
    ring = WaveformRing(window_s=60.0)
    served = ring.serve(since=None, channels=None, max_points=1500)
    assert served == {
        "cursor": 0,
        "reset": True,
        "sample_rate": None,
        "decimation": 1,
        "channels": {},
    }
