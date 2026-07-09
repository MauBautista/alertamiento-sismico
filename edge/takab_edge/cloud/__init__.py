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
import time
from collections import Counter, OrderedDict, deque
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from takab_edge.config import EdgeSettings
from takab_edge.module import EdgeModule

log = logging.getLogger("takab_edge.cloud")

#: Tope de la ventana de dedup (claves recientes; la nube garantiza exactly-once por PK).
_SEEN_CAP = 20_000

#: Espera máxima del PUBACK QoS1 del broker (transporte real).
_PUBACK_TIMEOUT_S = 10.0


@runtime_checkable
class _BackfillRouter(Protocol):
    """Decide la ruta del spool (T-1.25): S3 en bloque o MQTT (flush normal)."""

    def should_take(self, connector: CloudConnector) -> bool: ...
    def kick(self) -> None: ...


@runtime_checkable
class MqttTransport(Protocol):
    """Transporte MQTT mínimo (mTLS/QoS1). Impl real = AWS IoT Core; fake en tests."""

    def connect(self) -> None: ...
    def disconnect(self) -> None: ...
    def publish(self, topic: str, payload: bytes, qos: int = 1, retain: bool = False) -> bool: ...
    def subscribe(self, topic: str, callback: Callable[[str, bytes], None]) -> bool: ...
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
        status_topic: str = "",
        topic_caps: dict[str, int] | None = None,
    ) -> None:
        super().__init__()
        self.settings = settings
        self._transport = transport
        self._status_topic = status_topic  # vacío → sin beacon de presencia (tests T-1.11)
        self._spool = DurableSpool(spool_dir or settings.cloud_spool_dir or _tmp_spool())
        self._queue: deque[tuple[str, dict]] = deque()  # (spool_name, record)
        #: Cota por topic de telemetría REPONIBLE (features/health): offline
        #: prolongado no debe crecer sin límite. Eventos/ACKs no llevan cota.
        self._topic_caps: dict[str, int] = dict(topic_caps or {})
        self._topic_counts: Counter[str] = Counter()
        self._dropped = 0
        self._seen = _BoundedSeen()
        self._sent = 0
        self._lock = threading.RLock()
        self._flush_lock = threading.Lock()  # un solo drenado a la vez
        self._reconnect_stop = threading.Event()
        self._reconnect_thread: threading.Thread | None = None
        # Suscripciones nube→edge (cmd/cfg, T-1.23): se registran aquí y se
        # (re)aplican al transporte en cada conexión (la sesión MQTT puede
        # perderlas tras un corte largo; re-suscribir es idempotente).
        self._subscriptions: dict[str, Callable[[str, bytes], None]] = {}
        # Router de backfill (T-1.25, regla FASE-0 capa 4): si decide la ruta
        # S3, flush() NO drena por MQTT (el manager sube el spool en bloque).
        self._backfill_router: _BackfillRouter | None = None
        # Callbacks al (re)establecer enlace (evidencia pendiente, etc.).
        self._online_callbacks: list[Callable[[], None]] = []
        self._backfill()

    def _backfill(self) -> None:
        # Recarga la cola durable tras un reinicio (backfill idempotente).
        with self._lock:
            for name, record in self._spool.load():
                key = self._dedup_key(record)
                if key is not None:
                    self._seen.add(key)
                self._queue.append((name, record))
                self._topic_counts[record["topic"]] += 1
            for topic in self._topic_caps:  # spool heredado sobre la cota → poda
                self._evict_over_cap(topic)
        if self._queue:
            log.info("backfill: %d mensajes pendientes recargados del spool", len(self._queue))

    @staticmethod
    def _dedup_key(record: dict) -> tuple | None:
        """Identidad LÓGICA del mensaje para dedup (no colapsa mensajes distintos).

        Discrimina por tipo de payload: `tier` (eventos), `channel`+`action`+
        `success`+`executed_at` (ACKs: dentro de un episodio la transición
        fallo→éxito de la MISMA actuación es evidencia distinta y debe salir),
        `sha256` (evidencia). Solo la re-publicación idéntica se deduplica.
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
            payload.get("success"),
            payload.get("executed_at"),
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

    @property
    def mqtt_rtt_ms(self) -> float | None:
        """RTT del último PUBACK QoS1 (ms), medido por el transporte real (T-1.40).

        ``None`` = sin dato: no hay transporte, aún no se publicó nada, o el
        transporte (fake de tests) no lo expone. La salud lo reporta tal cual.
        """
        return getattr(self._transport, "last_puback_rtt_ms", None)

    def queued_by_topic(self, topic: str) -> int:
        """Pendientes de UN topic (separa eventos de la telemetría health/acks/features)."""
        with self._lock:
            return self._topic_counts[topic]

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
            self._announce_online()
            self._apply_subscriptions()
            self._fire_online()
            self.flush()
        else:
            self._transport.disconnect()

    # ------------------------------------------------- backfill S3 (T-1.25)

    def set_backfill_router(self, router: _BackfillRouter) -> None:
        """Inyecta el decisor de ruta del spool (regla FASE-0 capa 4)."""
        self._backfill_router = router

    def on_online(self, callback: Callable[[], None]) -> None:
        """Registra un callback que corre tras (re)establecer el enlace."""
        self._online_callbacks.append(callback)

    def _fire_online(self) -> None:
        for callback in self._online_callbacks:
            try:
                callback()
            except Exception:  # noqa: BLE001 — un hook jamás rompe la reconexión
                log.exception("callback on_online falló")

    def spool_span_s(self, now: datetime | None = None) -> float:
        """Antigüedad (s) del registro MÁS VIEJO del spool; 0.0 si está vacío.

        Los registros previos a T-1.25 (sin ``spooled_at``) cuentan como
        frescos: en el peor caso salen por MQTT, que era la ruta original.
        """
        now = now or datetime.now(UTC)
        with self._lock:
            oldest: datetime | None = None
            for _name, record in self._queue:
                raw = record.get("spooled_at")
                if not raw:
                    continue
                try:
                    ts = datetime.fromisoformat(raw)
                except ValueError:
                    continue
                if oldest is None or ts < oldest:
                    oldest = ts
        if oldest is None:
            return 0.0
        return max(0.0, (now - oldest).total_seconds())

    def peek_spool(self) -> list[tuple[str | None, dict]]:
        """Copia (nombre, registro) de la cola, en orden (para serializar NDJSON)."""
        with self._lock:
            return list(self._queue)

    def drop_spool(self, names: list[str | None]) -> int:
        """Retira del spool los registros confirmados por la ruta S3 (por nombre).

        Solo se retiran los que SIGUEN en la cola (un flush concurrente pudo
        haberlos enviado ya; la nube deduplica por PK de todos modos).
        """
        wanted = {n for n in names if n is not None}
        removed = 0
        with self._lock:
            kept: deque[tuple[str | None, dict]] = deque()
            for name, record in self._queue:
                if name in wanted:
                    self._topic_counts[record["topic"]] -= 1
                    self._spool.remove(name)
                    removed += 1
                else:
                    kept.append((name, record))
            self._queue = kept
        return removed

    def subscribe(self, topic: str, callback: Callable[[str, bytes], None]) -> None:
        """Registra un consumidor nube→edge; se aplica ya si hay enlace.

        El callback corre en el hilo del transporte y NUNCA debe lanzar hacia
        aquí (el dispatcher atrapa todo): un mensaje malformado jamás tira el
        enlace ni la actuación local.
        """
        self._subscriptions[topic] = callback
        if self.online:
            self._apply_subscriptions()

    def _apply_subscriptions(self) -> None:
        """(Re)aplica las suscripciones registradas al transporte (best-effort)."""
        for topic, callback in self._subscriptions.items():
            try:
                self._transport.subscribe(topic, callback)
            except Exception:  # noqa: BLE001 — sin suscripción no hay cmd/cfg, pero el edge vive
                log.warning("no se pudo suscribir a %s; reintento en la próxima conexión", topic)

    def _announce_online(self) -> None:
        """Retained `{"status":"online"}` al conectar — contraparte del LWT offline.

        Beacon best-effort directo al transporte (NO pasa por el spool: la presencia es
        punto-en-tiempo, encolarla offline no tiene sentido). Nunca propaga errores.
        """
        if not self._status_topic or not self.online:
            return
        try:
            self._transport.publish(self._status_topic, b'{"status":"online"}', qos=1, retain=True)
        except Exception:  # noqa: BLE001 — el beacon jamás bloquea el flush ni la actuación
            log.warning("no se pudo publicar el estado online en %s", self._status_topic)

    def publish_direct(self, topic: str, payload: BaseModel) -> bool:
        """Publica DIRECTO al transporte, sin spool (mensajes punto-en-tiempo:
        requests de backfill T-1.25, como el beacon de presencia). Best-effort:
        False si no hay enlace o el broker no confirmó; nunca lanza."""
        if not self.online:
            return False
        try:
            return self._transport.publish(
                topic, json.dumps(payload.model_dump(mode="json")).encode(), qos=1
            )
        except Exception:  # noqa: BLE001 — best-effort: el llamador decide el fallback
            log.warning("publish_direct falló (%s)", topic)
            return False

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
            # Edad del spool (T-1.25): decide la ruta S3 vs MQTT al reconectar.
            "spooled_at": datetime.now(UTC).isoformat(),
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
            self._topic_counts[topic] += 1
            if key is not None:
                self._seen.add(key)  # SÓLO tras encolar → un fallo de escritura no lo envenena
            self._evict_over_cap(topic)
        self.flush()
        return True

    def _evict_over_cap(self, topic: str) -> None:
        """Descarta lo más antiguo de un topic ACOTADO (telemetría reponible).

        Llamar con ``self._lock`` tomado. Los topics sin cota (eventos, ACKs:
        evidencia de compliance) jamás se descartan.
        """
        cap = self._topic_caps.get(topic)
        if cap is None:
            return
        while self._topic_counts[topic] > cap:
            idx = next(
                (i for i, (_n, rec) in enumerate(self._queue) if rec["topic"] == topic),
                None,
            )
            if idx is None:  # contador desalineado: re-sincroniza y no insistas
                self._topic_counts[topic] = sum(
                    1 for _n, rec in self._queue if rec["topic"] == topic
                )
                break
            name, _rec = self._queue[idx]
            del self._queue[idx]
            self._topic_counts[topic] -= 1
            if name is not None:
                self._spool.remove(name)
            self._dropped += 1
            if self._dropped == 1 or self._dropped % 1000 == 0:
                log.warning(
                    "spool acotado: descartado lo más antiguo de %s (%d descartes)",
                    topic,
                    self._dropped,
                )

    def flush(self) -> int:
        """Envía la cola por el transporte si hay enlace; borra del spool al confirmar.

        Un solo drenado a la vez (lock no bloqueante: si otro hilo ya drena, se
        retorna de inmediato) y el lock principal se suelta ENTRE mensajes: el
        backfill de un backlog grande jamás bloquea al hilo SeedLink (la
        detección local no se ciega justo tras recuperar el enlace).
        """
        if not self.online:
            return 0
        # Regla FASE-0 capa 4 (T-1.25): un spool con >umbral de datos va por S3
        # en bloque (el manager lo sube); MQTT no drena mientras tanto. Si la
        # ruta S3 falla, el router deja de tomar la cola y esto vuelve a drenar.
        if self._backfill_router is not None and self._backfill_router.should_take(self):
            self._backfill_router.kick()
            return 0
        if not self._flush_lock.acquire(blocking=False):
            return 0  # ya hay un drenado en curso; él se lleva la cola
        count = 0
        try:
            while True:
                with self._lock:
                    if not self._queue:
                        break
                    name, record = self._queue.popleft()
                    self._topic_counts[record["topic"]] -= 1
                payload = json.dumps(record["payload"]).encode()
                try:
                    ok = self._transport.publish(record["topic"], payload, qos=1)
                except Exception:  # noqa: BLE001 — fallo de enlace: reintenta luego, no pierdas
                    log.warning("fallo al publicar; se reintentará (%s)", record["topic"])
                    ok = False
                if not ok:
                    with self._lock:  # devuelve al FRENTE: orden y durabilidad intactos
                        self._queue.appendleft((name, record))
                        self._topic_counts[record["topic"]] += 1
                    break
                if name is not None:  # (name None = sólo en memoria por fallo de spool)
                    self._spool.remove(name)  # confirmado → ya no es necesario reenviarlo
                self._sent += 1
                count += 1
        finally:
            self._flush_lock.release()
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
                self._announce_online()
                self._apply_subscriptions()
                self._fire_online()
                self.flush()
            except Exception as exc:  # noqa: BLE001 — sin enlace: espera con backoff y reintenta
                attempt += 1
                delay = min(base * (2**attempt), self.settings.cloud_backoff_max_s)
                jitter = delay * 0.1 * ((attempt % 5) / 5.0)  # 0–10% determinista
                # La CAUSA debe ser visible: un rechazo del broker (política IoT,
                # certs) es indistinguible de una WAN caída si se traga en silencio.
                log.warning(
                    "conexión cloud falló (intento %d, reintento en %.0fs): %s",
                    attempt,
                    delay + jitter,
                    exc,
                )
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
        self._connected = False
        #: RTT del último PUBACK (ms) — la sonda de salud lo reporta (T-1.40).
        self.last_puback_rtt_ms: float | None = None

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
        conn = mqtt_connection_builder.mtls_from_path(
            endpoint=self._settings.mqtt_endpoint,
            port=self._settings.mqtt_port,
            cert_filepath=self._cert,
            pri_key_filepath=self._key,
            ca_filepath=self._ca,
            client_id=self._client_id,
            will=will,
            clean_session=False,  # sesión persistente: QoS1 sobrevive reconexiones
            keep_alive_secs=30,
            on_connection_interrupted=self._on_interrupted,
            on_connection_resumed=self._on_resumed,
        )
        # CONNACK PRIMERO: si falla, NO quedamos "conectados". Asignar antes del
        # result() hacía connected=True tras un connect fallido → flush borraba
        # el spool sin haber entregado nada y la reconexión dejaba de reintentar.
        conn.connect().result()
        self._conn = conn
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False
        if self._conn is not None:
            self._conn.disconnect().result()
            self._conn = None

    def publish(self, topic: str, payload: bytes, qos: int = 1, retain: bool = False) -> bool:
        from awscrt import mqtt

        if self._conn is None or not self._connected:
            return False
        future, _packet_id = self._conn.publish(
            topic=topic, payload=payload, qos=mqtt.QoS.AT_LEAST_ONCE, retain=retain
        )
        # QoS1 real: sin PUBACK no hay confirmación — el spool "cero pérdida"
        # solo se limpia cuando el broker acusó recibo. Un timeout propaga y el
        # conector conserva el mensaje para reintento (dedup por PK en la nube).
        # El tiempo hasta el PUBACK es el RTT real del enlace: la salud lo
        # reporta en vez del NULL de siempre (T-1.40).
        start = time.monotonic()
        future.result(timeout=_PUBACK_TIMEOUT_S)
        self.last_puback_rtt_ms = (time.monotonic() - start) * 1000.0
        return True

    def subscribe(self, topic: str, callback: Callable[[str, bytes], None]) -> bool:
        """Suscripción QoS1 (cmd/cfg nube→edge). El wrapper aísla la firma awscrt."""
        from awscrt import mqtt

        if self._conn is None or not self._connected:
            return False

        def _on_message(topic: str, payload: bytes, **_kwargs: object) -> None:
            callback(topic, payload)

        future, _packet_id = self._conn.subscribe(
            topic=topic, qos=mqtt.QoS.AT_LEAST_ONCE, callback=_on_message
        )
        future.result(timeout=_PUBACK_TIMEOUT_S)
        return True

    def _on_interrupted(self, *_args: object, **_kwargs: object) -> None:
        # awscrt avisa del corte: dejar de confiar en el enlace hasta el resume.
        self._connected = False

    def _on_resumed(self, *args: object, **kwargs: object) -> None:
        return_code = kwargs.get("return_code", args[1] if len(args) > 1 else None)
        self._connected = getattr(return_code, "value", return_code) == 0

    @property
    def connected(self) -> bool:
        return self._conn is not None and self._connected


def _tmp_spool() -> str:
    import tempfile

    return tempfile.mkdtemp(prefix="takab-cloud-spool-")
