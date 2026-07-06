"""buffer — ring miniSEED en disco: escritura, retención, tope de tamaño, extracción."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from io import BytesIO

from takab_edge.buffer import RingBuffer
from takab_edge.config import BufferConfig
from takab_edge.contracts import WaveformPacket

BASE = datetime(2026, 7, 6, 12, 0, 0, tzinfo=UTC)


def _pkt(start: datetime, channel: str = "EHZ", first: int = 0, n: int = 100) -> WaveformPacket:
    return WaveformPacket(
        network="AM",
        station="R4F74",
        location="00",
        channel=channel,
        starttime=start,
        sample_rate=100.0,
        samples=list(range(first, first + n)),
    )


def _buffer(tmp_path, **kw) -> RingBuffer:
    return RingBuffer(BufferConfig(root=str(tmp_path), **kw))


def test_append_writes_miniseed_and_counts(tmp_path):
    buf = _buffer(tmp_path)
    buf.append(_pkt(BASE))
    buf.append(_pkt(BASE + timedelta(seconds=1), first=100))
    assert len(buf) == 2
    assert buf.total_bytes() > 0
    assert list(tmp_path.glob("*.mseed"))


def test_empty_packet_is_skipped(tmp_path):
    buf = _buffer(tmp_path)
    buf.append(WaveformPacket(station="R4F74", channel="EHZ", starttime=BASE, samples=[]))
    assert len(buf) == 0
    assert buf.total_bytes() == 0


def test_extract_window_roundtrip(tmp_path):
    from obspy import UTCDateTime, read

    buf = _buffer(tmp_path)
    for i in range(10):  # 10 s contiguos, muestras distinguibles por segundo
        buf.append(_pkt(BASE + timedelta(seconds=i), first=i * 100))

    data = buf.extract_window(BASE + timedelta(seconds=2), BASE + timedelta(seconds=5))
    assert data
    stream = read(BytesIO(data))
    stream.merge(method=1)
    trace = stream[0]
    # La ventana arranca en el segundo 2 (muestra 200) y las muestras coinciden.
    assert trace.stats.starttime >= UTCDateTime(BASE + timedelta(seconds=2)) - 0.02
    assert trace.stats.endtime <= UTCDateTime(BASE + timedelta(seconds=5)) + 0.02
    assert list(trace.data[:100]) == list(range(200, 300))


def test_extract_includes_all_channels(tmp_path):
    buf = _buffer(tmp_path)
    for channel in ("EHZ", "ENZ", "ENN", "ENE"):
        buf.append(_pkt(BASE, channel=channel))
    from obspy import read

    stream = read(BytesIO(buf.extract_window(BASE, BASE + timedelta(seconds=1))))
    channels = {tr.stats.channel for tr in stream}
    assert channels == {"EHZ", "ENZ", "ENN", "ENE"}


def test_extract_across_dayfiles(tmp_path):
    buf = _buffer(tmp_path)
    midnight = datetime(2026, 7, 6, 23, 59, 59, tzinfo=UTC)
    buf.append(_pkt(midnight, first=0))  # día 06
    buf.append(_pkt(midnight + timedelta(seconds=1), first=100))  # día 07
    assert len({p.name for p in tmp_path.glob("*.mseed")}) == 2  # dos archivos de día
    data = buf.extract_window(midnight, midnight + timedelta(seconds=2))
    from obspy import read

    stream = read(BytesIO(data))
    stream.merge(method=1)
    assert stream[0].stats.npts >= 150  # cubre ambos lados de la medianoche


def test_retention_prunes_old_dayfiles(tmp_path):
    buf = _buffer(tmp_path, retention_days=7)
    buf.append(_pkt(BASE - timedelta(days=10)))  # viejo (>7 d)
    buf.append(_pkt(BASE))  # reciente → newest
    buf.prune()
    names = [p.name for p in tmp_path.glob("*.mseed")]
    assert any("20260706" in n for n in names)  # reciente conservado
    assert not any("20260626" in n for n in names)  # viejo podado


def test_max_bytes_caps_total_size(tmp_path):
    buf = _buffer(tmp_path, retention_days=3650, max_bytes=6000)
    for i in range(15):  # 15 días → 15 archivos
        buf.append(_pkt(BASE + timedelta(days=i)))
    buf.prune()
    assert buf.total_bytes() <= 6000
    # el día más reciente sobrevive
    newest = (BASE + timedelta(days=14)).strftime("%Y%m%d")
    assert any(newest in p.name for p in tmp_path.glob("*.mseed"))
