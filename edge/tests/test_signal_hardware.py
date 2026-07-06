"""signal — validación de features contra una traza REAL del Shake (gate #3).

Se SALTA si el Shake no es alcanzable (CI lo omite). Confirma que el algoritmo de
features (STA/LTA, integración) coincide con ObsPy (<1%) sobre datos reales de
`AM.R4F74`, no sólo sintéticos.
"""

from __future__ import annotations

import os
import socket
from datetime import UTC

import numpy as np
import pytest
from takab_edge.contracts import WaveformPacket
from takab_edge.signal import classic_sta_lta, compute_features, integrate

SHAKE_HOST = os.environ.get("TAKAB_SHAKE_HOST", "192.168.3.92")
SHAKE_PORT = int(os.environ.get("TAKAB_SHAKE_PORT", "18000"))
SHAKE_STATION = os.environ.get("TAKAB_SHAKE_STATION", "R4F74")


def _reachable(host: str, port: int, timeout: float = 0.6) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _reachable(SHAKE_HOST, SHAKE_PORT),
    reason=f"Raspberry Shake no alcanzable en {SHAKE_HOST}:{SHAKE_PORT} (gate #3 hardware)",
)


def _real_trace():
    from obspy import UTCDateTime
    from obspy.clients.seedlink.basic_client import Client

    client = Client(SHAKE_HOST, SHAKE_PORT, timeout=20)
    end = UTCDateTime()
    stream = client.get_waveforms("AM", SHAKE_STATION, "00", "EHZ", end - 15, end - 3)
    assert stream and len(stream[0].data), "el Shake no entregó traza EHZ"
    return stream[0]


def test_features_algorithm_matches_obspy_on_real_trace():
    from obspy.signal.trigger import classic_sta_lta as obspy_sta_lta

    trace = _real_trace()
    data = np.asarray(trace.data, dtype=np.float64)
    data = data - data.mean()
    nsta, nlta = 50, 500  # 0.5 s / 5 s a 100 sps
    assert len(data) >= nlta, "traza real demasiado corta para el LTA"

    ref = obspy_sta_lta(data, nsta, nlta)
    mine = classic_sta_lta(data, nsta, nlta)
    mask = np.abs(ref) > 1e-9
    assert (np.abs(mine[mask] - ref[mask]) / np.abs(ref[mask])).max() < 0.01

    # integración idéntica a ObsPy sobre la MISMA traza real demeaned.
    demeaned = trace.copy()
    demeaned.data = data
    demeaned.integrate()
    assert np.allclose(
        integrate(data, 1.0 / trace.stats.sampling_rate), demeaned.data, rtol=1e-5, atol=1e-3
    )


def test_compute_features_on_real_packet_is_sane():
    trace = _real_trace()
    packet = WaveformPacket(
        network="AM",
        station=SHAKE_STATION,
        location="00",
        channel="EHZ",
        starttime=trace.stats.starttime.datetime.replace(tzinfo=UTC),
        sample_rate=float(trace.stats.sampling_rate),
        samples=[int(x) for x in trace.data],
    )
    feature = compute_features(packet)
    assert feature.channel == "EHZ"
    assert feature.pga >= 0.0 and feature.pgv >= 0.0
    assert np.isfinite(feature.sta_lta)
    assert feature.health_score in (1.0, 0.5)  # fondo real: sin dropout
