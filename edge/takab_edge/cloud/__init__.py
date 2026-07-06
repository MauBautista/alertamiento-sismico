"""cloud — conector MQTT (mTLS) hacia AWS IoT Core + cola durable offline.

T-1.11 (edge-side): outbox **durable en disco** (sobrevive reinicios: cero pérdida) con
**dedup idempotente** por `(event_id, tier)` (cero duplicado; la escalación de tier SÍ
sale), transporte MQTT **abstracto** (QoS 1, last-will) con **reconexión backoff+jitter**,
y publicación NUNCA como prerequisito de actuar (blueprint §4.2: si la cola falla, el
gabinete sigue accionando).

El transporte real contra AWS IoT Core (`AwsIotMqttTransport`, awscrt/aws-iot-device-sdk)
necesita certificados y endpoint provisionados por Terraform (T-1.15) → gate AWS; los
tests usan `FakeMqttTransport`. Los contratos publicados están versionados en
`shared/schemas/` (contracts-first, [ANALISIS-00]).
"""

from __future__ import annotations

import json
import logging
import os
import threading
from collections import OrderedDict, deque
from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from takab_edge.config import EdgeSettings
from takab_edge.module import EdgeModule

log = logging.getLogger("takab_edge.cloud")

#: Tope de la ventana de dedup (claves recientes; la nube garantiza exactly-once por PK).
_SEEN_CAP = 20_000


@runtime_checkable
class MqttTransport(Protocol):
    """Transporte MQTT mínimo (mTLS/QoS1). Impl real = AWS IoT Core; fake en tests."""

    def connect(self) -> None: ...
    def disconnect(self) -> None: ...
    def publish(self, topic: str, payload: bytes, qos: int = 1) -> bool: ...
    @property
    def connected(self) -> bool: ...


class _BoundedSeen:
    """Conjunto de claves vistas con tope (LRU) — dedup sin crecer sin límite."""

    def __init__(self, cap: int = _SEEN_CAP) -> None:
        self._d: OrderedDict[tuple, None] = OrderedDict()
        self._cap = cap

    def __contains__(self, key: tuple) -> bool:
        return key in self._d

    def add(self, key: tuple) -> None:
        self._d[key] = None
        self._d.move_to_end(key)
        while len(self._d) > self._cap:
            self._d.popitem(last=False)


class DurableSpool:
    """Cola durable en disco: un archivo JSON por mensaje; se borra al confirmar el envío.

    Sobrevive a reinicios del Pi (cero pérdida). El orden se preserva por un contador
    monótono en el nombre; al recargar continúa desde el máximo existente.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._counter = self._max_counter()

    def _max_counter(self) -> int:
        counters = [self._counter_of(p) for p in self.root.glob("*.json")]
        return max([c for c in counters if c is not None], default=0)

    @staticmethod
    def _counter_of(path: Path) -> int | None:
        try:
            return int(path.stem.split("-", 1)[0])
        except (ValueError, IndexError):
            return None

    def append(self, record: dict) -> str:
        with self._lock:
            self._counter += 1
            name = f"{self._counter:012d}-{record.get('event_id') or 'na'}.json"
            path = self.root / name
            tmp = path.with_suffix(".tmp")
            # fsync del archivo + del directorio ANTES de retornar: durable ante corte de
            # energía (un sismo suele cortar la luz al Pi justo tras escribir el evento).
            with open(tmp, "w") as fh:
                fh.write(json.dumps(record))
                fh.flush()
                os.fsync(fh.fileno())
            tmp.replace(path)  # rename atómico: nunca un archivo a medio escribir
            self._fsync_dir()
            return name

    def _fsync_dir(self) -> None:
        fd = os.open(self.root, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def remove(self, name: str) -> None:
        with self._lock:
            (self.root / name).unlink(missing_ok=True)

    def load(self) -> list[tuple[str, dict]]:
        """Recarga los mensajes pendientes en orden (backfill tras reinicio)."""
        out: list[tuple[int, str, dict]] = []
        for path in self.root.glob("*.json"):
            counter = self._counter_of(path)
            if counter is None:
                continue
            try:
                out.append((counter, path.name, json.loads(path.read_text())))
            except (OSError, ValueError):
                # NO se descarta en silencio: cuarentena + alarma (posible corte de energía
                # a mitad de escritura). Se conserva para inspección, no se pierde callado.
                corrupt = path.with_suffix(".corrupt")
                path.rename(corrupt)
                log.error("mensaje spool corrupto en cuarentena: %s", corrupt.name)
        out.sort(key=lambda item: item[0])
        return [(name, record) for _c, name, record in out]

    def __len__(self) -> int:
        return sum(1 for _ in self.root.glob("*.json"))


class CloudConnector(EdgeModule):
    """Publica payloads a la nube (durable, offline-first); nunca bloquea la actuación."""

    name = "cloud"

    def __init__(
        self,
        settings: EdgeSettings,
        transport: MqttTransport | None = None,
        spool_dir: str | Path | None = None,
    ) -> None:
        super().__init__()
        self.settings = settings
        self._transport = transport
        self._spool = DurableSpool(spool_dir or settings.cloud_spool_dir or _tmp_spool())
        self._queue: deque[tuple[str, dict]] = deque()  # (spool_name, record)
        self._seen = _BoundedSeen()
        self._sent = 0
        self._lock = threading.RLock()
        self._reconnect_stop = threading.Event()
        self._reconnect_thread: threading.Thread | None = None
        self._backfill()

    def _backfill(self) -> None:
        # Recarga la cola durable tras un reinicio (backfill idempotente).
        for name, record in self._spool.load():
            key = self._dedup_key(record)
            if key is not None:
                self._seen.add(key)
            self._queue.append((name, record))
        if self._queue:
            log.info("backfill: %d mensajes pendientes recargados del spool", len(self._queue))

    @staticmethod
    def _dedup_key(record: dict) -> tuple | None:
        """Identidad LÓGICA del mensaje para dedup (no colapsa mensajes distintos).

        Discrimina por tipo de payload: `tier` (eventos), `channel`+`action` (ACKs),
        `sha256` (evidencia). Distintos ACKs/evidencias del mismo `event_id` tienen
        discriminador distinto → NO se deduplican (no se pierde telemetría/evidencia).
        Sin `event_id` (p.ej. heartbeat de salud) → no se deduplica.
        """
        event_id = record.get("event_id") or ""
        if not event_id:
            return None
        payload = record.get("payload", {})
        disc = (
            payload.get("tier"),
            payload.get("channel"),
            payload.get("action"),
            payload.get("sha256"),
        )
        return (record["topic"], event_id, disc)

    @property
    def online(self) -> bool:
        return self._transport is not None and self._transport.connected

    @property
    def queued(self) -> int:
        return len(self._queue)

    @property
    def sent(self) -> int:
        return self._sent

    def set_online(self, online: bool) -> None:
        """Marca el enlace (tests/dev). En prod lo gestiona el hilo de reconexión."""
        if self._transport is None:
            return
        if online:
            try:
                self._transport.connect()
            except Exception:  # noqa: BLE001 — el enlace es best-effort, nunca bloquea
                log.warning("no se pudo conectar el transporte")
                return
            self.flush()
        else:
            self._transport.disconnect()

    def publish(self, topic: str, payload: BaseModel) -> bool:
        """Encola durable + envía si hay enlace. NUNCA lanza/bloquea al llamador.

        Regla de oro 4.2: publicar no es prerequisito de actuar, así que un fallo de disco
        o de enlace jamás propaga a la vía de actuación. La escalación de tier (mismo
        `event_id`, tier mayor) y los distintos ACKs/evidencias del mismo evento SÍ salen
        (dedup por identidad lógica). La nube garantiza exactly-once por PK (CLAUDE.md §2.3).
        """
        record = {
            "topic": topic,
            "event_id": getattr(payload, "event_id", None) or "",
            "payload": payload.model_dump(mode="json"),
        }
        key = self._dedup_key(record)
        with self._lock:
            if key is not None and key in self._seen:
                return True  # re-publicación idéntica → no duplicar
            try:
                name = self._spool.append(record)  # durable ANTES de intentar enviar
            except OSError:
                # Sin respaldo durable (¿disco lleno / FS de sólo lectura?): best-effort en
                # memoria + alarma. NUNCA propaga (no debe romper la actuación local).
                log.critical("spool falló al escribir; mensaje sólo en memoria (best-effort)")
                name = None
            self._queue.append((name, record))
            if key is not None:
                self._seen.add(key)  # SÓLO tras encolar → un fallo de escritura no lo envenena
        self.flush()
        return True

    def flush(self) -> int:
        """Envía la cola por el transporte si hay enlace; borra del spool al confirmar."""
        if not self.online:
            return 0
        count = 0
        with self._lock:
            while self._queue:
                name, record = self._queue[0]
                payload = json.dumps(record["payload"]).encode()
                try:
                    ok = self._transport.publish(record["topic"], payload, qos=1)
                except Exception:  # noqa: BLE001 — fallo de enlace: reintenta luego, no pierdas
                    log.warning("fallo al publicar; se reintentará (%s)", record["topic"])
                    break
                if not ok:
                    break
                self._queue.popleft()
                if name is not None:  # (name None = sólo en memoria por fallo de spool)
                    self._spool.remove(name)  # confirmado → ya no es necesario reenviarlo
                self._sent += 1
                count += 1
        return count

    def _reconnect_loop(self) -> None:
        # Reconexión con backoff+jitter (patrón de seedlink); jitter determinista por intento.
        attempt = 0
        base = self.settings.cloud_backoff_s
        while not self._reconnect_stop.is_set():
            if self.online:
                self.flush()
                self._reconnect_stop.wait(base)
                continue
            try:
                self._transport.connect()
                attempt = 0
                log.info("enlace cloud restablecido; backfill de %d mensajes", self.queued)
                self.flush()
            except Exception:  # noqa: BLE001 — sin enlace: espera con backoff y reintenta
                attempt += 1
                delay = min(base * (2**attempt), self.settings.cloud_backoff_max_s)
                jitter = delay * 0.1 * ((attempt % 5) / 5.0)  # 0–10% determinista
                self._reconnect_stop.wait(delay + jitter)

    def _on_start(self) -> None:
        endpoint = self.settings.mqtt_endpoint or "<sin definir>"
        if self._transport is not None:
            self._reconnect_stop.clear()
            self._reconnect_thread = threading.Thread(
                target=self._reconnect_loop, name="cloud-reconnect", daemon=True
            )
            self._reconnect_thread.start()
        log.info("conector cloud activo (endpoint=%s, %d en spool)", endpoint, self.queued)

    def _on_stop(self) -> None:
        self._reconnect_stop.set()
        if self._reconnect_thread is not None:
            self._reconnect_thread.join(timeout=2.0)
            self._reconnect_thread = None
        if self._transport is not None and self._transport.connected:
            self._transport.disconnect()


class AwsIotMqttTransport:
    """Transporte real contra AWS IoT Core (mTLS, QoS1, last-will). **Gate AWS (T-1.15).**

    Requiere `aws-iot-device-sdk-python-v2` (awscrt) + cert/key/CA X.509 y endpoint
    provisionados por Terraform. No se ejecuta en CI (sin credenciales/certs AWS); es la
    impl de producción detrás de la misma interfaz `MqttTransport` que el fake.
    """

    def __init__(
        self,
        settings: EdgeSettings,
        cert_path: str,
        key_path: str,
        ca_path: str,
        client_id: str,
        status_topic: str,
    ) -> None:
        self._settings = settings
        self._cert = cert_path
        self._key = key_path
        self._ca = ca_path
        self._client_id = client_id
        self._status_topic = status_topic
        self._conn = None

    def connect(self) -> None:
        from awscrt import mqtt  # import perezoso: solo en el Pi con el SDK instalado
        from awsiot import mqtt_connection_builder

        # Last-will retenido: si el Pi cae sin desconectar, la nube ve el gabinete offline.
        will = mqtt.Will(
            topic=self._status_topic,
            qos=mqtt.QoS.AT_LEAST_ONCE,
            payload=b'{"status":"offline"}',
            retain=True,
        )
        self._conn = mqtt_connection_builder.mtls_from_path(
            endpoint=self._settings.mqtt_endpoint,
            port=self._settings.mqtt_port,
            cert_filepath=self._cert,
            pri_key_filepath=self._key,
            ca_filepath=self._ca,
            client_id=self._client_id,
            will=will,
            clean_session=False,  # sesión persistente: QoS1 sobrevive reconexiones
            keep_alive_secs=30,
        )
        self._conn.connect().result()

    def disconnect(self) -> None:
        if self._conn is not None:
            self._conn.disconnect().result()
            self._conn = None

    def publish(self, topic: str, payload: bytes, qos: int = 1) -> bool:
        from awscrt import mqtt

        if self._conn is None:
            return False
        self._conn.publish(topic=topic, payload=payload, qos=mqtt.QoS.AT_LEAST_ONCE)
        return True

    @property
    def connected(self) -> bool:
        return self._conn is not None


def _tmp_spool() -> str:
    import tempfile

    return tempfile.mkdtemp(prefix="takab-cloud-spool-")
