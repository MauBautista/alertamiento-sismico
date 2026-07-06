"""evidence — extracción de ventana + subida idempotente por sha256."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from takab_edge.buffer import RingBuffer
from takab_edge.config import BufferConfig
from takab_edge.contracts import WaveformPacket
from takab_edge.evidence import (
    FakeEvidenceUploader,
    collect_evidence,
    evidence_key,
    sha256_hex,
)

BASE = datetime(2026, 7, 6, 12, 0, 0, tzinfo=UTC)


def _pkt(start, channel="EHZ", first=0, n=100):
    return WaveformPacket(
        network="AM",
        station="R4F74",
        location="00",
        channel=channel,
        starttime=start,
        sample_rate=100.0,
        samples=list(range(first, first + n)),
    )


def _buffer_with_window(tmp_path) -> RingBuffer:
    buf = RingBuffer(BufferConfig(root=str(tmp_path)))
    for i in range(5):
        buf.append(_pkt(BASE + timedelta(seconds=i), first=i * 100))
    return buf


def test_sha256_and_key():
    assert sha256_hex(b"abc") == hashlib.sha256(b"abc").hexdigest()
    assert evidence_key("evt-1", "deadbeef") == "evidence/evt-1/deadbeef.mseed"


def test_collect_evidence_extracts_and_uploads(tmp_path):
    buf = _buffer_with_window(tmp_path)
    uploader = FakeEvidenceUploader()
    obj = collect_evidence(buf, uploader, "evt-1", BASE, BASE + timedelta(seconds=5))
    assert obj is not None
    assert obj.size_bytes > 0
    assert obj.s3_key == f"evidence/evt-1/{obj.sha256}.mseed"
    assert (("evt-1", obj.sha256)) in uploader.objects


def test_upload_is_idempotent_by_content(tmp_path):
    buf = _buffer_with_window(tmp_path)
    uploader = FakeEvidenceUploader()
    window = (BASE, BASE + timedelta(seconds=5))
    first = collect_evidence(buf, uploader, "evt-1", *window)
    again = collect_evidence(buf, uploader, "evt-1", *window)
    assert first.sha256 == again.sha256  # mismo contenido → mismo digest
    assert first.s3_key == again.s3_key
    assert len(uploader.objects) == 1  # idempotente: no duplica


def test_collect_returns_none_without_data(tmp_path):
    buf = RingBuffer(BufferConfig(root=str(tmp_path)))  # vacío
    obj = collect_evidence(buf, FakeEvidenceUploader(), "e", BASE, BASE + timedelta(seconds=1))
    assert obj is None
