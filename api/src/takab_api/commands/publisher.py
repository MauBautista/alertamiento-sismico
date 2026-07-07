"""Publicador MQTT nube→edge vía AWS IoT Core Data Plane (T-1.23).

boto3 usa las credenciales del rol de la tarea/instancia en prod; los tests
inyectan un fake detrás del mismo Protocol. QoS1: IoT Core reintenta la
entrega al edge (sesión persistente del gateway, clean_session=False).
"""

from __future__ import annotations

from typing import Protocol

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from takab_api.settings import Settings


class PublishError(Exception):
    """El plano de datos IoT no aceptó la publicación."""


class CommandPublisher(Protocol):
    """Contrato mínimo del publicador (impl real IoT Core; fake en tests)."""

    def publish(self, topic: str, payload: bytes) -> None:
        """Publica QoS1; levanta ``PublishError`` si falla."""
        ...


class IotDataPublisher:
    """Publicación por ``iot-data`` (cliente perezoso: no exige AWS al importar)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = None

    def publish(self, topic: str, payload: bytes) -> None:
        if self._client is None:
            self._client = boto3.client("iot-data", region_name=self._settings.aws_region)
        try:
            self._client.publish(topic=topic, qos=1, payload=payload)
        except (BotoCoreError, ClientError) as exc:
            raise PublishError(f"iot-data: {exc}") from exc
