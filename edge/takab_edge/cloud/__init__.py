"""cloud — conector MQTT (mTLS) hacia AWS IoT Core + cola durable offline.

Scaffold de T-1.2: outbox en memoria con **cola offline idempotente** (dedup por
`event_id`), que NUNCA es prerequisito para actuar (blueprint §4.2). El transporte
MQTT QoS 1/mTLS real, la cola durable en disco, el last-will y el backfill al
reconectar (cero pérdida/duplicado) son **T-1.11**.
"""

from __future__ import annotations

import logging
from collections import deque

from pydantic import BaseModel

from takab_edge.config import EdgeSettings
from takab_edge.module import EdgeModule

log = logging.getLogger("takab_edge.cloud")


class CloudConnector(EdgeModule):
    """Publica payloads a la nube; encola cuando no hay enlace (offline-first)."""

    name = "cloud"

    def __init__(self, settings: EdgeSettings) -> None:
        super().__init__()
        self.settings = settings
        self._online = False
        self._queue: deque[tuple[str, str, dict]] = deque()  # (topic, event_id, payload)
        self._seen: set[tuple[str, str]] = set()  # dedup idempotente (topic, event_id)
        self._sent = 0

    @property
    def online(self) -> bool:
        return self._online

    @property
    def queued(self) -> int:
        return len(self._queue)

    @property
    def sent(self) -> int:
        return self._sent

    def set_online(self, online: bool) -> None:
        self._online = online
        if online:
            self.flush()

    def publish(self, topic: str, payload: BaseModel) -> bool:
        """Encola/envía un payload. `payload` debe tener `event_id` para idempotencia."""
        event_id = getattr(payload, "event_id", None) or ""
        key = (topic, event_id)
        if event_id and key in self._seen:
            return True  # ya visto → no duplicar (idempotencia, CLAUDE.md §2.3)
        if event_id:
            self._seen.add(key)
        self._queue.append((topic, event_id, payload.model_dump(mode="json")))
        if self._online:
            self.flush()
        return True

    def flush(self) -> int:
        """Vacía la cola si hay enlace. Devuelve cuántos se enviaron."""
        if not self._online:
            return 0
        count = 0
        while self._queue:
            topic, _event_id, _payload = self._queue.popleft()
            self._sent += 1
            count += 1
            log.debug("publicado a %s", topic)
        return count

    def _on_start(self) -> None:
        endpoint = self.settings.mqtt_endpoint or "<sin definir>"
        log.info("conector cloud activo (endpoint=%s)", endpoint)
