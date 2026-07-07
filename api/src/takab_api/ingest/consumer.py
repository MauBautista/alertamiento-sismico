"""Consumidor SQS → Postgres (T-1.17, G4/G5).

Semántica de entrega (nunca se borra de SQS antes de commitear — hacerlo
sería pérdida de datos):

- OK     → ``q-events`` (per_message_commit=True): commit INMEDIATO por
  mensaje y delete (presupuesto G5 ≤1.5 s). ``q-telemetry``: se acumula el
  batch (≤10), UN commit por batch y ``delete_message_batch`` DESPUÉS del
  commit.
- REJECT → copia a la DLQ con MessageAttributes {reason, original_topic} y
  delete del original (no quema los 5 ciclos de visibilidad). Si el REJECT
  vino del handler, sus escrituras se COMMITEAN antes — EN AMBOS MODOS —
  (evidencia de auditoría, p.ej. ``ingest_reject``: diferirla al commit del
  batch la expondría a un rollback posterior y el original ya no estaría en
  la cola); un REJECT del pipeline no escribe.
- RETRY  → ni delete ni DLQ: el mensaje reaparece al vencer la visibilidad y
  la redrive policy de la cola lo manda a la DLQ tras 5 recepciones.

Errores inesperados (handler/DB) ⇒ rollback + RETRY conservador: los
handlers son idempotentes por PK (G2), reprocesar tras rollback es seguro.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

import boto3
import psycopg

from takab_api.contracts.loader import ContractError, kind_for_topic, validate
from takab_api.contracts.meta import Meta, split_meta
from takab_api.db import pool
from takab_api.settings import Settings

log = logging.getLogger("takab_api.ingest")

OK = "ok"
REJECT = "reject"
RETRY = "retry"

_STATUS_PREFIX = "takab/status/"

# Handler: (conn, payload, meta, ctx) → HandlerResult (duck-typed, ver _outcome).
Handler = Callable[[psycopg.Connection, dict, Meta, Any], Any]


def _outcome(result: Any) -> tuple[str, str]:
    """Normaliza un HandlerResult por duck-typing: ``.outcome`` (o ``.status``)
    como str/StrEnum/Enum con value str, case-insensitive, más ``.reason``.
    Un resultado irreconocible se trata como RETRY (conservador)."""
    raw = getattr(result, "outcome", None)
    if raw is None:
        raw = getattr(result, "status", None)
    raw = getattr(raw, "value", raw)
    status = str(raw).strip().lower() if raw is not None else ""
    reason = str(getattr(result, "reason", "") or "")
    if status not in (OK, REJECT, RETRY):
        return RETRY, f"handler result desconocido: {raw!r}"
    return status, reason


class SqsConsumer:
    """Worker de una cola SQS de ingesta; conexión DB de larga vida con
    reconexión por backoff (``db.pool.with_retry``)."""

    def __init__(
        self,
        queue_url: str,
        dlq_url: str,
        handler_router: Mapping[str, Handler],
        registry: Any,
        conn_factory: Callable[[], psycopg.Connection],
        settings: Settings,
        per_message_commit: bool,
        *,
        sqs_client: Any | None = None,
        wait_time_s: int = 20,
    ) -> None:
        self._queue_url = queue_url
        self._dlq_url = dlq_url
        self._router = handler_router
        self._registry = registry
        self._conn_factory = conn_factory
        self._per_message_commit = per_message_commit
        self._wait_time_s = wait_time_s
        self._sqs = sqs_client or boto3.client("sqs", region_name=settings.aws_region)
        self._conn: psycopg.Connection | None = None
        self._stop = threading.Event()

    # ------------------------------------------------------------------ loop

    def run(self) -> None:
        """Consume hasta ``stop()``; el batch en curso siempre se termina
        (commit incluido) antes de salir — cierre gracioso SIGTERM/SIGINT."""
        while not self._stop.is_set():
            try:
                self.process_once()
            except psycopg.OperationalError:
                # with_retry ya agotó su backoff; pausa breve y de nuevo.
                log.exception("DB no disponible; se reintenta el ciclo")
                time.sleep(1.0)
            except Exception:
                log.exception("error inesperado en el ciclo de consumo")
                time.sleep(1.0)
        self._close()

    def stop(self) -> None:
        """Solicita cierre gracioso (idempotente, seguro desde señales)."""
        self._stop.set()

    def process_once(self) -> dict[str, Any]:
        """Recibe y procesa un batch (≤10 mensajes); devuelve las métricas."""
        # DB PRIMERO: recibir con la DB caída arrancaría el reloj de visibilidad
        # y quemaría receives del maxReceiveCount (mensajes válidos → DLQ).
        self._ensure_conn()
        resp = self._sqs.receive_message(
            QueueUrl=self._queue_url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=self._wait_time_s,
        )
        messages = resp.get("Messages", [])
        stats: dict[str, Any] = {
            "queue": self._queue_url.rsplit("/", 1)[-1],
            "n": len(messages),
            "n_ok": 0,
            "n_reject": 0,
            "n_retry": 0,
            "lag_max_s": None,
        }
        if not messages:
            return stats

        pending: list[dict] = []  # OKs de telemetry a la espera del commit de batch
        for msg in messages:
            try:
                conn = self._ensure_conn()
                outcome, reason, meta, handler_ran = self._handle_message(conn, msg["Body"])
                self._track_lag(stats, meta)
                if outcome == OK:
                    if self._per_message_commit:
                        conn.commit()  # G5: durable antes de borrar
                        self._delete_message(msg)
                    else:
                        pending.append(msg)
                    stats["n_ok"] += 1
                elif outcome == REJECT:
                    # REJECT del handler puede dejar evidencia (audit de rechazo
                    # de identidad): se COMMITEA YA, en ambos modos, porque el
                    # original se borra de la cola — diferir al commit del batch
                    # perdería la evidencia ante un rollback posterior. En modo
                    # batch esto también commitea los pending (inocuo: G2).
                    if handler_ran:
                        conn.commit()
                    elif self._per_message_commit:
                        conn.rollback()  # defensivo
                    self._send_to_dlq(msg, reason, meta)
                    self._delete_message(msg)
                    stats["n_reject"] += 1
                else:  # RETRY: ni delete ni DLQ; redrive → DLQ tras 5 recepciones
                    if self._per_message_commit:
                        conn.rollback()
                    log.warning("RETRY: %s", reason or "sin razón")
                    stats["n_retry"] += 1
            except psycopg.OperationalError:
                # DB caída a mitad de batch: se pierde lo no commiteado; los
                # pending se reentregan y reprocesan idempotentemente (G2).
                log.exception("fallo operacional de DB; el batch se reentrega")
                stats["n_retry"] += 1 + len(pending)
                stats["n_ok"] -= len(pending)
                pending.clear()
                self._drop_conn()
            except Exception:
                log.exception("error inesperado procesando mensaje; RETRY conservador")
                stats["n_retry"] += 1 + len(pending)
                stats["n_ok"] -= len(pending)
                pending.clear()
                self._safe_rollback()

        if pending:
            try:
                self._ensure_conn().commit()  # primero durable…
                if pending:
                    self._delete_batch(pending)  # …luego borrar. NUNCA al revés.
            except psycopg.OperationalError:
                log.exception("commit de batch falló; los mensajes se reentregan")
                stats["n_retry"] += len(pending)
                stats["n_ok"] -= len(pending)
                self._drop_conn()

        log.info(json.dumps(stats, default=str))
        return stats

    # ------------------------------------------------------------- pipeline

    def _handle_message(
        self, conn: psycopg.Connection, body: str
    ) -> tuple[str, str, Meta | None, bool]:
        """json → split_meta → kind → validate → resolve → identidad → handler.

        Devuelve (outcome, reason, meta, handler_ran): el flag distingue los
        REJECT del pipeline (sin escrituras) de los del handler (que pueden
        dejar evidencia auditable que hay que commitear).
        """
        try:
            raw = json.loads(body)
        except ValueError:
            return REJECT, "json inválido", None, False
        if not isinstance(raw, dict):
            return REJECT, "el payload no es un objeto JSON", None, False

        payload, meta = split_meta(raw)
        if not meta.topic:
            return REJECT, "sin meta_topic", meta, False
        try:
            kind = kind_for_topic(meta.topic)
            validate(kind, payload)
        except ContractError as exc:
            return REJECT, str(exc), meta, False

        if not meta.principal:
            return REJECT, "sin meta_principal", meta, False
        ctx = self._registry.resolve(meta.principal)
        if ctx is None:
            return REJECT, "unknown principal", meta, False
        # Identidad a nivel de topic: nadie publica el status de OTRO thing.
        # El cross-check de campos del payload vive en cada handler (G4).
        if kind == "status" and meta.topic.removeprefix(_STATUS_PREFIX) != meta.principal:
            return REJECT, "principal/topic mismatch", meta, False

        handler = self._router.get(kind)
        if handler is None:
            return RETRY, f"sin handler para {kind!r}", meta, False
        return *_outcome(handler(conn, payload, meta, ctx)), meta, True

    # ------------------------------------------------------------------ sqs

    def _send_to_dlq(self, msg: dict, reason: str, meta: Meta | None) -> None:
        topic = (meta.topic if meta else None) or "unknown"
        self._sqs.send_message(
            QueueUrl=self._dlq_url,
            MessageBody=msg["Body"],
            MessageAttributes={
                "reason": {"DataType": "String", "StringValue": (reason or "unknown")[:256]},
                "original_topic": {"DataType": "String", "StringValue": topic[:256]},
            },
        )

    def _delete_message(self, msg: dict) -> None:
        self._sqs.delete_message(QueueUrl=self._queue_url, ReceiptHandle=msg["ReceiptHandle"])

    def _delete_batch(self, msgs: list[dict]) -> None:
        entries = [{"Id": str(i), "ReceiptHandle": m["ReceiptHandle"]} for i, m in enumerate(msgs)]
        resp = self._sqs.delete_message_batch(QueueUrl=self._queue_url, Entries=entries)
        failed = resp.get("Failed", [])
        if failed:
            # Ya commiteado: la reentrega se resuelve por idempotencia (G2).
            log.warning("delete_message_batch con %d fallos; reentrega idempotente", len(failed))

    # ------------------------------------------------------------------- db

    def _ensure_conn(self) -> psycopg.Connection:
        if self._conn is None or self._conn.closed:
            self._conn = pool.with_retry(self._conn_factory)
        return self._conn

    def _safe_rollback(self) -> None:
        if self._conn is not None and not self._conn.closed:
            try:
                self._conn.rollback()
            except psycopg.Error:
                self._drop_conn()

    def _drop_conn(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except psycopg.Error:
                pass
        self._conn = None

    def _close(self) -> None:
        self._drop_conn()

    # ---------------------------------------------------------------- stats

    @staticmethod
    def _track_lag(stats: dict[str, Any], meta: Meta | None) -> None:
        if meta is None or meta.ts_iot is None:
            return
        lag = (datetime.now(tz=UTC) - meta.ts_iot).total_seconds()
        prev = stats["lag_max_s"]
        stats["lag_max_s"] = lag if prev is None else max(prev, lag)
