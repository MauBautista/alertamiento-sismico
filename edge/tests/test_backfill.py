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

import pytest
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


class _RaisingBuffer:
    """[T-2.67] Ring que REVIENTA al extraer.

    No es hipotético: `RingBuffer.extract_window` hace `merge(method=1)` sin
    `fill_value` y con huecos ObsPy devuelve masked arrays que `write(MSEED)` no
    sabe escribir. En el gabinete real hay 3 eventos que fallan así en CADA
    pasada desde hace días — y `_FakeBuffer` nunca lanzó, así que la rama no
    tenía prueba ninguna.
    """

    def __init__(self) -> None:
        self.calls = 0

    def extract_window(self, start: datetime, end: datetime) -> bytes:
        self.calls += 1
        raise NotImplementedError("Masked array writing is not supported.")


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


def _rig(
    tmp_path: Path,
    *,
    put_ok: bool = True,
    grant_timeout_s: float = 0.3,
    buffer: object | None = None,
):
    settings = EdgeSettings(
        dev_mode=True,
        iot_thing=THING,
        cloud_spool_dir=str(tmp_path / "spool"),
        backfill_grant_timeout_s=grant_timeout_s,
    )
    transport = FakeMqttTransport()
    connector = CloudConnector(settings, transport=transport, spool_dir=tmp_path / "spool")
    put = _FakePut(ok=put_ok)
    buffer = buffer if buffer is not None else _FakeBuffer(data=b"MSEED-BYTES")
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


# ---------------------------------------- instantánea de evidencia (T-2.67)
#
# El panel del gabinete es lo único que queda cuando no hay nube, y hasta aquí no
# sabía NADA de la evidencia: fuera del proceso solo existía un bit observable
# —el .json está o no está— y ese bit colapsaba el mejor caso con el peor
# (subida OK y DESCARTE POR RING VACÍO borran el fichero igual). La instantánea
# vive en memoria y se reemplaza por asignación atómica: `status()` corre a la
# cadencia del kiosco y NO puede recorrer el directorio.


def _pending_file(pending: Path, event_id: str, start: datetime, end: datetime) -> None:
    pending.mkdir(parents=True, exist_ok=True)
    (pending / f"{event_id}.json").write_text(
        json.dumps({"event_id": event_id, "start": start.isoformat(), "end": end.isoformat()})
    )


def _wait_result(manager: BackfillManager, timeout: float = 3.0) -> dict:
    """Espera al FIN de la pasada: al cerrar, la instantánea se re-verifica contra disco."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        con_resultado = manager.evidence_snapshot()["last_result"] is not None
        if con_resultado and not manager._evidence_in_progress.is_set():  # noqa: SLF001
            break
        time.sleep(0.01)
    return manager.evidence_snapshot()


def test_el_conteo_de_evidencia_sobrevive_al_reinicio(tmp_path: Path) -> None:
    """Un contador sembrado en cero con el directorio LLENO miente tras reiniciar."""
    pending = tmp_path / "pending"
    viejo, nuevo = NOW - timedelta(days=15), NOW - timedelta(hours=2)
    _pending_file(pending, "evt-nuevo", nuevo, nuevo + timedelta(seconds=120))
    _pending_file(pending, "evt-viejo", viejo, viejo + timedelta(seconds=120))

    _s, _t, _c, manager, _p, _b = _rig(tmp_path)  # "reinicio": construye sobre el dir lleno

    snap = manager.evidence_snapshot()
    assert snap["pending"] == 2
    assert snap["oldest_pending_at"] == viejo.isoformat()  # el más viejo, no el primero por nombre
    assert [item["event_id"] for item in snap["items"]] == ["evt-viejo", "evt-nuevo"]
    assert snap["uploaded_total"] == 0  # nada subido aún: cero HONESTO
    assert snap["last_result"] is None  # ni verde ni rojo: S/D


def test_encolar_evidencia_no_recorre_el_directorio(tmp_path: Path, monkeypatch) -> None:
    """El contador se mantiene EN MEMORIA: encolar no puede pagar un glob+read.

    `queue_evidence` se llama desde el hilo de detección tras confirmar un
    evento; releer 18 ficheros ahí para actualizar un número sería pagar disco
    en el peor momento posible.
    """
    _s, _t, _c, manager, _p, _b = _rig(tmp_path)

    def _boom(*_a, **_k):
        raise AssertionError("queue_evidence recorrió el directorio pendiente")

    monkeypatch.setattr(type(manager._pending_dir), "glob", _boom)  # noqa: SLF001
    ventana = (NOW, NOW + timedelta(seconds=120))  # post-roll futuro: nadie sube nada
    manager.queue_evidence("evt-a", *ventana)
    manager.queue_evidence("evt-b", *ventana)
    manager.queue_evidence("evt-a", *ventana)  # re-encolado del MISMO evento: no duplica

    snap = manager.evidence_snapshot()
    assert snap["pending"] == 2
    assert snap["oldest_pending_at"] == NOW.isoformat()


def test_la_extraccion_que_revienta_se_declara_y_conserva_el_pendiente(tmp_path: Path) -> None:
    """El fallo VIVO del gabinete: se reintenta para siempre y no dejaba rastro."""
    ring = _RaisingBuffer()
    _s, _t, connector, manager, put, _b = _rig(tmp_path, buffer=ring)
    event_id = uuid.uuid4().hex
    manager.queue_evidence(event_id, NOW - timedelta(seconds=60), NOW - timedelta(seconds=1))

    connector.set_online(True)
    snap = _wait_result(manager)

    assert ring.calls == 1
    assert snap["extract_failed_total"] == 1
    assert snap["last_result"] == "extract_failed"
    assert snap["uploaded_total"] == 0
    assert manager.pending_evidence() == [event_id]  # NO se pierde: se reintentará
    assert snap["pending"] == 1
    assert put.calls == []


def test_el_descarte_por_ring_vacio_no_se_confunde_con_una_subida(tmp_path: Path) -> None:
    """Sin datos en el ring la evidencia SE PIERDE y el fichero se borra igual.

    Desde fuera era indistinguible del éxito. El contador propio es lo único que
    separa «archivada en la nube» de «perdida para siempre».
    """
    _s, _t, connector, manager, put, _b = _rig(tmp_path, buffer=_FakeBuffer(data=b""))
    event_id = uuid.uuid4().hex
    manager.queue_evidence(event_id, NOW - timedelta(seconds=60), NOW - timedelta(seconds=1))

    connector.set_online(True)
    snap = _wait_result(manager)

    assert snap["discarded_no_data_total"] == 1
    assert snap["uploaded_total"] == 0
    assert snap["last_result"] == "discarded_no_data"
    assert manager.pending_evidence() == []  # el fichero se fue (comportamiento vigente)
    assert snap["pending"] == 0
    assert put.calls == []


def test_la_subida_exitosa_se_cuenta_y_vacia_la_cola(tmp_path: Path) -> None:
    _s, transport, connector, manager, put, _b = _rig(tmp_path)
    event_id = uuid.uuid4().hex
    manager.queue_evidence(event_id, NOW - timedelta(seconds=60), NOW - timedelta(seconds=1))

    connector.set_online(True)
    time.sleep(0.05)
    _grant_for(transport, key=f"evidence/tenant-x/{event_id}/abc.mseed")
    snap = _wait_result(manager)

    assert snap["uploaded_total"] == 1
    assert snap["last_result"] == "uploaded"
    assert snap["pending"] == 0
    assert snap["discarded_no_data_total"] == 0
    assert len(put.calls) == 1


def test_el_grant_que_nunca_llega_deja_rastro(tmp_path: Path) -> None:
    """Antes devolvía None SIN una sola línea de log: 'no ha pasado nada'."""
    _s, _t, connector, manager, put, _b = _rig(tmp_path, grant_timeout_s=0.05)
    event_id = uuid.uuid4().hex
    manager.queue_evidence(event_id, NOW - timedelta(seconds=60), NOW - timedelta(seconds=1))

    connector.set_online(True)
    snap = _wait_result(manager)

    assert snap["failed_total"] == 1
    assert snap["last_result"] == "grant_timeout"
    assert snap["pending"] == 1
    assert manager.pending_evidence() == [event_id]
    assert put.calls == []


def test_el_put_fallido_se_distingue_del_grant_que_no_llega(tmp_path: Path) -> None:
    _s, transport, connector, manager, put, _b = _rig(tmp_path, put_ok=False)
    event_id = uuid.uuid4().hex
    manager.queue_evidence(event_id, NOW - timedelta(seconds=60), NOW - timedelta(seconds=1))

    connector.set_online(True)
    time.sleep(0.05)
    _grant_for(transport)
    snap = _wait_result(manager)

    assert snap["last_result"] == "put_failed"
    assert snap["failed_total"] == 1
    assert snap["pending"] == 1
    assert len(put.calls) == 1


# ------------------------------------ el pendiente ilegible (T-2.67 · auditoría)
#
# `_scan_pending` daba por hecho que todo `*.json` del directorio de pendientes
# era un OBJETO JSON y llamaba `spec.get("start")` a pelo. Un fichero con `null`,
# `[]`, `"x"` o `42` levanta AttributeError — que NO estaba en el `except` — y se
# escapa por DOS sitios:
#
#   1. el CONSTRUCTOR (`_refresh_pending_state`), que corre dentro de
#      `EdgeSupervisor.build()`, y `build()` no aísla por módulo ⇒ el gabinete
#      ENTERO no arranca. Un fichero basura deja un edificio sin protección.
#   2. el `finally` de `_run_pending_evidence` ⇒ el testigo `_evidence_in_progress`
#      no se libera nunca y la evidencia deja de procesarse EN SILENCIO.
#
# Agravante: sin `cloud_spool_dir` el directorio resuelve a `/tmp/backfill-pending`,
# compartido entre procesos y corridas.


#: Contenidos que un `.json` del directorio pendiente puede tener y no ser una spec.
#: Los cinco primeros son JSON VÁLIDO pero no un objeto: ahí estaba el AttributeError.
_BASURA_IRREPARABLE = [
    ("null", b"null"),
    ("lista_vacia", b"[]"),
    ("cadena", b'"x"'),
    ("entero", b"42"),
    ("booleano", b"true"),
    ("truncado", b'{"event_id":"a","start":'),
    ("no_utf8", b"\xff\xfe\x00"),
    ("vacio", b""),
]


@pytest.mark.parametrize(
    "contenido", [c for _n, c in _BASURA_IRREPARABLE], ids=[n for n, _c in _BASURA_IRREPARABLE]
)
def test_un_pendiente_ilegible_no_impide_construir_el_backfill(
    tmp_path: Path, contenido: bytes
) -> None:
    """Construir el manager NO puede lanzar: corre dentro de `EdgeSupervisor.build()`."""
    pending = tmp_path / "pending"
    pending.mkdir(parents=True)
    (pending / "evt-envenenado.json").write_bytes(contenido)

    _s, _t, _c, manager, _p, _b = _rig(tmp_path)  # antes: AttributeError aquí mismo

    snap = manager.evidence_snapshot()
    assert snap["unreadable"] == 1  # ni desaparece en silencio…
    assert "evt-envenenado" in snap["unreadable_items"]  # …ni anónimo: se NOMBRA
    assert snap["pending"] == 0  # y no se cuenta como si fuera a subir


@pytest.mark.parametrize(
    "contenido", [c for _n, c in _BASURA_IRREPARABLE], ids=[n for n, _c in _BASURA_IRREPARABLE]
)
def test_el_pendiente_irreparable_se_aparta_y_sigue_en_disco(
    tmp_path: Path, contenido: bytes
) -> None:
    """Cuarentena (patrón `DurableSpool.load`): ni se reintenta para siempre ni se borra.

    El contenido no va a mejorar nunca —`spec["end"]` fallaría en CADA pasada—,
    así que se aparta con otro sufijo; pero se CONSERVA para inspección y sigue
    contando: apartar en silencio sería el mismo pecado que reventar.
    """
    pending = tmp_path / "pending"
    pending.mkdir(parents=True)
    (pending / "evt-envenenado.json").write_bytes(contenido)

    _s, _t, _c, manager, _p, _b = _rig(tmp_path)

    assert not (pending / "evt-envenenado.json").exists()  # fuera de la ruta de subida
    apartados = list(pending.glob("*.unreadable"))
    assert [p.name for p in apartados] == ["evt-envenenado.json.unreadable"]
    assert apartados[0].read_bytes() == contenido  # el byte exacto, para el forense
    # …y al RECONSTRUIR (reinicio del gabinete) el conteo NO vuelve a cero: el
    # fichero apartado ya no casa con `*.json`, así que si sólo se contara el glob
    # de pendientes el hallazgo se evaporaría en el siguiente arranque.
    _s2, _t2, _c2, reinicio, _p2, _b2 = _rig(tmp_path)
    assert reinicio.evidence_snapshot()["unreadable"] == 1


def test_un_pendiente_ilegible_por_E_S_no_se_aparta_pero_se_cuenta(tmp_path: Path) -> None:
    """Permisos/EIO pueden ser TRANSITORIOS: renombrar ahí perdería evidencia buena.

    La frontera es exacta: contenido irreparable ⇒ cuarentena; error de E/S ⇒ se
    deja donde está y sólo se declara.
    """
    pending = tmp_path / "pending"
    pending.mkdir(parents=True)
    victima = pending / "evt-sin-permiso.json"
    victima.write_text(json.dumps({"event_id": "evt-sin-permiso", "start": NOW.isoformat()}))
    victima.chmod(0o000)
    try:
        _s, _t, _c, manager, _p, _b = _rig(tmp_path)
        snap = manager.evidence_snapshot()
        assert snap["unreadable"] == 1
        assert "evt-sin-permiso" in snap["unreadable_items"]
        assert victima.exists()  # NO se aparta: puede ser transitorio
        assert list(pending.glob("*.unreadable")) == []
    finally:
        victima.chmod(0o600)


def test_un_directorio_o_symlink_roto_con_nombre_json_no_tumba_el_backfill(
    tmp_path: Path,
) -> None:
    """Dos formas de `*.json` que ni siquiera son un fichero legible."""
    pending = tmp_path / "pending"
    pending.mkdir(parents=True)
    (pending / "soy-un-directorio.json").mkdir()
    (pending / "symlink-roto.json").symlink_to(tmp_path / "no-existe")

    _s, _t, _c, manager, _p, _b = _rig(tmp_path)

    snap = manager.evidence_snapshot()
    assert snap["unreadable"] == 2
    assert snap["pending"] == 0
    assert (pending / "soy-un-directorio.json").is_dir()  # jamás se renombra un directorio


def test_un_pendiente_ilegible_no_atasca_la_pasada_de_evidencia(tmp_path: Path) -> None:
    """El segundo escape: el `finally` de la pasada.

    Si `_refresh_pending_state` lanza dentro del `finally`, el testigo
    `_evidence_in_progress` no se limpia NUNCA: el hilo muere, la evidencia deja
    de procesarse y desde fuera no pasó nada. El gabinete queda mudo para el
    respaldo hasta el siguiente reinicio (que además tampoco arrancaría).
    """
    pending = tmp_path / "pending"
    pending.mkdir(parents=True)
    _s, transport, connector, manager, put, _b = _rig(tmp_path)
    bueno = uuid.uuid4().hex
    manager.queue_evidence(bueno, NOW - timedelta(seconds=60), NOW - timedelta(seconds=1))
    (pending / "evt-envenenado.json").write_bytes(b"null")

    connector.set_online(True)
    time.sleep(0.05)
    _grant_for(transport, key=f"evidence/tenant-x/{bueno}/abc.mseed")
    snap = _wait_result(manager)

    assert snap["uploaded_total"] == 1  # el pendiente BUENO sí subió
    assert not manager._evidence_in_progress.is_set()  # noqa: SLF001 — testigo liberado
    assert snap["phase"] == "idle"  # la pasada cerró: el panel no se queda en 'uploading'
    assert snap["unreadable"] == 1
    assert snap["pending"] == 0
    # …y una pasada POSTERIOR sigue arrancando (el testigo no quedó pegado).
    manager._kick_evidence()  # noqa: SLF001
    time.sleep(0.05)
    assert manager.evidence_snapshot()["unreadable"] == 1


def test_el_cierre_de_la_pasada_no_se_atasca_pase_lo_que_pase(tmp_path: Path) -> None:
    """El `finally` es un cuello de botella: lo que se escape de ahí deja el
    testigo puesto PARA SIEMPRE y el respaldo muere en silencio.

    Que hoy `_scan_pending` no lance es un accidente de la corrección de arriba;
    el invariante es del `finally`, no del escáner, y por eso se prueba con un
    fallo que NO es de disco (el `except OSError` original sólo cubría esos).
    """
    _s, _t, connector, manager, _p, _b = _rig(tmp_path)
    manager.queue_evidence("evt-x", NOW - timedelta(seconds=60), NOW - timedelta(seconds=1))

    def _boom() -> dict:
        raise RuntimeError("el escáner del directorio reventó por donde nadie miraba")

    manager._scan_pending = _boom  # noqa: SLF001

    connector.set_online(True)
    deadline = time.monotonic() + 3.0
    while manager._evidence_in_progress.is_set() and time.monotonic() < deadline:  # noqa: SLF001
        time.sleep(0.01)

    assert not manager._evidence_in_progress.is_set()  # noqa: SLF001 — testigo LIBERADO
    assert manager.evidence_snapshot()["phase"] == "idle"  # y el panel no se queda colgado


def test_encolar_evidencia_escribe_atomico(tmp_path: Path) -> None:
    """Sin tmp+replace, un corte de energía a media escritura deja un `.json`
    truncado — y la cuarentena de arriba se comería una evidencia LEGÍTIMA que
    otra pasada está escribiendo justo ahora. El fichero aparece entero o no
    aparece: mismo patrón que `DurableSpool.append` y `CatalogStore._write_atomic`.
    """
    _s, _t, _c, manager, _p, _b = _rig(tmp_path)
    pending = tmp_path / "pending"
    vistos: list[list[str]] = []
    real = Path.write_text

    def _espia(self: Path, data: str, *args, **kwargs):  # noqa: ANN202
        salida = real(self, data, *args, **kwargs)
        vistos.append(sorted(p.name for p in pending.glob("*.json")))
        return salida

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(Path, "write_text", _espia)
        manager.queue_evidence("evt-atomico", NOW, NOW + timedelta(seconds=120))

    # En el instante de escribir el contenido, el nombre DEFINITIVO no existe aún.
    assert vistos and all("evt-atomico.json" not in visto for visto in vistos)
    assert manager.pending_evidence() == ["evt-atomico"]


def test_la_cola_de_evidencia_declara_si_es_durable(tmp_path: Path) -> None:
    """Sin `cloud_spool_dir`, la evidencia pendiente vive en un tempdir NUEVO en
    cada arranque: se evapora al reiniciar y el contador diría 0 honestamente
    para siempre. `provision_gateway.sh` no escribe esa clave, así que todo
    gabinete recién aprovisionado está así — el panel tiene que DECIRLO.
    """
    _s, _t, _c, durable, _p, _b = _rig(tmp_path)
    assert durable.evidence_snapshot()["durable"] is True

    settings = EdgeSettings(dev_mode=True, iot_thing=THING, cloud_spool_dir="")
    connector = CloudConnector(
        settings, transport=FakeMqttTransport(), spool_dir=tmp_path / "spool-efimero"
    )
    efimero = BackfillManager(settings, connector, buffer=_FakeBuffer(data=b"X"))
    assert efimero.evidence_snapshot()["durable"] is False
