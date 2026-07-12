"""telemetry — batcheo escalonado por tier de la publicación de features (T-1.56).

El costo de SQS/IoT es por REQUEST: 4 canales a 1 Hz son ~350k publishes/día por
gabinete, casi todos de ruido de fondo. Este módulo se interpone SOLO en la
publicación: en tier `normal` acumula features y publica 1 mensaje
``feature_batch`` cada ``cloud_features_batch_s``; al escalar a `watch`+
(por features O por SASMEX) hace flush inmediato del acumulado y deja pasar
cada feature individual a 1 Hz — telemetría densa exactamente cuando importa.

Reglas de oro respetadas:
- La detección/actuación NO pasa por aquí (el supervisor actúa ANTES de llamar
  ``submit``); módulo no-crítico: si falla, el gabinete sigue protegiendo.
- Compone SOBRE ``cloud.publish`` (spool durable, QoS1, FIFO, cota por topic):
  un batch pendiente en el spool sobrevive reinicios igual que un feature suelto.
- El flush del acumulado sale ANTES del primer feature 1 Hz (el spool es FIFO):
  la ventana ciega del SOC al escalar es mínima.
- Kill-switch operativo: ``cloud_features_batch_enabled=false`` ⇒ passthrough
  1 Hz exacto (camino previo a T-1.56).
"""

from __future__ import annotations

import logging
import threading

from takab_edge.config import EdgeSettings
from takab_edge.contracts import Feature1s, FeatureBatch, Tier
from takab_edge.module import EdgeModule

log = logging.getLogger("takab_edge.telemetry")

#: Topic de features individuales (1 Hz, tier watch+ o kill-switch).
FEATURES_TOPIC = "takab/features"
#: Topic del lote de tier normal. Regla IoT propia → la MISMA telemetry_queue.
FEATURES_BATCH_TOPIC = "takab/features/batch"


class FeatureBatcher(EdgeModule):
    """Acumula features en tier normal y los publica en lotes; 1 Hz en watch+."""

    name = "telemetry"
    depends_on = ("cloud",)  # toposort: arranca después ⇒ se DETIENE antes que cloud

    def __init__(
        self,
        settings: EdgeSettings,
        cloud,
        features_topic: str = FEATURES_TOPIC,
        batch_topic: str = FEATURES_BATCH_TOPIC,
    ) -> None:
        super().__init__()
        self._settings = settings
        self._cloud = cloud
        self._features_topic = features_topic
        self._batch_topic = batch_topic
        self._enabled = settings.cloud_features_batch_enabled
        self._batch_s = settings.cloud_features_batch_s
        self._batch_max = settings.cloud_features_batch_max
        self._pending: list[Feature1s] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------ publicación

    def submit(self, feature: Feature1s, tier: Tier) -> None:
        """Publica un feature según el tier vigente. JAMÁS lanza al llamador.

        `normal` → acumula (flush por timer o al llenar el lote). `watch`+ →
        flush del acumulado PRIMERO y feature individual después (FIFO del
        spool ⇒ el contexto pre-evento llega antes que el 1 Hz).
        """
        try:
            if not self._enabled or tier is not Tier.NORMAL:
                self.flush_pending()
                self._cloud.publish(self._features_topic, feature)
                return
            with self._lock:
                self._pending.append(feature)
                full = len(self._pending) >= self._batch_max
            if full:
                self.flush_pending()
        except Exception:  # noqa: BLE001 — telemetría jamás propaga al hilo SeedLink
            log.exception("submit falló; el feature se pierde (telemetría reponible)")

    def notify_tier(self, tier: Tier) -> None:
        """Escalación SIN feature (ruta SASMEX por gpio): drena el acumulado ya."""
        try:
            if tier is not Tier.NORMAL:
                self.flush_pending()
        except Exception:  # noqa: BLE001 — jamás propaga a la ruta SASMEX
            log.exception("notify_tier falló; el acumulado saldrá por timer")

    def flush_pending(self) -> int:
        """Publica el acumulado como lote(s) ``feature_batch``. Devuelve nº de lotes.

        Swap bajo lock, publish FUERA del lock: el hilo del timer nunca retiene
        el lock mientras toca el spool/transporte. En trozos de ``batch_max``
        (una carrera submit/timer puede dejar el buffer ligeramente pasado).
        """
        with self._lock:
            batch, self._pending = self._pending, []
        if not batch:
            return 0
        published = 0
        for start in range(0, len(batch), self._batch_max):
            chunk = batch[start : start + self._batch_max]
            payload = FeatureBatch(gateway_id=self._settings.gateway_id, features=chunk)
            self._cloud.publish(self._batch_topic, payload)
            published += 1
        return published

    @property
    def pending(self) -> int:
        with self._lock:
            return len(self._pending)

    # ---------------------------------------------------------- ciclo de vida

    def _loop(self) -> None:
        # Patrón _reconnect_loop: wait(timeout) como tick, sin sleeps sueltos.
        while not self._stop.wait(self._batch_s):
            try:
                self.flush_pending()
            except Exception:  # noqa: BLE001 — un tick fallido no mata el timer
                log.exception("flush por timer falló; se reintenta al siguiente tick")

    def _on_start(self) -> None:
        if not self._enabled:
            log.info("batcheo de features DESHABILITADO (kill-switch): 1 Hz directo")
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="telemetry-batch", daemon=True)
        self._thread.start()

    def _on_stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        # Flush final: el acumulado cae al spool durable de cloud (que se detiene
        # DESPUÉS que este módulo, por el orden inverso del toposort).
        self.flush_pending()
