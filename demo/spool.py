"""Sustituto en disco de **IoT Core + SQS** para la demo del hito de Fase 1.

Es el ÚNICO tramo del sistema que la demo local sustituye. Todo lo demás
—supervisor del edge, reglas, actuadores, `SqsConsumer`, handlers de ingesta,
`IncidentEngine`, NOTIFY/WS, consola— es el código de producción.

Dos mitades, ambas SOLO stdlib para que las importen los dos venv (edge y api):

- ``SpoolMqttTransport``: implementa el ``MqttTransport`` del edge. En vez de
  publicar por mTLS a IoT Core, escribe un archivo JSON por mensaje **enriquecido
  igual que la IoT Rule** (``meta_principal`` = thing name del certificado,
  ``meta_topic``, ``meta_ts_iot``). ``go_offline()`` modela la caída de WAN: el
  próximo ``connect()`` falla, exactamente como el ``FakeMqttTransport`` de los tests.

- ``SpoolSqsClient``: habla el dialecto de boto3 que ``SqsConsumer`` consume
  (``receive_message`` / ``delete_message`` / ``delete_message_batch`` /
  ``send_message`` para la DLQ) leyendo esos archivos. Así el puente de la demo
  NO es un handler a mano: es el consumer REAL.

Orden de entrega: los archivos se nombran con un contador monótono por gabinete,
así que ordenar por nombre reproduce el orden de publicación (lo que el criterio
de "cero pérdida / cero duplicados" necesita observar tras reconectar).
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

# Claves que inyecta la IoT Rule real (T-1.15). El consumer las separa con
# `split_meta` ANTES de validar contra el schema, así que deben venir aquí.
META_PRINCIPAL = "meta_principal"
META_TOPIC = "meta_topic"
META_TS_IOT = "meta_ts_iot"


def _atomic_write(path: Path, body: str) -> None:
    """Escribe y renombra: el lector nunca ve un archivo a medias."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, path)


class SpoolMqttTransport:
    """``MqttTransport`` que deja los mensajes en un directorio (≡ IoT Core).

    ``thing`` es el nombre del thing IoT = ``meta_principal``. En el sistema real
    lo inyecta la IoT Rule desde el certificado X.509 y por eso NO es falsificable;
    aquí lo fija el gabinete que arranca, que es quien tendría el certificado.
    """

    def __init__(
        self,
        spool_dir: str | Path,
        thing: str,
        *,
        online: bool = True,
        archive_dir: str | Path | None = None,
        archive_topics: tuple[str, ...] = (),
    ) -> None:
        self.dir = Path(spool_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.thing = thing
        self._online = online
        self._connected = False
        self._seq = 0
        self._lock = threading.Lock()
        self.subscriptions: dict[str, Callable[[str, bytes], None]] = {}
        # Copia inmutable de lo publicado en ciertos topics, para RE-ENTREGAR el
        # mensaje byte-idéntico y probar la idempotencia del pipeline (ON CONFLICT).
        self.archive_dir = Path(archive_dir) if archive_dir else None
        self.archive_topics = set(archive_topics)
        if self.archive_dir:
            self.archive_dir.mkdir(parents=True, exist_ok=True)

    # --- protocolo MqttTransport ------------------------------------------
    def connect(self) -> None:
        if not self._online:
            raise ConnectionError("WAN offline (demo)")
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def publish(self, topic: str, payload: bytes, qos: int = 1, retain: bool = False) -> bool:
        if not self._connected:
            return False  # el CloudConnector encola durablemente; nunca bloquea
        message = json.loads(payload)
        message[META_PRINCIPAL] = self.thing
        message[META_TOPIC] = topic
        message[META_TS_IOT] = int(time.time() * 1000)
        with self._lock:
            self._seq += 1
            name = f"{self._seq:012d}-{uuid.uuid4().hex[:8]}.json"
        body = json.dumps(message)
        _atomic_write(self.dir / name, body)
        if self.archive_dir and topic in self.archive_topics:
            _atomic_write(self.archive_dir / name, body)
        return True

    def subscribe(self, topic: str, callback: Callable[[str, bytes], None]) -> bool:
        if not self._connected:
            return False
        self.subscriptions[topic] = callback
        return True

    @property
    def connected(self) -> bool:
        return self._connected

    # --- palanca de la demo: corte y restauración de la WAN ----------------
    def go_offline(self) -> None:
        """Caída de WAN: se desconecta y el próximo ``connect()`` falla."""
        self._connected = False
        self._online = False

    def go_online(self) -> None:
        self._online = True


class SpoolSqsClient:
    """Cliente boto3-compatible que sirve el spool como si fuera una cola SQS.

    Modela las dos propiedades de SQS de las que depende el consumer REAL:

    - **visibility timeout**: un mensaje entregado queda invisible un rato; si el
      handler devuelve ``RETRY`` (y por tanto NO lo borra), vuelve a la cola. Sin
      esto, un ``ActuatorAck`` que llega antes que su ``LocalEvent`` —el orden en
      que el edge los publica— se perdería para siempre.
    - **redrive policy**: tras ``max_receives`` entregas sin éxito, el mensaje va
      a la DLQ en vez de girar eternamente.
    """

    def __init__(
        self,
        spool_dirs: list[str | Path],
        dlq_dir: str | Path,
        *,
        visibility_timeout_s: float = 0.5,
        max_receives: int = 20,
    ) -> None:
        self.dirs = [Path(d) for d in spool_dirs]
        self.dlq = Path(dlq_dir)
        self.dlq.mkdir(parents=True, exist_ok=True)
        for d in self.dirs:
            d.mkdir(parents=True, exist_ok=True)
        self._visibility_s = visibility_timeout_s
        self._max_receives = max_receives
        self._inflight: dict[str, tuple[Path, float]] = {}  # receipt → (path, visible_at)
        self._receives: dict[str, int] = {}

    def _visible(self, name: str) -> bool:
        entry = self._inflight.get(name)
        return entry is None or entry[1] <= time.monotonic()

    def _pending(self) -> list[Path]:
        """Mensajes por entregar, en orden de publicación dentro de cada gabinete."""
        files: list[Path] = []
        for d in self.dirs:
            files.extend(sorted(p for p in d.glob("*.json") if self._visible(p.name)))
        return files

    def _to_dlq_if_exhausted(self, path: Path) -> bool:
        """True si el mensaje agotó sus entregas y se movió a la DLQ."""
        if self._receives.get(path.name, 0) < self._max_receives:
            return False
        body = path.read_text(encoding="utf-8")
        self.send_message(
            "",
            MessageBody=body,
            MessageAttributes={
                "reason": {"DataType": "String", "StringValue": "maxReceiveCount agotado"}
            },
        )
        path.unlink(missing_ok=True)
        self._inflight.pop(path.name, None)
        return True

    # --- dialecto boto3 ----------------------------------------------------
    def receive_message(
        self, QueueUrl: str, MaxNumberOfMessages: int = 10, WaitTimeSeconds: int = 0, **_: Any
    ) -> dict:
        batch = self._pending()[:MaxNumberOfMessages]
        if not batch and WaitTimeSeconds:
            # Espera corta: el consumer hace long-polling; aquí sólo cedemos CPU.
            time.sleep(min(WaitTimeSeconds, 0.2))
            batch = self._pending()[:MaxNumberOfMessages]
        messages = []
        for path in batch:
            receipt = path.name
            if self._to_dlq_if_exhausted(path):
                continue
            self._receives[receipt] = self._receives.get(receipt, 0) + 1
            self._inflight[receipt] = (path, time.monotonic() + self._visibility_s)
            messages.append(
                {
                    "MessageId": receipt,
                    "ReceiptHandle": receipt,
                    "Body": path.read_text(encoding="utf-8"),
                }
            )
        return {"Messages": messages}

    def delete_message(self, QueueUrl: str, ReceiptHandle: str, **_: Any) -> dict:
        entry = self._inflight.pop(ReceiptHandle, None)
        self._receives.pop(ReceiptHandle, None)
        if entry is not None:
            entry[0].unlink(missing_ok=True)
        return {}

    def delete_message_batch(self, QueueUrl: str, Entries: list[dict], **_: Any) -> dict:
        for entry in Entries:
            self.delete_message(QueueUrl, entry["ReceiptHandle"])
        return {"Failed": []}

    def send_message(self, QueueUrl: str, MessageBody: str, **kwargs: Any) -> dict:
        """DLQ: un REJECT del consumer aterriza aquí, con su razón."""
        attrs = kwargs.get("MessageAttributes", {})
        reason = attrs.get("reason", {}).get("StringValue", "")
        name = f"{uuid.uuid4().hex}.json"
        _atomic_write(self.dlq / name, json.dumps({"reason": reason, "body": MessageBody}))
        return {}

    # --- observabilidad de la demo ----------------------------------------
    @property
    def dlq_count(self) -> int:
        return len(list(self.dlq.glob("*.json")))

    @property
    def pending_count(self) -> int:
        """Mensajes que quedan en la cola (visibles o en vuelo). 0 = todo procesado."""
        return sum(len(list(d.glob("*.json"))) for d in self.dirs)
