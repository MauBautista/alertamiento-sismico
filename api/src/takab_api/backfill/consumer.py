"""Consumer de ``q-backfill`` (T-1.25): grants + objetos S3.

La cola recibe DOS familias de mensajes y se discrimina por forma:
- **backfill_request** (IoT Rule, con ``meta_*``): → grant service.
- **S3 ObjectCreated** (notificación del bucket transfer prefix ``backfill/``
  y del bucket evidence prefix ``evidence/``): → ingesta del objeto.

Semántica SQS espejo de ``ingest.SqsConsumer``: commit ANTES de borrar; REJECT
⇒ DLQ + borrar; RETRY ⇒ ni borrar ni DLQ (redrive a DLQ tras maxReceiveCount);
el reproceso es idempotente (PK/ON CONFLICT). El ``s3:TestEvent`` de la
configuración de notificaciones se descarta en silencio.

[T-2.139] **Un fallo transitorio de base tampoco es un RETRY aquí.** `T-2.132`
arregló eso en la ingesta y dejó a este worker fuera **con la razón del orden**:
sin política de reintento, ponerle un tope convertiría cada bloqueo en una
recepción quemada. Medido sobre este consumidor tal como estaba, con un mensaje
**válido** y la redrive real (``maxReceiveCount = 5``):

===================  =====================  ====  =======  ================
``55P03`` seguidos   Recepciones (máx 5)    DLQ   Commits  Conexión tirada
===================  =====================  ====  =======  ================
3                    4                      0     1        sí
5                    5                      1     0        sí
===================  =====================  ====  =======  ================

Y el daño es **más caro que en la ingesta**: lo que se reentrega no es un
feature de 1 s, es el spool entero de una caída. La pasada representativa
—900 s de spool, que es el umbral exacto a partir del cual el edge elige la ruta
S3— son **90 líneas NDJSON, 3600 filas, 0.88 s** contra Postgres real. Cada
recepción quemada es esa pasada repetida, y a la quinta el objeto se va a la DLQ
por un lock que ya había cedido.
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
from takab_api.db.transient import (
    TRANSIENT_SQLSTATES,
    TransientPolicy,
    TransitorioAgotado,
    reintentar_en_el_sitio,
)
from takab_api.ingest.handlers import Outcome
from takab_api.ingest.registry import Registry
from takab_api.settings import Settings

log = logging.getLogger("takab_api.backfill")

__all__ = ["TRANSIENT_SQLSTATES", "BACKFILL_TRANSIENT_POLICY", "BackfillConsumer"]

#: [T-2.139] El presupuesto de reintento de ESTA cola, que no es el de la
#: ingesta y no lo es por dos razones medidas — no por gusto de tener otro número.
#:
#: · **Por arriba manda su propio `VisibilityTimeout`: 300 s**, 10× el de
#:   ``q-events``. Leído del Terraform real por un test, no copiado aquí.
#: · **Y hay un segundo término que en la ingesta no existe.** Allí una pasada
#:   son microsegundos, así que «presupuesto» ≈ «tiempo total». Aquí no: cuando
#:   el presupuesto vence todavía queda por delante **una pasada entera** —el
#:   último intento rehace el objeto desde S3—. Lo que tiene que caber en la
#:   visibilidad es la SUMA::
#:
#:       presupuesto + pasada  <  VisibilityTimeout
#:          120 s   +  0.88 s  <      300 s
#:
#:   con la pasada medida sobre el objeto representativo (900 s de spool = el
#:   umbral a partir del cual el edge elige S3: 90 líneas, 3600 filas). El
#:   alargue en vuelo cubre esa misma suma o el mensaje se escaparía a mitad.
#: · **Por qué 120 s y no 20.** Rendirse aquí no cuesta un feature: cuesta la
#:   pasada entera otra vez, más una lectura de S3. Con 10× de visibilidad para
#:   gastar, esperar sale barato y abandonar sale caro — el reparto opuesto al de
#:   la ingesta, donde el mensaje siguiente pisa los talones al anterior.
#: · **El respiro al rendirse es la visibilidad ENTERA de la cola.** Un lock que
#:   no cedió en dos minutos no cede en cinco segundos, y las cinco recepciones
#:   de este mensaje valen 25 minutos de trabajo rehecho.
BACKFILL_TRANSIENT_POLICY = TransientPolicy(
    budget_s=120.0,
    base_delay_s=0.5,
    max_delay_s=10.0,
    inflight_visibility_s=240,
    giveup_visibility_s=300,
)


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
        transient_policy: TransientPolicy | None = None,
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
        self._transient = transient_policy or BACKFILL_TRANSIENT_POLICY

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
        stats = {
            "n": len(messages),
            "n_ok": 0,
            "n_reject": 0,
            "n_retry": 0,
            # [T-2.139] Reintentos EN EL SITIO: cuestan latencia, no datos. Lo
            # que se mira aquí es si esta cifra crece sin que crezca `n_retry`.
            "n_lock_retries": 0,
        }
        for msg in messages:
            try:
                outcome, reason = self._reintentando(
                    lambda m=msg: self._handle(m["Body"]), [msg], stats
                )
            except TransitorioAgotado:
                # [T-2.139] El bloqueo no cedió dentro del presupuesto: deja de
                # ser «transitorio». El objeto sigue siendo bueno, así que ni DLQ
                # ni delete — pero tampoco se tira la conexión: está sana.
                # Vuelve a la cola con el respiro de una visibilidad entera.
                log.exception("bloqueo persistente; el objeto vuelve a la cola con respiro")
                self._safe_rollback()
                self._cambiar_visibilidad([msg], self._transient.giveup_visibility_s, "respiro")
                stats["n_retry"] += 1
                continue
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

    # ------------------------------------------- reintento transitorio (T-2.139)

    def _reintentando[T](
        self, accion: Callable[[], T], en_vuelo: list[dict], stats: dict[str, int]
    ) -> T:
        """Ejecuta ``accion`` reintentando EN EL SITIO mientras la base esté ocupada.

        El bucle es el compartido de ``db/transient.py`` — el mismo censo de
        SQLSTATE y la misma palanca que la ingesta: SQS solo cuenta recepciones
        **al recibir**, así que todos los intentos caben dentro de la que ya se
        gastó, siempre que se sostenga la invisibilidad mientras duran.

        **Lo que aquí no hace falta y en la ingesta sí:** el gancho ``rehacer``.
        En el modo batch de ``ingest`` el rollback se lleva por delante el
        trabajo de mensajes que la acción reintentada NO vuelve a tocar, y hay
        que reponerlos a mano. Aquí la acción **es** la pasada entera —vuelve a
        leer el objeto de S3 y a reinsertar cada línea—, así que se repone sola.
        Y es seguro por lo mismo que lo es la reentrega: la re-ingesta del mismo
        objeto deja **cero deltas** (PK ``(ts, sensor_id, channel)`` +
        ``ON CONFLICT``). Lo caro no es la corrección, es el tiempo — por eso el
        presupuesto de esta cola cuenta con una pasada de más.
        """

        def anotar() -> None:
            stats["n_lock_retries"] += 1

        return reintentar_en_el_sitio(
            accion,
            policy=self._transient,
            # La transacción queda ABORTADA tras un 55P03: sin este rollback, el
            # siguiente intento fallaría por «current transaction is aborted».
            rollback=self._safe_rollback,
            prolongar=lambda s: self._cambiar_visibilidad(en_vuelo, s, "reintento"),
            anotar=anotar,
        )

    def _cambiar_visibilidad(self, msgs: list[dict], segundos: int, motivo: str) -> None:
        """Ajusta la invisibilidad de los mensajes EN VUELO.

        Best-effort a propósito: si la llamada falla, lo peor que pasa es que el
        mensaje se haga visible antes de tiempo y alguien reprocese el objeto —
        idempotente, a costa de una recepción y de una pasada. Convertir ese
        fallo en excepción cambiaría un contratiempo de coste conocido por un
        objeto sin ingerir, que es peor.

        ⚠️ Requiere ``sqs:ChangeMessageVisibility`` en el rol de los workers —
        el permiso que `T-2.132` descubrió que faltaba. Sin él la llamada da
        ``AccessDenied``, el mensaje se hace visible a mitad del reintento y otro
        worker gasta justo la recepción que se estaba ahorrando: el arreglo
        entero queda decorativo.
        """
        for m in msgs:
            try:
                self._sqs.change_message_visibility(
                    QueueUrl=self._queue_url,
                    ReceiptHandle=m["ReceiptHandle"],
                    VisibilityTimeout=segundos,
                )
            except Exception:  # noqa: BLE001 - ver docstring: es best-effort
                log.warning("no se pudo ajustar la visibilidad (%s); se sigue", motivo)

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
        # `closed` también, como en la ingesta: desde `T-2.139` esto se llama en
        # cada reintento y hacer rollback sobre una conexión ya cerrada tiraría
        # una excepción distinta justo donde se está intentando recuperar.
        if self._conn is not None and not self._conn.closed:
            try:
                self._conn.rollback()
            except psycopg.Error:
                self._drop_conn()

    def _close(self) -> None:
        self._drop_conn()
