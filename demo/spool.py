"""Sustituto en disco de **IoT Core + SQS** para la demo del hito de Fase 1.

Es el ÚNICO tramo del sistema que la demo local sustituye. Todo lo demás
—supervisor del edge, reglas, actuadores, `SqsConsumer`, handlers de ingesta,
`IncidentEngine`, NOTIFY/WS, consola— es el código de producción.

Tres piezas, todas SOLO stdlib para que las importen los dos venv (edge y api):

- ``SpoolMqttTransport``: implementa el ``MqttTransport`` del edge. En vez de
  publicar por mTLS a IoT Core, escribe un archivo JSON por mensaje **enriquecido
  igual que la IoT Rule** (``meta_principal`` = thing name del certificado,
  ``meta_topic``, ``meta_ts_iot``). ``go_offline()`` modela la caída de WAN: el
  próximo ``connect()`` falla, exactamente como el ``FakeMqttTransport`` de los tests.

- ``SpoolSqsClient``: habla el dialecto de boto3 que ``SqsConsumer`` consume
  (``receive_message`` / ``delete_message`` / ``delete_message_batch`` /
  ``send_message`` para la DLQ) leyendo esos archivos. Así el puente de la demo
  NO es un handler a mano: es el consumer REAL.

- ``SpoolCommandPublisher``: [T-5.29] **la bajada**. Implementa el
  ``CommandPublisher`` de la nube (``takab_api.commands.publisher``) y deja el
  envelope FIRMADO en el buzón del thing; el transporte de arriba lo entrega a la
  suscripción del edge, y ahí lo recibe el ``CommandDispatcher`` REAL, que
  verifica HMAC + nonce + ventana antes de tocar nada.

**Por qué la bajada faltaba y por qué importa.** Hasta `T-5.29` este arnés era
SOLO edge→nube, así que la demo no podía guionizar nada comandado desde la nube:
un simulacro son comandos firmados nube→gabinete, uno por sitio, y también lo son
la actuación por quórum y la sincronización de config. La escena de simulacro de
`T-5.08` se quedó a medias por esto.

**Lo que NO se salta: la firma.** Un transporte de bajada que entregara el payload
sin envelope, o que verificara él mismo, probaría lo contrario de lo que hay que
probar. Aquí el archivo viaja tal cual lo firmó la nube y el único que decide si
se ejecuta es el dispatcher del edge — el mismo código que corre en el Pi.

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


#: [T-5.29] Nombre del buzón de bajada de un thing dentro del directorio raíz.
#: Un directorio por thing, igual que un topic por thing en IoT Core.
def downlink_dir(root: str | Path, thing: str) -> Path:
    """Buzón de bajada de ese gabinete. Lo crean los dos lados, sin coordinarse."""
    d = Path(root) / thing
    d.mkdir(parents=True, exist_ok=True)
    return d


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
        downlink_root: str | Path | None = None,
        poll_s: float = 0.05,
    ) -> None:
        self.dir = Path(spool_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.thing = thing
        self._online = online
        self._connected = False
        self._seq = 0
        self._lock = threading.Lock()
        self.subscriptions: dict[str, Callable[[str, bytes], None]] = {}
        # [T-5.29] Bajada. `None` = gabinete sin buzón: la demo de Fase 1 no lo
        # necesitaba y el arnés sigue funcionando exactamente igual sin él.
        self.downlink = downlink_dir(downlink_root, thing) if downlink_root else None
        self._poll_s = poll_s
        self._poller: threading.Thread | None = None
        self._stop = threading.Event()
        #: Cuántos mensajes de bajada se han ENTREGADO a una suscripción. Lo lee
        #: la guarda de no-vacuidad del guion: sin este número, una escena en la
        #: que no llegara ningún comando pasaría en verde sin haber probado nada.
        self.delivered = 0
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
        self._arrancar_bajada()

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

    # --- [T-5.29] bajada nube→gabinete -------------------------------------
    def _arrancar_bajada(self) -> None:
        """Hilo que vacía el buzón. Idempotente: reconectar no duplica hilos.

        `poll_s <= 0` lo deja SIN arrancar, y entonces la única forma de entregar
        es pedirlo con `entregar_pendientes()`. No es un capricho de test: con el
        hilo vivo, quien llama compite con él por los mismos archivos y el número
        que recibe de vuelta depende de quién ganó. Medido: cuatro tests de este
        módulo fallaban ~20 % de las veces por eso, cada vez uno distinto.
        """
        if self.downlink is None or self._poll_s <= 0:
            return
        if self._poller is not None and self._poller.is_alive():
            return
        self._stop.clear()
        self._poller = threading.Thread(target=self._bajada, daemon=True, name="spool-downlink")
        self._poller.start()

    def _bajada(self) -> None:
        while not self._stop.is_set():
            if self._connected:
                self.entregar_pendientes()
            self._stop.wait(self._poll_s)

    def entregar_pendientes(self) -> int:
        """Entrega lo que haya en el buzón a la suscripción de su topic.

        Devuelve cuántos entregó. Se expone además del hilo para poder pedir la
        entrega sin reloj que esperar. **Solo es determinista si el hilo no está
        corriendo** (`poll_s <= 0`): con el hilo vivo, los dos consumen del mismo
        buzón y el número que devuelve depende de cuál llegó antes al archivo.

        **Entregar es consumir**, igual que un mensaje QoS1 que el cliente
        confirma: el archivo se borra ANTES de invocar el callback, para que un
        despacho que tarde no se convierta en una segunda entrega. Y el
        dispatcher del edge es idempotente por nonce de todas formas: un replay
        lo rechazaría, que es lo que debe pasar.

        Sin suscripción para ese topic el archivo se QUEDA: el gabinete todavía
        no ha llegado a suscribirse, y tirarlo sería perder un comando por una
        carrera de arranque.
        """
        if self.downlink is None or not self._connected:
            return 0
        entregados = 0
        for path in sorted(self.downlink.glob("*.json")):
            # Se re-comprueba POR ARCHIVO, no solo al entrar. El enlace puede
            # caerse a mitad del lote, y con la comprobación únicamente en el
            # bucle del hilo había una carrera real: el hilo entraba con la WAN
            # arriba, `go_offline()` corría en medio y el comando bajaba igual.
            # Salió en la suite completa, no en el módulo aislado.
            if not self._connected:
                break
            try:
                sobre = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue  # escritura a medias: el siguiente barrido lo verá entero
            topic = sobre.get(META_TOPIC, "")
            callback = self.subscriptions.get(topic)
            if callback is None:
                continue
            path.unlink(missing_ok=True)
            entregados += 1
            with self._lock:
                self.delivered += 1
            # El callback del edge JAMÁS lanza (lo garantiza `on_command`), pero
            # este hilo tampoco puede morir por sorpresa: se queda sin bajada el
            # gabinete entero y en silencio.
            try:
                callback(topic, json.dumps(sobre["payload"]).encode())
            except Exception:  # noqa: BLE001
                pass
        return entregados

    @property
    def pendientes_de_bajada(self) -> int:
        """Comandos en el buzón sin entregar (p. ej. con la WAN caída)."""
        return 0 if self.downlink is None else len(list(self.downlink.glob("*.json")))

    # --- palanca de la demo: corte y restauración a WAN --------------------
    def go_offline(self) -> None:
        """Caída de WAN: se desconecta y el próximo ``connect()`` falla.

        La bajada cae con ella —es el mismo enlace—, así que un comando emitido
        durante el corte se queda en el buzón y se entrega al reconectar. Es lo
        que hace la sesión persistente de IoT Core con QoS1.
        """
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


class SpoolCommandPublisher:
    """[T-5.29] ``CommandPublisher`` de la nube que escribe en el buzón del thing.

    Es el reflejo exacto de ``IotDataPublisher``: recibe ``(topic, payload)`` con
    el envelope **ya firmado** por ``commands.service.issue_signed_command`` y lo
    deja donde el gabinete lo va a leer. **No firma, no verifica y no interpreta**
    — si lo hiciera, la demo estaría probando este archivo en vez del dispatcher
    real del edge, que es justo lo que hay que probar.

    El thing sale del topic (``takab/cmd/<thing>``, ``takab/cfg/<thing>``), igual
    que en IoT Core: ahí el topic ES la dirección.
    """

    def __init__(self, downlink_root: str | Path) -> None:
        self.root = Path(downlink_root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._seq = 0
        self._lock = threading.Lock()
        #: Cuántos comandos se han PUBLICADO. La otra mitad del conteo de la
        #: guarda de no-vacuidad: publicados aquí, entregados allá.
        self.published: list[tuple[str, str]] = []  # (topic, command_id | "")

    def publish(self, topic: str, payload: bytes) -> None:
        thing = topic.rsplit("/", 1)[-1]
        sobre = json.loads(payload)
        with self._lock:
            self._seq += 1
            name = f"{self._seq:012d}-{uuid.uuid4().hex[:8]}.json"
            self.published.append((topic, str(sobre.get("command_id", ""))))
        # El envelope viaja INTACTO dentro de `payload`; el `meta_topic` de fuera
        # es solo la dirección, como el topic en IoT Core, y el transporte lo usa
        # para elegir a qué suscripción entregarlo.
        _atomic_write(
            downlink_dir(self.root, thing) / name,
            json.dumps({META_TOPIC: topic, "payload": sobre}),
        )
