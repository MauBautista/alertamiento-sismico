"""Consumer de ``q-backfill`` (T-1.25): grants + objetos S3.

La cola recibe DOS familias de mensajes y se discrimina por forma:
- **backfill_request** (IoT Rule, con ``meta_*``): → grant service.
- **S3 ObjectCreated** (notificación del bucket transfer prefix ``backfill/``
  y del bucket evidence prefix ``evidence/``): → ingesta del objeto.

Semántica SQS espejo de ``ingest.SqsConsumer``: commit ANTES de borrar; REJECT
⇒ DLQ + borrar; RETRY ⇒ ni borrar ni DLQ (redrive a DLQ tras maxReceiveCount);
el reproceso es idempotente (PK/ON CONFLICT). El ``s3:TestEvent`` de la
configuración de notificaciones se descarta en silencio.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.parse
from collections.abc import Callable
from typing import Any

import boto3
import psycopg

from takab_api.backfill.grants import handle_backfill_request
from takab_api.backfill.objects import process_s3_object
from takab_api.commands.publisher import CommandPublisher, IotDataPublisher
from takab_api.contracts.loader import ContractError, kind_for_topic, validate
from takab_api.contracts.meta import split_meta
from takab_api.db import pool
from takab_api.ingest.handlers import Outcome
from takab_api.ingest.registry import Registry
from takab_api.settings import Settings

log = logging.getLogger("takab_api.backfill")


class BackfillConsumer:
    """Worker de la cola de backfill; conexión DB de larga vida con reintento."""

    def __init__(
        self,
        queue_url: str,
        dlq_url: str,
        registry: Registry,
        conn_factory: Callable[[], psycopg.Connection],
        settings: Settings,
        *,
        publisher: CommandPublisher | None = None,
        sqs_client: Any | None = None,
        s3_client: Any | None = None,
        wait_time_s: int = 20,
    ) -> None:
        self._queue_url = queue_url
        self._dlq_url = dlq_url
        self._registry = registry
        self._conn_factory = conn_factory
        self._settings = settings
        self._publisher = publisher if publisher is not None else IotDataPublisher(settings)
        self._sqs = sqs_client or boto3.client("sqs", region_name=settings.aws_region)
        self._s3 = s3_client or boto3.client("s3", region_name=settings.aws_region)
        self._wait_time_s = wait_time_s
        self._conn: psycopg.Connection | None = None
        self._stop = threading.Event()

    # ------------------------------------------------------------------ loop

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                self.process_once()
            except psycopg.OperationalError:
                log.exception("DB no disponible; se reintenta el ciclo")
                time.sleep(1.0)
            except Exception:
                log.exception("error inesperado en el ciclo de backfill")
                time.sleep(1.0)
        self._close()

    def stop(self) -> None:
        self._stop.set()

    def process_once(self) -> dict[str, int]:
        """Recibe y procesa un batch (≤10); devuelve métricas."""
        self._ensure_conn()
        resp = self._sqs.receive_message(
            QueueUrl=self._queue_url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=self._wait_time_s,
        )
        messages = resp.get("Messages", [])
        stats = {"n": len(messages), "n_ok": 0, "n_reject": 0, "n_retry": 0}
        for msg in messages:
            try:
                outcome, reason = self._handle(msg["Body"])
            except psycopg.OperationalError:
                log.exception("fallo de DB; el mensaje se reentrega")
                self._drop_conn()
                stats["n_retry"] += 1
                continue
            except Exception:
                log.exception("error inesperado; RETRY conservador")
                self._safe_rollback()
                stats["n_retry"] += 1
                continue
            if outcome is Outcome.OK:
                self._delete(msg)
                stats["n_ok"] += 1
            elif outcome is Outcome.REJECT:
                self._send_to_dlq(msg, reason)
                self._delete(msg)
                stats["n_reject"] += 1
            else:
                log.warning("RETRY: %s", reason or "sin razón")
                self._safe_rollback()
                stats["n_retry"] += 1
        if messages:
            log.info(json.dumps({"queue": "backfill", **stats}))
        return stats

    # -------------------------------------------------------------- pipeline

    def _handle(self, body: str) -> tuple[Outcome, str]:
        try:
            raw = json.loads(body)
        except ValueError:
            return Outcome.REJECT, "json inválido"
        if not isinstance(raw, dict):
            return Outcome.REJECT, "el mensaje no es un objeto JSON"

        if raw.get("Event") == "s3:TestEvent":
            return Outcome.OK, ""  # saludo de la configuración de notificaciones
        if "Records" in raw:
            return self._handle_s3_records(raw["Records"])
        if raw.get("meta_topic", "").startswith("takab/backfill/request/"):
            return self._handle_request(raw)
        return Outcome.REJECT, "mensaje sin forma conocida (ni S3 ni request)"

    def _handle_request(self, raw: dict) -> tuple[Outcome, str]:
        payload, meta = split_meta(raw)
        try:
            kind = kind_for_topic(meta.topic or "")
            validate(kind, payload)
        except ContractError as exc:
            return Outcome.REJECT, str(exc)
        if not meta.principal:
            return Outcome.REJECT, "sin meta_principal"
        ctx = self._registry.resolve(meta.principal)
        if ctx is None:
            return Outcome.REJECT, "unknown principal"
        ok, reason = handle_backfill_request(payload, meta, ctx, self._publisher, self._settings)
        return (Outcome.OK, "") if ok else (Outcome.REJECT, reason)

    def _handle_s3_records(self, records: list) -> tuple[Outcome, str]:
        conn = self._ensure_conn()
        for record in records:
            if not isinstance(record, dict) or "s3" not in record:
                return Outcome.REJECT, "record S3 malformado"
            bucket = record["s3"]["bucket"]["name"]
            key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])
            result = process_s3_object(
                conn, bucket, key, self._registry, self._settings, s3_client=self._s3
            )
            if result.outcome is not Outcome.OK:
                return result.outcome, result.reason
        return Outcome.OK, ""

    # ------------------------------------------------------------------- sqs

    def _delete(self, msg: dict) -> None:
        self._sqs.delete_message(QueueUrl=self._queue_url, ReceiptHandle=msg["ReceiptHandle"])

    def _send_to_dlq(self, msg: dict, reason: str) -> None:
        self._sqs.send_message(
            QueueUrl=self._dlq_url,
            MessageBody=msg["Body"],
            MessageAttributes={
                "reject_reason": {"DataType": "String", "StringValue": reason[:256] or "?"}
            },
        )

    # -------------------------------------------------------------------- db

    def _ensure_conn(self) -> psycopg.Connection:
        if self._conn is None or self._conn.closed:
            self._conn = pool.with_retry(self._conn_factory)
        return self._conn

    def _drop_conn(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except psycopg.Error:
                pass
        self._conn = None

    def _safe_rollback(self) -> None:
        if self._conn is not None:
            try:
                self._conn.rollback()
            except psycopg.Error:
                self._drop_conn()

    def _close(self) -> None:
        self._drop_conn()
