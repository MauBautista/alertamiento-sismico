"""seedlink — reconexión/backoff, lag, cero-pérdida (dedup) y gaps, sin hardware."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from takab_edge.config import EdgeSettings
from takab_edge.contracts import WaveformPacket, utcnow
from takab_edge.seedlink import SeedLinkClient

START = datetime(2026, 7, 6, 5, 0, 0, tzinfo=UTC)


def _settings(**kw) -> EdgeSettings:
    # Backoff diminuto para que la reconexión sea rápida en test.
    return EdgeSettings(seedlink_backoff_initial_s=0.001, seedlink_backoff_max_s=0.01, **kw)


def _pkt(channel: str = "EHZ", start: datetime = START, n: int = 100, sr: float = 100.0):
    return WaveformPacket(
        station="R4F74", channel=channel, starttime=start, sample_rate=sr, samples=list(range(n))
    )


def _pkt_lagging(lag_s: float, channel: str = "EHZ", n: int = 100, sr: float = 100.0):
    end = utcnow() - timedelta(seconds=lag_s)
    start = end - timedelta(seconds=(n - 1) / sr)
    return WaveformPacket(
        station="R4F74", channel=channel, starttime=start, sample_rate=sr, samples=list(range(n))
    )


def _wait_until(pred: Callable[[], bool], timeout: float = 5.0) -> bool:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        if pred():
            return True
        time.sleep(0.005)
    return pred()


class FakeTransport:
    """Transporte guionable: cada `run` consume un ítem (lote de paquetes o excepción)."""

    def __init__(self, script: list) -> None:
        self.script = list(script)

    def run(self, emit: Callable[[WaveformPacket], None], stop: threading.Event) -> None:
        if self.script:
            item = self.script.pop(0)
            if isinstance(item, BaseException):
                raise item
            for packet in item:
                if stop.is_set():
                    return
                emit(packet)
            return  # lote entregado → "desconexión" → el cliente reconectará
        while not stop.wait(0.02):  # sin más guion: conexión viva ociosa hasta stop
            pass


def _client(transport: FakeTransport, **kw) -> tuple[SeedLinkClient, list[WaveformPacket]]:
    client = SeedLinkClient(_settings(**kw), transport=transport)
    got: list[WaveformPacket] = []
    client.on_packet(got.append)
    return client, got


def test_reconnects_with_backoff_then_streams():
    transport = FakeTransport(
        [
            ConnectionError("caído"),
            ConnectionError("caído"),
            [_pkt(), _pkt(start=START + timedelta(seconds=1))],
        ]
    )
    client, got = _client(transport)
    client.start()
    try:
        assert _wait_until(lambda: len(got) >= 2)
    finally:
        client.stop()
    assert len(got) == 2
    assert client.reconnects >= 2


def test_zero_loss_dedup_on_resume():
    p1, p2, p3 = (
        _pkt(),
        _pkt(start=START + timedelta(seconds=1)),
        _pkt(start=START + timedelta(seconds=2)),
    )
    # La reconexión reproduce p2 (solape del resume) antes de p3: no debe duplicarse.
    transport = FakeTransport([[p1, p2], ConnectionError("drop"), [p2, p3]])
    client, got = _client(transport)
    client.start()
    try:
        assert _wait_until(lambda: len(got) >= 3)
    finally:
        client.stop()
    assert [p.starttime for p in got] == [p1.starttime, p2.starttime, p3.starttime]
    assert client.duplicates == 1


def test_gap_detected_when_packet_missing():
    # p1 cubre [START, START+1s); falta el de START+1s; p3 empieza en START+2s → gap.
    p1, p3 = _pkt(), _pkt(start=START + timedelta(seconds=2))
    transport = FakeTransport([[p1, p3]])
    client, got = _client(transport)
    client.start()
    try:
        assert _wait_until(lambda: len(got) >= 2)
    finally:
        client.stop()
    assert client.gaps == 1


def test_lag_is_measured():
    transport = FakeTransport([[_pkt_lagging(0.3)]])
    client, got = _client(transport)
    client.start()
    try:
        assert _wait_until(lambda: len(got) >= 1)
    finally:
        client.stop()
    assert client.last_lag_s is not None
    assert 0.0 < client.last_lag_s < 1.5


def test_no_thread_without_transport_or_source():
    client = SeedLinkClient(_settings(), source=None, transport=None)
    client.start()
    client.stop()
    assert client.packets_seen == 0


def test_obspy_transport_treats_slerror_as_disconnect(monkeypatch):
    # SLERROR es un centinela de bytes (no SLPacket) = desconexión → run() debe RETORNAR
    # (para que el cliente reconecte y lo cuente), no tragarlo con `continue`.
    from obspy.clients.seedlink.slpacket import SLPacket
    from takab_edge.seedlink import ObsPySeedLinkTransport

    class FakeConn:
        netto = 0.0

        def __init__(self) -> None:
            self.calls = 0

        def set_sl_address(self, addr: str) -> None:
            pass

        def add_stream(self, *a, **k) -> None:
            pass

        def collect(self):
            self.calls += 1
            # Red de seguridad: si el fix regresara y tragara SLERROR, SLTERMINATE evita colgar.
            return SLPacket.SLERROR if self.calls <= 3 else SLPacket.SLTERMINATE

        def close(self) -> None:
            pass

    conn = FakeConn()
    monkeypatch.setattr(
        "obspy.clients.seedlink.client.seedlinkconnection.SeedLinkConnection",
        lambda *a, **k: conn,
    )
    transport = ObsPySeedLinkTransport("h", 1, "AM", "R4F74", "00", ["EHZ"])
    transport.run(lambda p: None, threading.Event())
    assert conn.calls == 1  # SLERROR retornó en la 1ª llamada (no lo trató como no-dato)
