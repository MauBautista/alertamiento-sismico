"""Tests del SqsConsumer (T-1.17) con moto y handlers/registry falsos.

La semántica bajo prueba: OK ⇒ commit ANTES de borrar (por mensaje en events,
por batch en telemetry); REJECT ⇒ DLQ con razón + delete del original;
RETRY ⇒ el mensaje permanece en la cola (redrive → DLQ tras 5 recepciones);
SIGTERM ⇒ termina el batch en curso y sale.
"""

from __future__ import annotations

import json
import os
import signal
import time

import boto3
import psycopg
import pytest
from moto import mock_aws

from takab_api.ingest.consumer import SqsConsumer
from takab_api.settings import Settings

REGION = "us-east-2"
PRINCIPAL = "gw-sim-0001"


# ------------------------------------------------------------------- fakes


class Result:
    """HandlerResult mínimo según el contrato duck-typed del consumer
    (mismos atributos que ``handlers.HandlerResult``: outcome + reason)."""

    def __init__(self, outcome: str, reason: str = "") -> None:
        self.outcome = outcome
        self.reason = reason


class FakeConn:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.closed = False
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1
        self.calls.append("commit")

    def rollback(self) -> None:
        self.calls.append("rollback")

    def close(self) -> None:
        self.closed = True


class FakeRegistry:
    def __init__(self, known: tuple[str, ...] = (PRINCIPAL,)) -> None:
        self.known = set(known)
        self.ctx = object()  # centinela: debe llegar tal cual al handler

    def resolve(self, principal: str) -> object | None:
        return self.ctx if principal in self.known else None


class SpySqs:
    """Proxy del cliente moto: registra el orden de llamadas y corta el loop
    (backstop) si ``run()`` no termina solo — el test lo detecta y falla."""

    def __init__(self, client, calls: list[str], max_receives: int = 25) -> None:
        self._client = client
        self.calls = calls
        self.consumer: SqsConsumer | None = None
        self._receives = 0
        self._max = max_receives

    def __getattr__(self, name: str):
        real = getattr(self._client, name)

        def call(**kwargs):
            if name == "receive_message":
                self._receives += 1
                if self._receives > self._max and self.consumer is not None:
                    self.calls.append("backstop")
                    self.consumer.stop()
            if name in ("delete_message", "delete_message_batch", "send_message"):
                self.calls.append(name)
            return real(**kwargs)

        return call


# ---------------------------------------------------------------- fixtures


@pytest.fixture
def sqs():
    with mock_aws():
        yield boto3.client("sqs", region_name=REGION)


@pytest.fixture
def queues(sqs) -> tuple[str, str]:
    """Cola + DLQ con redrive real (maxReceiveCount=5) y visibilidad 0 para
    poder observar los RETRY de inmediato."""
    dlq = sqs.create_queue(QueueName="q-dlq")["QueueUrl"]
    dlq_arn = sqs.get_queue_attributes(QueueUrl=dlq, AttributeNames=["QueueArn"])["Attributes"][
        "QueueArn"
    ]
    q = sqs.create_queue(
        QueueName="q-main",
        Attributes={
            "VisibilityTimeout": "0",
            "RedrivePolicy": json.dumps({"deadLetterTargetArn": dlq_arn, "maxReceiveCount": "5"}),
        },
    )["QueueUrl"]
    return q, dlq


def _consumer(sqs, queues, handler, *, per_message_commit, registry=None, kind="feature_1s"):
    calls: list[str] = []
    spy = SpySqs(sqs, calls)
    conn = FakeConn(calls)
    consumer = SqsConsumer(
        queues[0],
        queues[1],
        {kind: handler},
        registry or FakeRegistry(),
        lambda: conn,
        Settings(),
        per_message_commit,
        sqs_client=spy,
        wait_time_s=0,
    )
    spy.consumer = consumer
    return consumer, conn, calls


def _feature_body(principal: str = PRINCIPAL, **overrides) -> str:
    body = {
        "station": "SIM001",
        "channel": "ENZ",
        "window_start": "2026-07-06T10:00:00+00:00",
        "pga": 0.001,
        "pgv": 0.01,
        "rms": 0.0005,
        "sta_lta": 1.1,
        "meta_principal": principal,
        "meta_topic": "takab/features",
        "meta_ts_iot": int(time.time() * 1000),
    }
    body.update(overrides)
    return json.dumps({k: v for k, v in body.items() if v is not None})


def _n_messages(sqs, url: str) -> int:
    attrs = sqs.get_queue_attributes(QueueUrl=url, AttributeNames=["ApproximateNumberOfMessages"])
    return int(attrs["Attributes"]["ApproximateNumberOfMessages"])


def _dlq_receive(sqs, dlq: str) -> dict:
    resp = sqs.receive_message(QueueUrl=dlq, MessageAttributeNames=["All"])
    assert len(resp.get("Messages", [])) == 1, "se esperaba exactamente 1 mensaje en la DLQ"
    return resp["Messages"][0]


# ------------------------------------------------------------------- tests


def test_valid_message_calls_handler_and_deletes(sqs, queues):
    seen: list[tuple] = []

    def handler(conn, payload, meta, ctx):
        seen.append((conn, payload, meta, ctx))
        return Result("ok")

    registry = FakeRegistry()
    consumer, conn, _ = _consumer(sqs, queues, handler, per_message_commit=True, registry=registry)
    sqs.send_message(QueueUrl=queues[0], MessageBody=_feature_body())

    stats = consumer.process_once()

    assert stats["n_ok"] == 1 and stats["n_reject"] == 0 and stats["n_retry"] == 0
    assert len(seen) == 1
    _, payload, meta, ctx = seen[0]
    assert ctx is registry.ctx
    assert meta.principal == PRINCIPAL and meta.topic == "takab/features"
    # el strip de meta_* ocurre ANTES de validar y de llegar al handler
    assert not any(k.startswith("meta_") for k in payload)
    assert payload["station"] == "SIM001"
    assert conn.commits == 1
    assert _n_messages(sqs, queues[0]) == 0
    assert _n_messages(sqs, queues[1]) == 0


def test_invalid_schema_lands_in_dlq_with_reason(sqs, queues):
    def handler(conn, payload, meta, ctx):  # pragma: no cover - no debe llamarse
        raise AssertionError("el handler no debe ejecutarse con payload inválido")

    consumer, conn, _ = _consumer(sqs, queues, handler, per_message_commit=True)
    sqs.send_message(QueueUrl=queues[0], MessageBody=_feature_body(pga=None))  # sin 'pga'

    stats = consumer.process_once()

    assert stats["n_reject"] == 1
    assert conn.commits == 0
    assert _n_messages(sqs, queues[0]) == 0  # el original se borró
    msg = _dlq_receive(sqs, queues[1])
    attrs = msg["MessageAttributes"]
    assert "pga" in attrs["reason"]["StringValue"]
    assert attrs["original_topic"]["StringValue"] == "takab/features"


def test_malformed_json_lands_in_dlq(sqs, queues):
    consumer, _, _ = _consumer(sqs, queues, lambda *a: Result("ok"), per_message_commit=True)
    sqs.send_message(QueueUrl=queues[0], MessageBody="{esto no es json")

    consumer.process_once()

    msg = _dlq_receive(sqs, queues[1])
    assert msg["MessageAttributes"]["reason"]["StringValue"] == "json inválido"
    assert msg["MessageAttributes"]["original_topic"]["StringValue"] == "unknown"


def test_unknown_principal_lands_in_dlq(sqs, queues):
    def handler(conn, payload, meta, ctx):  # pragma: no cover - no debe llamarse
        raise AssertionError("principal desconocido no debe llegar al handler")

    consumer, _, _ = _consumer(sqs, queues, handler, per_message_commit=True)
    sqs.send_message(QueueUrl=queues[0], MessageBody=_feature_body(principal="gw-evil"))

    consumer.process_once()

    assert _n_messages(sqs, queues[0]) == 0
    msg = _dlq_receive(sqs, queues[1])
    assert msg["MessageAttributes"]["reason"]["StringValue"] == "unknown principal"


def test_status_topic_principal_mismatch_rejected(sqs, queues):
    def handler(conn, payload, meta, ctx):  # pragma: no cover - no debe llamarse
        raise AssertionError("mismatch de identidad no debe llegar al handler")

    consumer, _, _ = _consumer(sqs, queues, handler, per_message_commit=True, kind="status")
    body = json.dumps(
        {
            "status": "offline",
            "meta_principal": PRINCIPAL,
            "meta_topic": "takab/status/gw-otro",
        }
    )
    sqs.send_message(QueueUrl=queues[0], MessageBody=body)

    consumer.process_once()

    msg = _dlq_receive(sqs, queues[1])
    assert msg["MessageAttributes"]["reason"]["StringValue"] == "principal/topic mismatch"


def test_retry_keeps_message_in_queue_and_out_of_dlq(sqs, queues):
    consumer, conn, _ = _consumer(
        sqs, queues, lambda *a: Result("retry", "db glitch"), per_message_commit=True
    )
    sqs.send_message(QueueUrl=queues[0], MessageBody=_feature_body())

    stats = consumer.process_once()

    assert stats["n_retry"] == 1
    assert conn.commits == 0
    # visibilidad 0 ⇒ el mensaje ya es visible otra vez; la DLQ sigue vacía
    # (la redrive policy solo lo movería tras 5 recepciones).
    assert _n_messages(sqs, queues[0]) == 1
    assert _n_messages(sqs, queues[1]) == 0


def test_per_message_commit_commits_before_each_delete(sqs, queues):
    consumer, conn, calls = _consumer(sqs, queues, lambda *a: Result("ok"), per_message_commit=True)
    for _ in range(3):
        sqs.send_message(QueueUrl=queues[0], MessageBody=_feature_body())

    for _ in range(3):  # moto puede repartir el batch en varias recepciones
        if _n_messages(sqs, queues[0]) == 0:
            break
        consumer.process_once()

    assert conn.commits == 3
    relevant = [c for c in calls if c in ("commit", "delete_message")]
    assert relevant == ["commit", "delete_message"] * 3
    assert _n_messages(sqs, queues[0]) == 0


def test_telemetry_batch_single_commit_before_delete_batch(sqs, queues):
    n_handled = 0

    def handler(conn, payload, meta, ctx):
        nonlocal n_handled
        n_handled += 1
        return Result("ok")

    consumer, conn, calls = _consumer(sqs, queues, handler, per_message_commit=False)
    for _ in range(4):
        sqs.send_message(QueueUrl=queues[0], MessageBody=_feature_body())

    batches = 0
    for _ in range(5):
        if _n_messages(sqs, queues[0]) == 0:
            break
        stats = consumer.process_once()
        if stats["n"]:
            batches += 1

    assert n_handled == 4
    assert conn.commits == batches  # UN commit por batch, no por mensaje
    assert "delete_message" not in calls  # solo borrado por batch
    # NUNCA borrar antes de commitear: cada delete_message_batch va precedido
    # por más commits que deletes acumulados hasta ese punto.
    for i, call in enumerate(calls):
        if call == "delete_message_batch":
            assert calls[:i].count("commit") > calls[:i].count("delete_message_batch")
    assert calls.count("delete_message_batch") == batches
    assert _n_messages(sqs, queues[0]) == 0


def test_real_handler_result_contract(sqs, queues):
    """El consumer entiende el HandlerResult REAL de handlers.py (Outcome StrEnum)."""
    from takab_api.ingest import handlers as h

    results = iter([h.OK, h.reject("dato malo permanente")])

    def handler(conn, payload, meta, ctx):
        return next(results)

    consumer, conn, _ = _consumer(sqs, queues, handler, per_message_commit=True)
    for _ in range(2):
        sqs.send_message(QueueUrl=queues[0], MessageBody=_feature_body())

    totals = {"n_ok": 0, "n_reject": 0, "n_retry": 0}
    for _ in range(3):  # moto puede repartir el batch en varias recepciones
        if _n_messages(sqs, queues[0]) == 0:
            break
        stats = consumer.process_once()
        for key in totals:
            totals[key] += stats[key]

    assert totals == {"n_ok": 1, "n_reject": 1, "n_retry": 0}
    # 1 commit del OK + 1 commit del REJECT de handler (preserva su audit)
    assert conn.commits == 2
    msg = _dlq_receive(sqs, queues[1])
    assert msg["MessageAttributes"]["reason"]["StringValue"] == "dato malo permanente"


def test_handler_reject_commits_audit_before_dlq(sqs, queues):
    """Un REJECT del handler commitea sus escrituras (audit) ANTES de la DLQ;
    un REJECT del pipeline (schema, principal) NO commitea (ver commits==0 en
    test_invalid_schema_lands_in_dlq_with_reason)."""
    consumer, conn, calls = _consumer(
        sqs, queues, lambda *a: Result("reject", "identidad falsa"), per_message_commit=True
    )
    sqs.send_message(QueueUrl=queues[0], MessageBody=_feature_body())

    consumer.process_once()

    assert conn.commits == 1
    relevant = [c for c in calls if c in ("commit", "send_message", "delete_message")]
    assert relevant == ["commit", "send_message", "delete_message"]
    _dlq_receive(sqs, queues[1])


def test_batch_handler_reject_commits_audit_before_dlq(sqs, queues):
    """También en modo batch (q-telemetry) la evidencia del REJECT de handler se
    commitea ANTES de copiar a la DLQ y borrar el original: diferirla al commit
    del batch la expondría a un rollback posterior (y el original ya no estaría
    en la cola para reprocesarse)."""
    consumer, conn, calls = _consumer(
        sqs, queues, lambda *a: Result("reject", "identidad falsa"), per_message_commit=False
    )
    sqs.send_message(QueueUrl=queues[0], MessageBody=_feature_body())

    consumer.process_once()

    assert conn.commits == 1
    relevant = [c for c in calls if c in ("commit", "send_message", "delete_message")]
    assert relevant == ["commit", "send_message", "delete_message"]
    _dlq_receive(sqs, queues[1])


def test_db_down_fails_before_receiving(monkeypatch):
    """Con la DB caída, process_once falla ANTES de recibir de SQS: no arranca el
    reloj de visibilidad ni quema receives del maxReceiveCount (un outage de DB
    no convierte mensajes válidos en dead-letters)."""
    monkeypatch.setattr("takab_api.db.pool.with_retry", lambda fn, **kw: fn())

    class _SpyNoDb:
        def __init__(self) -> None:
            self.receives = 0

        def receive_message(self, **kwargs):
            self.receives += 1
            return {"Messages": []}

    spy = _SpyNoDb()

    def factory() -> psycopg.Connection:
        raise psycopg.OperationalError("DB en failover")

    consumer = SqsConsumer(
        "q-url",
        "dlq-url",
        {},
        FakeRegistry(),
        factory,
        Settings(),
        per_message_commit=True,
        sqs_client=spy,
        wait_time_s=0,
    )

    with pytest.raises(psycopg.OperationalError):
        consumer.process_once()

    assert spy.receives == 0  # nada recibido: el mensaje no quema su redrive


def test_sigterm_finishes_batch_and_exits(sqs, queues):
    from takab_api.ingest.__main__ import install_signal_handlers

    seen: list[dict] = []

    def handler(conn, payload, meta, ctx):
        # simula la señal llegando a mitad del batch en curso
        os.kill(os.getpid(), signal.SIGTERM)
        seen.append(payload)
        return Result("ok")

    consumer, conn, calls = _consumer(sqs, queues, handler, per_message_commit=True)
    sqs.send_message(QueueUrl=queues[0], MessageBody=_feature_body())

    old_term = signal.getsignal(signal.SIGTERM)
    old_int = signal.getsignal(signal.SIGINT)
    try:
        install_signal_handlers(consumer)
        consumer.run()  # debe retornar solo: batch terminado + stop por señal
    finally:
        signal.signal(signal.SIGTERM, old_term)
        signal.signal(signal.SIGINT, old_int)

    assert "backstop" not in calls, "run() no salió por la señal; lo cortó el backstop"
    assert len(seen) == 1  # el batch en curso se terminó…
    assert conn.commits == 1  # …con su commit…
    assert _n_messages(sqs, queues[0]) == 0  # …y su delete
    assert conn.closed  # cierre gracioso de la conexión
