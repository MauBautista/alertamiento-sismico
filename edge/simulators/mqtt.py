"""Simulador de transporte MQTT — implementa `MqttTransport` sin broker real.

Registra las publicaciones y permite simular caída/recuperación del enlace WAN para
probar la cola durable, el backfill idempotente y la reconexión sin hardware ni AWS.
"""

from __future__ import annotations

import json


class FakeMqttTransport:
    """Transporte MQTT en memoria para tests (mTLS/QoS1 simulados)."""

    def __init__(self, online: bool = True) -> None:
        self._online = online  # ¿hay WAN? (si no, connect() falla)
        self._connected = False
        self.published: list[tuple[str, dict]] = []
        self.retained: dict[str, dict] = {}  # último mensaje retained por topic

    def connect(self) -> None:
        if not self._online:
            raise ConnectionError("WAN offline")
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def publish(self, topic: str, payload: bytes, qos: int = 1, retain: bool = False) -> bool:
        if not self._connected:
            return False
        message = json.loads(payload)
        self.published.append((topic, message))
        if retain:
            self.retained[topic] = message
        return True

    @property
    def connected(self) -> bool:
        return self._connected

    # --- Helpers de test ---
    def go_offline(self) -> None:
        """Simula caída de WAN: se desconecta y falla el próximo connect()."""
        self._connected = False
        self._online = False

    def go_online(self) -> None:
        """Restaura la WAN (el próximo connect() tendrá éxito)."""
        self._online = True

    @property
    def event_ids(self) -> list[str]:
        return [p.get("event_id", "") for _topic, p in self.published]
