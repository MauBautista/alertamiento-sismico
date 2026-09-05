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

from demo.spool import (  # noqa: E402
    SpoolCommandPublisher,
    SpoolMqttTransport,
    SpoolSqsClient,
)

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


# ── [T-5.29] la BAJADA nube→gabinete ────────────────────────────────────────
#
# Hasta esta ficha el arnés era solo edge→nube: `subscribe()` guardaba el
# callback y **nadie lo invocaba nunca**. Por eso la demo no podía guionizar
# nada comandado desde la nube —un simulacro son comandos firmados, uno por
# sitio— y la escena de `T-5.08` se quedó a medias.
#
# Lo que estos contratos protegen es que el transporte **no toque el envelope**:
# el día que entregue el payload pelado, o verifique él, la demo pasaría en verde
# demostrando lo contrario de lo que dice demostrar.


def _con_bajada(
    tmp_path: Path, thing: str = "gw-sim-0001", poll_s: float = 0.0
) -> SpoolMqttTransport:
    """Por defecto SIN hilo de sondeo: el test es el único que entrega.

    Con el hilo vivo, `entregar_pendientes()` compite con él por los mismos
    archivos y devuelve lo que le haya quedado — cuatro tests de este módulo
    fallaban ~20 % de las corridas por eso, y en la suite completa parecía un
    problema de otro. Quien de verdad quiera probar el hilo lo pide.
    """
    t = SpoolMqttTransport(
        tmp_path / "cola" / thing,
        thing=thing,
        downlink_root=tmp_path / "bajada",
        poll_s=poll_s,
    )
    t.connect()
    return t


def test_la_bajada_entrega_el_ENVELOPE_INTACTO(tmp_path: Path) -> None:
    """El transporte es un cable, no un verificador.

    Si entregara `sobre["payload"]["payload"]` —el payload pelado— el dispatcher
    del edge no encontraría firma que verificar y rechazaría todo; si verificara
    él, la demo probaría este archivo en vez del gabinete.
    """
    t = _con_bajada(tmp_path)
    recibido: list[bytes] = []
    t.subscribe("takab/cmd/gw-sim-0001", lambda _topic, raw: recibido.append(raw))

    pub = SpoolCommandPublisher(tmp_path / "bajada")
    sobre = {
        "command_id": "c1",
        "nonce": "n1",
        "ts": "2026-09-04T18:00:00+00:00",
        "sig": "ab" * 32,
        "payload": {"channel": "system", "action": "drill_start"},
    }
    pub.publish("takab/cmd/gw-sim-0001", json.dumps(sobre).encode())

    assert t.entregar_pendientes() == 1
    assert json.loads(recibido[0]) == sobre, "el transporte tocó el envelope firmado"


def test_cada_thing_recibe_SOLO_lo_suyo(tmp_path: Path) -> None:
    """El topic ES la dirección, igual que en IoT Core."""
    uno = _con_bajada(tmp_path, "gw-sim-0001")
    otro = _con_bajada(tmp_path, "gw-sim-0002")
    for t, thing in ((uno, "gw-sim-0001"), (otro, "gw-sim-0002")):
        t.subscribe(f"takab/cmd/{thing}", lambda *_: None)

    pub = SpoolCommandPublisher(tmp_path / "bajada")
    pub.publish("takab/cmd/gw-sim-0002", json.dumps({"payload": {}}).encode())

    assert uno.entregar_pendientes() == 0
    assert otro.entregar_pendientes() == 1


def test_sin_suscripcion_el_comando_SE_QUEDA(tmp_path: Path) -> None:
    """Un gabinete que aún no llegó a suscribirse no pierde su comando.

    Tirarlo convertiría una carrera de arranque en un simulacro que no suena en
    un edificio, y el operador no tendría cómo saberlo.
    """
    t = _con_bajada(tmp_path)
    pub = SpoolCommandPublisher(tmp_path / "bajada")
    pub.publish("takab/cmd/gw-sim-0001", json.dumps({"payload": {}}).encode())

    assert t.entregar_pendientes() == 0
    assert t.pendientes_de_bajada == 1

    t.subscribe("takab/cmd/gw-sim-0001", lambda *_: None)
    assert t.entregar_pendientes() == 1
    assert t.pendientes_de_bajada == 0


def test_entregar_es_CONSUMIR_no_hay_segunda_entrega(tmp_path: Path) -> None:
    t = _con_bajada(tmp_path)
    vistos: list[bytes] = []
    t.subscribe("takab/cmd/gw-sim-0001", lambda _t, raw: vistos.append(raw))
    SpoolCommandPublisher(tmp_path / "bajada").publish(
        "takab/cmd/gw-sim-0001", json.dumps({"payload": {}}).encode()
    )

    assert t.entregar_pendientes() == 1
    assert t.entregar_pendientes() == 0
    assert len(vistos) == 1


def test_con_la_WAN_CAIDA_el_comando_espera_y_baja_al_reconectar(tmp_path: Path) -> None:
    """La bajada cae con el mismo enlace, y la sesión persistente la recupera."""
    t = _con_bajada(tmp_path, poll_s=0.01)  # ESTE sí prueba el hilo
    entregados: list[bytes] = []
    t.subscribe("takab/cmd/gw-sim-0001", lambda _t, raw: entregados.append(raw))

    t.go_offline()
    SpoolCommandPublisher(tmp_path / "bajada").publish(
        "takab/cmd/gw-sim-0001", json.dumps({"payload": {}}).encode()
    )
    time.sleep(0.05)
    assert entregados == [] and t.pendientes_de_bajada == 1

    t.go_online()
    t.connect()
    assert _espera(lambda: len(entregados) == 1), "el comando no bajó al reconectar"


def test_un_callback_que_LANZA_no_mata_la_bajada(tmp_path: Path) -> None:
    """El hilo de bajada es el único enlace: si muere, el gabinete queda sordo
    y en silencio. El del edge no lanza (lo garantiza `on_command`), pero eso
    no puede ser lo único que lo impida."""
    t = _con_bajada(tmp_path)
    llamadas: list[int] = []

    def explota(_topic: str, _raw: bytes) -> None:
        llamadas.append(1)
        raise RuntimeError("mensaje hostil")

    t.subscribe("takab/cmd/gw-sim-0001", explota)
    pub = SpoolCommandPublisher(tmp_path / "bajada")
    for _ in range(2):
        pub.publish("takab/cmd/gw-sim-0001", json.dumps({"payload": {}}).encode())

    assert t.entregar_pendientes() == 2
    assert len(llamadas) == 2, "la excepción del primero se llevó al segundo"


def test_el_contador_de_entregados_es_la_guarda_de_no_vacuidad(tmp_path: Path) -> None:
    """Sin este número, una escena en la que no bajara NADA pasaría en verde."""
    t = _con_bajada(tmp_path)
    assert t.delivered == 0
    t.subscribe("takab/cmd/gw-sim-0001", lambda *_: None)
    SpoolCommandPublisher(tmp_path / "bajada").publish(
        "takab/cmd/gw-sim-0001", json.dumps({"payload": {}}).encode()
    )
    t.entregar_pendientes()
    assert t.delivered == 1


def test_sin_buzon_el_arnes_sigue_funcionando_igual(tmp_path: Path) -> None:
    """La demo de Fase 1 no necesitaba bajada y no puede romperse por añadirla."""
    t = SpoolMqttTransport(tmp_path / "cola", thing="gw-sim-0001")
    t.connect()
    assert t.downlink is None
    assert t.entregar_pendientes() == 0 and t.pendientes_de_bajada == 0
    assert t.publish("takab/events", json.dumps({"event_id": "e1"}).encode()) is True


def _espera(pred, timeout_s: float = 3.0) -> bool:  # noqa: ANN001
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if pred():
            return True
        time.sleep(0.01)
    return False
