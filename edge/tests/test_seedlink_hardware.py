"""seedlink — validación contra el Raspberry Shake REAL (gate #3).

Se SALTA si el Shake no es alcanzable (así CI, sin hardware, lo omite; en la LAN
del gabinete corre y mide de verdad). Host/estación overridables por entorno.

Hallazgos medidos contra `AM.R4F74` (ringserver OSOP): 100 sps, lag ~0.4 s; el
resume por número de secuencia reproduce el histórico del ring (cero-pérdida).
"""

from __future__ import annotations

import os
import socket
import threading
import time
from collections.abc import Callable

import pytest
from takab_edge.config import EdgeSettings
from takab_edge.contracts import WaveformPacket, utcnow
from takab_edge.seedlink import ObsPySeedLinkTransport, SeedLinkClient

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


def _wait_until(pred: Callable[[], bool], timeout: float = 25.0) -> bool:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        if pred():
            return True
        time.sleep(0.05)
    return pred()


def _transport(channels: list[str] | None = None) -> ObsPySeedLinkTransport:
    return ObsPySeedLinkTransport(
        SHAKE_HOST, SHAKE_PORT, "AM", SHAKE_STATION, "00", channels or ["EHZ"]
    )


def _run_until_first(transport: ObsPySeedLinkTransport) -> WaveformPacket:
    """Corre el transporte hasta el primer paquete y para (síncrono para el test)."""
    got: list[WaveformPacket] = []
    stop = threading.Event()

    def emit(packet: WaveformPacket) -> None:
        got.append(packet)
        stop.set()

    thread = threading.Thread(target=transport.run, args=(emit, stop), daemon=True)
    thread.start()
    assert _wait_until(lambda: bool(got)), "el Shake no entregó ningún paquete"
    stop.set()
    thread.join(timeout=5)
    return got[0]


def test_real_shake_streams_100sps_with_low_lag():
    client = SeedLinkClient(EdgeSettings(), transport=_transport())
    got: list[WaveformPacket] = []
    client.on_packet(got.append)
    client.start()
    try:
        assert _wait_until(lambda: len(got) >= 3)
    finally:
        client.stop()
    assert all(p.sample_rate == 100.0 for p in got), "sample rate del Shake ≠ 100 sps"
    assert client.last_lag_s is not None
    assert client.last_lag_s < 3.0, f"lag {client.last_lag_s:.2f}s (medido ~0.4s en R4F74)"
    assert client.reconnects == 0


def test_real_shake_backfills_via_seqnum_resume():
    # Cero-pérdida: reanudar desde un seqnum pasado reproduce el histórico del ring.
    transport = _transport()
    first = _run_until_first(transport)
    resume_seq = transport._resume_seq
    assert resume_seq >= 0
    time.sleep(8)  # deja avanzar el tiempo real ~8 s

    transport._resume_seq = resume_seq  # forzar reanudación desde el pasado
    resumed = _run_until_first(transport)
    # `age_s > 6` prueba el backfill: el paquete reanudado es de ~hace 8 s (no del
    # presente). El resume por seqnum entrega el paquete siguiente al seqnum pedido
    # (unos segundos tras `first`), así que no se afina más el offset exacto.
    age_s = (utcnow() - resumed.starttime).total_seconds()
    assert age_s > 6, f"el resume por seqnum no hizo backfill (age={age_s:.1f}s)"
    assert resumed.starttime >= first.starttime  # reanuda desde ≥ el punto pedido, no antes
