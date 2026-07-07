"""BackfillManager (T-1.25): ruta S3 del spool + evidencia offline.

Regla FASE-0 capa 4 con frontera exacta (≤15 min ⇒ MQTT; >15 min ⇒ S3);
anti-thundering-herd (jitter inyectado a 0, un objeto a la vez); fallback a
MQTT si el grant no llega o el PUT falla (los datos jamás se atoran).
"""

from __future__ import annotations

import gzip
import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from simulators.mqtt import FakeMqttTransport
from takab_edge.backfill import BackfillManager
from takab_edge.cloud import CloudConnector
from takab_edge.config import EdgeSettings
from takab_edge.contracts import Feature1s

NOW = datetime(2026, 7, 7, 12, 0, 0, tzinfo=UTC)
THING = "gw-backfill-test"


class _FakePut:
    def __init__(self, *, ok: bool = True) -> None:
        self.ok = ok
        self.calls: list[tuple[str, bytes, str]] = []

    def __call__(self, url: str, body: bytes, content_type: str) -> bool:
        self.calls.append((url, body, content_type))
        return self.ok


class _FakeBuffer:
    def __init__(self, data: bytes = b"") -> None:
        self.data = data
        self.windows: list[tuple[datetime, datetime]] = []

    def extract_window(self, start: datetime, end: datetime) -> bytes:
        self.windows.append((start, end))
        return self.data


def _feature(ts_offset_s: float = 0.0) -> Feature1s:
    return Feature1s(
        station="R4F74",
        channel="ENZ",
        window_start=NOW + timedelta(seconds=ts_offset_s),
        pga=0.01,
        pgv=0.1,
        rms=0.001,
        sta_lta=1.0,
    )


def _grant_for(transport: FakeMqttTransport, *, url: str = "https://s3/put", key: str = "k") -> int:
    """Responde el grant al ÚLTIMO request publicado; devuelve cuántos había."""
    requests = [p for t, p in transport.published if t.endswith(f"request/{THING}")]
    if requests:
        grant = {
            "kind": "backfill_grant",
            "request_id": requests[-1]["request_id"],
            "mode": requests[-1]["mode"],
            "url": url,
            "key": key,
            "expires_at": (NOW + timedelta(seconds=900)).isoformat(),
        }
        transport.deliver(f"takab/backfill/grant/{THING}", json.dumps(grant).encode())
    return len(requests)


def _rig(tmp_path: Path, *, put_ok: bool = True, grant_timeout_s: float = 0.3):
    settings = EdgeSettings(
        dev_mode=True,
        iot_thing=THING,
        cloud_spool_dir=str(tmp_path / "spool"),
        backfill_grant_timeout_s=grant_timeout_s,
    )
    transport = FakeMqttTransport()
    connector = CloudConnector(settings, transport=transport, spool_dir=tmp_path / "spool")
    put = _FakePut(ok=put_ok)
    buffer = _FakeBuffer(data=b"MSEED-BYTES")
    manager = BackfillManager(
        settings,
        connector,
        buffer=buffer,
        pending_dir=tmp_path / "pending",
        http_put=put,
        jitter_s=lambda: 0.0,
        clock=lambda: NOW,
    )
    return settings, transport, connector, manager, put, buffer


def _age_spool(connector: CloudConnector, seconds: float) -> None:
    """Envejece el registro MÁS VIEJO del spool (simula cola offline larga)."""
    with connector._lock:  # noqa: SLF001 — manipulación quirúrgica del fixture
        name, record = connector._queue[0]  # noqa: SLF001
        record["spooled_at"] = (NOW - timedelta(seconds=seconds)).isoformat()


def _wait_idle(manager: BackfillManager, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while manager._in_progress.is_set() and time.monotonic() < deadline:  # noqa: SLF001
        time.sleep(0.01)


# ------------------------------------------------------------- frontera 15 min


def test_spool_under_threshold_goes_mqtt(tmp_path: Path) -> None:
    _s, transport, connector, manager, put, _b = _rig(tmp_path)
    connector.publish("takab/features", _feature())
    _age_spool(connector, 899.0)  # 14:59 — bajo el umbral
    connector.set_online(True)
    _wait_idle(manager)

    assert put.calls == []  # nada por S3
    features = [t for t, _p in transport.published if t == "takab/features"]
    assert len(features) == 1  # drenó por MQTT (flush normal)


def test_spool_over_threshold_goes_s3(tmp_path: Path) -> None:
    _s, transport, connector, manager, put, _b = _rig(tmp_path)
    for i in range(3):
        connector.publish("takab/features", _feature(float(i)))
    _age_spool(connector, 901.0)  # 15:01 — sobre el umbral

    connector.set_online(True)  # dispara kick() vía flush
    time.sleep(0.05)
    assert _grant_for(transport) == 1  # publicó el request (directo, sin spool)
    _wait_idle(manager)

    assert len(put.calls) == 1
    _url, body, ctype = put.calls[0]
    assert ctype == "application/x-ndjson"
    lines = gzip.decompress(body).decode().strip().split("\n")
    assert len(lines) == 3
    assert all(json.loads(line)["topic"] == "takab/features" for line in lines)
    assert connector.queued == 0  # spool retirado tras confirmar el PUT
    # Ningún feature salió por MQTT (la ruta S3 tomó la cola completa).
    assert [t for t, _p in transport.published if t == "takab/features"] == []


def test_ndjson_preserves_spool_order(tmp_path: Path) -> None:
    _s, _t, connector, manager, _p, _b = _rig(tmp_path)
    for i in range(5):
        connector.publish("takab/features", _feature(float(i)))
    records = connector.peek_spool()
    lines = gzip.decompress(manager.ndjson_payload(records)).decode().strip().split("\n")
    got = [json.loads(line)["payload"]["window_start"] for line in lines]
    assert got == sorted(got)  # orden de encolado (cronológico aquí)


# ---------------------------------------------------------------- fallbacks


def test_grant_timeout_falls_back_to_mqtt(tmp_path: Path) -> None:
    _s, transport, connector, manager, put, _b = _rig(tmp_path, grant_timeout_s=0.05)
    connector.publish("takab/features", _feature())
    _age_spool(connector, 1200.0)

    connector.set_online(True)  # request sale pero NADIE responde el grant
    _wait_idle(manager)
    connector.flush()  # cooldown activo ⇒ MQTT drena

    assert put.calls == []
    assert [t for t, _p in transport.published if t == "takab/features"]
    assert connector.queued == 0


def test_put_failure_keeps_spool_and_cools_down(tmp_path: Path) -> None:
    _s, transport, connector, manager, put, _b = _rig(tmp_path, put_ok=False)
    connector.publish("takab/features", _feature())
    _age_spool(connector, 1200.0)

    connector.set_online(True)
    time.sleep(0.05)
    _grant_for(transport)
    _wait_idle(manager)

    assert len(put.calls) == 1  # lo intentó
    connector.flush()  # cooldown ⇒ vuelve la ruta MQTT
    assert [t for t, _p in transport.published if t == "takab/features"]


def test_one_upload_at_a_time(tmp_path: Path) -> None:
    _s, _t, connector, manager, _p, _b = _rig(tmp_path)
    manager._in_progress.set()  # noqa: SLF001 — simula upload en curso
    assert manager.should_take(connector) is True  # MQTT no compite
    manager.kick()  # no lanza un segundo hilo (idempotente)
    manager._in_progress.clear()  # noqa: SLF001


# ------------------------------------------------------------------ evidencia


def test_offline_event_evidence_uploads_on_reconnect(tmp_path: Path) -> None:
    _s, transport, connector, manager, put, buffer = _rig(tmp_path)
    event_id = uuid.uuid4().hex
    start, end = NOW - timedelta(seconds=60), NOW - timedelta(seconds=1)
    manager.queue_evidence(event_id, start, end)  # OFFLINE: queda durable
    assert manager.pending_evidence() == [event_id]
    assert put.calls == []

    connector.set_online(True)  # reconexión ⇒ on_online procesa pendientes
    time.sleep(0.05)
    _grant_for(transport, key=f"evidence/tenant-x/{event_id}/abc.mseed")

    deadline = time.monotonic() + 3.0
    while manager.pending_evidence() and time.monotonic() < deadline:
        time.sleep(0.01)

    assert manager.pending_evidence() == []
    assert len(put.calls) == 1
    assert put.calls[0][1] == b"MSEED-BYTES"
    assert put.calls[0][2] == "application/vnd.fdsn.mseed"
    request = [p for t, p in transport.published if t.endswith(f"request/{THING}")][-1]
    assert request["mode"] == "evidence"
    assert request["event_id"] == event_id
    assert request["sha256"]  # el sha va en el request (la nube arma la key)


def test_evidence_window_not_complete_waits(tmp_path: Path) -> None:
    _s, _t, connector, manager, put, _b = _rig(tmp_path)
    event_id = uuid.uuid4().hex
    manager.queue_evidence(event_id, NOW, NOW + timedelta(seconds=120))  # post-roll futuro
    connector.set_online(True)
    time.sleep(0.05)
    assert manager.pending_evidence() == [event_id]  # espera la ventana completa
    assert put.calls == []


def test_evidence_grant_timeout_stays_pending(tmp_path: Path) -> None:
    _s, _t, connector, manager, put, _b = _rig(tmp_path, grant_timeout_s=0.05)
    event_id = uuid.uuid4().hex
    manager.queue_evidence(event_id, NOW - timedelta(seconds=60), NOW - timedelta(seconds=1))
    connector.set_online(True)
    time.sleep(0.3)
    assert manager.pending_evidence() == [event_id]  # se reintenta en el siguiente online
    assert put.calls == []
