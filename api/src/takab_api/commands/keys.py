"""Resolución PER-GATEWAY de la clave HMAC de comandos (T-1.38, regla de oro 8).

Terraform emite una clave HMAC DISTINTA por gabinete (secreto
``takab/dev/gateway-hmac/<iot_thing>``) y el edge ya verifica con la suya
(``TAKAB_EDGE_HMAC_KEY``, instalada por ``provision_gateway.sh``). Este módulo
le da a la nube la misma granularidad: la firma de un comando o de una config
se produce con la clave DEL gateway destino, resuelta por ``iot_thing``.

``key_for`` devuelve ``None`` cuando no hay clave resoluble para ESE gateway,
y None significa SIEMPRE fail-closed (503 en la API, skip en el config sync).
Jamás se degrada a una clave compartida de flota: esa es exactamente la clase
de atajo que esta pieza elimina (una clave única no liga la firma al gateway).

Dos implementaciones:

- ``StaticKeyProvider``: mapa inline (env ``TAKAB_API_COMMAND_HMAC_KEYS_JSON``)
  para dev/tests sin AWS — mismo patrón que ``auth_jwks_json``.
- ``SecretsManagerKeyProvider``: producción. Cache TTL positivo (una rotación
  se ve en ≤``command_hmac_cache_ttl_s`` sin reinicio), cache negativa corta
  (una ráfaga contra un thing sin secreto no martillea Secrets Manager) y
  errores transitorios SIN cachear (el request actual falla cerrado; el
  siguiente reintenta). Espejo del patrón de ``ingest/registry.py::Registry``.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable, Mapping
from typing import Any, Protocol

from botocore.exceptions import BotoCoreError, ClientError

from takab_api.settings import Settings

logger = logging.getLogger("takab_api.commands")


class CommandKeyProvider(Protocol):
    """Contrato mínimo: clave del gateway o ``None`` (= fail-closed)."""

    def key_for(self, iot_thing: str) -> bytes | None: ...


class StaticKeyProvider:
    """Mapa inline ``iot_thing → clave`` (dev/tests). Vacío ⇒ todo fail-closed."""

    def __init__(self, keys: Mapping[str, str]) -> None:
        # Una clave vacía equivale a no tener clave: nunca se firma con b"".
        self._keys = {thing: key.encode() for thing, key in keys.items() if key}

    def key_for(self, iot_thing: str) -> bytes | None:
        return self._keys.get(iot_thing)


class SecretsManagerKeyProvider:
    """Resuelve ``{prefix}/{iot_thing}`` (campo ``hmac_key``) con cache TTL."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: Any | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._prefix = settings.command_hmac_secret_prefix.rstrip("/")
        self._ttl_s = settings.command_hmac_cache_ttl_s
        self._negative_ttl_s = settings.command_hmac_negative_ttl_s
        self._region = settings.aws_region
        self._client = client
        self._clock = clock
        self._cache: dict[str, tuple[float, bytes | None]] = {}
        self._lock = threading.Lock()

    @property
    def prefix(self) -> str:
        return self._prefix

    def key_for(self, iot_thing: str) -> bytes | None:
        now = self._clock()
        hit = self._cache.get(iot_thing)
        if hit is not None and hit[0] > now:
            return hit[1]
        # Single-flight por proceso: el primer fetch de un thing serializa a
        # los demás (flota pequeña; serializar UN GetSecretValue es irrelevante
        # frente a un thundering herd contra Secrets Manager).
        with self._lock:
            now = self._clock()
            hit = self._cache.get(iot_thing)
            if hit is not None and hit[0] > now:
                return hit[1]
            key, cache_ttl = self._fetch(iot_thing)
            if cache_ttl is not None:
                self._cache[iot_thing] = (now + cache_ttl, key)
            return key

    def invalidate(self, iot_thing: str | None = None) -> None:
        """Fuerza re-fetch (hook para rotaciones coordinadas; sin uso en caliente)."""
        with self._lock:
            if iot_thing is None:
                self._cache.clear()
            else:
                self._cache.pop(iot_thing, None)

    def _fetch(self, iot_thing: str) -> tuple[bytes | None, float | None]:
        """(clave, ttl_de_cache). ttl ``None`` = transitorio: NO cachear."""
        secret_id = f"{self._prefix}/{iot_thing}"
        try:
            raw = self._get_client().get_secret_value(SecretId=secret_id)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code == "ResourceNotFoundException":
                # Definitivo: gateway sin secreto (aún). Cache negativa corta:
                # uno recién aprovisionado es comandable en ≤negative_ttl.
                return None, self._negative_ttl_s
            logger.warning(
                "hmac keys: error transitorio de Secrets Manager (%s): %s", iot_thing, code or exc
            )
            return None, None
        except BotoCoreError as exc:
            logger.warning("hmac keys: fallo de red/cliente (%s): %s", iot_thing, exc)
            return None, None
        try:
            key = json.loads(raw["SecretString"])["hmac_key"]
        except (KeyError, TypeError, ValueError):
            logger.warning("hmac keys: secreto %s malformado (sin hmac_key)", secret_id)
            return None, self._negative_ttl_s
        if not isinstance(key, str) or not key:
            logger.warning("hmac keys: secreto %s con hmac_key vacía", secret_id)
            return None, self._negative_ttl_s
        return key.encode(), self._ttl_s

    def _get_client(self) -> Any:
        if self._client is None:
            import boto3  # perezoso: los tests inyectan el cliente y jamás tocan AWS

            self._client = boto3.client("secretsmanager", region_name=self._region)
        return self._client


def build_key_provider(settings: Settings, *, client: Any | None = None) -> CommandKeyProvider:
    """Provider según settings: ``keys_json`` (dev) ≻ ``secret_prefix`` (prod) ≻ vacío.

    El mapa inline gana sobre el prefijo: quien lo define quiere claves
    deterministas sin AWS. Sin ninguno, todo ``key_for`` es None (fail-closed).
    """
    if settings.command_hmac_keys_json:
        try:
            keys = json.loads(settings.command_hmac_keys_json)
        except ValueError as exc:
            raise ValueError("TAKAB_API_COMMAND_HMAC_KEYS_JSON no es JSON válido") from exc
        if not isinstance(keys, dict):
            raise ValueError(
                "TAKAB_API_COMMAND_HMAC_KEYS_JSON debe ser un objeto {iot_thing: clave}"
            )
        return StaticKeyProvider(keys)
    if settings.command_hmac_secret_prefix:
        return SecretsManagerKeyProvider(settings, client=client)
    return StaticKeyProvider({})
