"""El sustituto de IoT Core + SQS debe comportarse como el original.

Si estos contratos se rompen, la demo del hito deja de demostrar lo que dice
demostrar: el enriquecimiento `meta_*` es lo que el consumer usa para resolver la
identidad del gateway, y el orden/idempotencia del spool es lo que sostiene el
criterio de "cero pérdida, cero duplicados" tras un corte de internet.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from demo.spool import SpoolMqttTransport, SpoolSqsClient  # noqa: E402

QUEUE = "demo://events"


@pytest.fixture
def spool(tmp_path: Path) -> Path:
    return tmp_path / "gw-sim-0001"


def _transport(spool: Path) -> SpoolMqttTransport:
    t = SpoolMqttTransport(spool, thing="gw-sim-0001")
    t.connect()
    return t


def test_publish_enriquece_como_la_iot_rule(spool: Path) -> None:
    """`meta_principal` es la identidad NO falsificable que el consumer resuelve."""
    t = _transport(spool)
    assert t.publish("takab/events", json.dumps({"event_id": "e1"}).encode()) is True

    (written,) = list(spool.glob("*.json"))
    body = json.loads(written.read_text())
    assert body["meta_principal"] == "gw-sim-0001"
    assert body["meta_topic"] == "takab/events"
    assert isinstance(body["meta_ts_iot"], int)
    assert body["event_id"] == "e1"  # el payload original se conserva intacto


def test_publish_sin_conectar_no_escribe_y_devuelve_false(spool: Path) -> None:
    """El CloudConnector encola durablemente cuando publish devuelve False."""
    t = SpoolMqttTransport(spool, thing="gw-sim-0001")  # sin connect()
    assert t.publish("takab/events", b"{}") is False
    assert list(spool.glob("*.json")) == []


def test_go_offline_corta_la_wan_y_el_proximo_connect_falla(spool: Path) -> None:
    t = _transport(spool)
    t.go_offline()
    assert t.connected is False
    assert t.publish("takab/events", b"{}") is False
    with pytest.raises(ConnectionError):
        t.connect()

    t.go_online()
    t.connect()
    assert t.connected is True
    assert t.publish("takab/events", b"{}") is True


def test_orden_de_publicacion_se_preserva(spool: Path) -> None:
    """Sin orden estable no se puede afirmar 'la cola drena EN ORDEN'."""
    t = _transport(spool)
    for i in range(12):  # >9 para que el orden lexicográfico no sea el numérico ingenuo
        t.publish("takab/events", json.dumps({"n": i}).encode())

    sqs = SpoolSqsClient([spool], spool.parent / "dlq")
    got = [json.loads(m["Body"])["n"] for m in sqs.receive_message(QUEUE, 20)["Messages"]]
    assert got == list(range(12))


def test_receive_delete_es_at_least_once_no_reentrega_lo_borrado(spool: Path) -> None:
    t = _transport(spool)
    t.publish("takab/events", b'{"n": 1}')
    sqs = SpoolSqsClient([spool], spool.parent / "dlq")

    first = sqs.receive_message(QUEUE)["Messages"]
    assert len(first) == 1
    # En vuelo: un segundo receive NO lo vuelve a entregar.
    assert sqs.receive_message(QUEUE)["Messages"] == []

    sqs.delete_message(QUEUE, first[0]["ReceiptHandle"])
    assert sqs.receive_message(QUEUE)["Messages"] == []
    assert sqs.pending_count == 0


def test_delete_batch_borra_todo_el_lote(spool: Path) -> None:
    t = _transport(spool)
    for i in range(3):
        t.publish("takab/events", json.dumps({"n": i}).encode())
    sqs = SpoolSqsClient([spool], spool.parent / "dlq")
    msgs = sqs.receive_message(QUEUE, 10)["Messages"]

    entries = [{"Id": str(i), "ReceiptHandle": m["ReceiptHandle"]} for i, m in enumerate(msgs)]
    assert sqs.delete_message_batch(QUEUE, entries)["Failed"] == []
    assert sqs.pending_count == 0


def test_send_message_aterriza_en_la_dlq_con_su_razon(tmp_path: Path) -> None:
    dlq = tmp_path / "dlq"
    sqs = SpoolSqsClient([tmp_path / "gw"], dlq)
    sqs.send_message(
        QUEUE,
        MessageBody='{"x": 1}',
        MessageAttributes={"reason": {"DataType": "String", "StringValue": "unknown principal"}},
    )
    assert sqs.dlq_count == 1
    body = json.loads(next(dlq.glob("*.json")).read_text())
    assert body["reason"] == "unknown principal"


def test_varios_gabinetes_se_intercalan_en_una_sola_cola(tmp_path: Path) -> None:
    """Los 3 gabinetes publican a la misma cola de eventos, como en IoT Core."""
    dirs = []
    for gw in ("gw-sim-0001", "gw-sim-0002", "gw-sim-0003"):
        d = tmp_path / gw
        t = SpoolMqttTransport(d, thing=gw)
        t.connect()
        t.publish("takab/events", json.dumps({"gw": gw}).encode())
        dirs.append(d)

    sqs = SpoolSqsClient(dirs, tmp_path / "dlq")
    principals = {
        json.loads(m["Body"])["meta_principal"] for m in sqs.receive_message(QUEUE, 10)["Messages"]
    }
    assert principals == {"gw-sim-0001", "gw-sim-0002", "gw-sim-0003"}


def test_un_mensaje_no_borrado_vuelve_a_la_cola(spool: Path) -> None:
    """RETRY del handler ⇒ el mensaje reaparece. Es EXACTAMENTE lo que salva a un
    `ActuatorAck` que llega antes que su `LocalEvent` (el orden en que el edge los
    publica): sin visibility timeout se perdería para siempre."""
    t = _transport(spool)
    t.publish("takab/acks", b'{"n": 1}')
    sqs = SpoolSqsClient([spool], spool.parent / "dlq", visibility_timeout_s=0.05)

    assert len(sqs.receive_message(QUEUE)["Messages"]) == 1
    assert sqs.receive_message(QUEUE)["Messages"] == []  # invisible…
    time.sleep(0.08)
    assert len(sqs.receive_message(QUEUE)["Messages"]) == 1  # …y vuelve
    assert sqs.pending_count == 1  # sigue en la cola: nadie lo borró


def test_tras_max_receives_el_mensaje_cae_a_la_dlq(spool: Path) -> None:
    """Sin redrive policy, un mensaje que siempre falla giraría eternamente y la
    demo se colgaría en vez de fallar ruidosamente."""
    t = _transport(spool)
    t.publish("takab/acks", b'{"n": 1}')
    sqs = SpoolSqsClient([spool], spool.parent / "dlq", visibility_timeout_s=0.0, max_receives=3)

    for _ in range(3):
        assert len(sqs.receive_message(QUEUE)["Messages"]) == 1  # nunca se borra
    assert sqs.receive_message(QUEUE)["Messages"] == []  # 4ª entrega: a la DLQ
    assert sqs.dlq_count == 1
    assert sqs.pending_count == 0
    body = json.loads(next((spool.parent / "dlq").glob("*.json")).read_text())
    assert "maxReceiveCount" in body["reason"]


def test_archive_conserva_copia_para_reentrega(tmp_path: Path) -> None:
    """C3 prueba idempotencia RE-ENTREGANDO el LocalEvent archivado byte-idéntico:
    el archive debe conservar sólo los topics pedidos y sobrevivir al borrado de la
    cola (el consumer borra de la cola, no del archive)."""
    spool = tmp_path / "gw"
    archive = tmp_path / "sent_events"
    t = SpoolMqttTransport(spool, thing="gw", archive_dir=archive, archive_topics=("takab/events",))
    t.connect()
    t.publish("takab/events", json.dumps({"event_id": "e1"}).encode())
    t.publish("takab/health", b'{"x": 1}')  # NO se archiva (topic no pedido)

    archivados = list(archive.glob("*.json"))
    assert len(archivados) == 1
    assert json.loads(archivados[0].read_text())["event_id"] == "e1"

    # El consumer drena la cola…
    sqs = SpoolSqsClient([spool], tmp_path / "dlq")
    for m in sqs.receive_message(QUEUE, 10)["Messages"]:
        sqs.delete_message(QUEUE, m["ReceiptHandle"])
    assert sqs.pending_count == 0
    # …y el archive sigue intacto para re-entregar.
    assert len(list(archive.glob("*.json"))) == 1


def test_sin_archive_no_escribe_copias(tmp_path: Path) -> None:
    spool = tmp_path / "gw"
    t = SpoolMqttTransport(spool, thing="gw")  # sin archive_dir
    t.connect()
    t.publish("takab/events", b'{"event_id": "e1"}')
    assert not (tmp_path / "sent_events").exists()
