"""Provisión de claves públicas (JWKS) para verificar la firma del token.

``RemoteJWKS`` usa el endpoint JWKS del pool (prod); ``StaticJWKS`` parsea un
JWKS inline (dev/tests, sin Cognito real). La factoría elige según settings.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

from jwt import PyJWK, PyJWKClient


class JWKSProvider(Protocol):
    """Resuelve el ``kid`` del header a una clave pública para ``jwt.decode``."""

    def get_key(self, kid: str) -> Any: ...


class RemoteJWKS:
    """JWKS remoto vía ``PyJWKClient`` (cache por kid + refetch en kid desconocido)."""

    def __init__(self, jwks_url: str) -> None:
        self._client = PyJWKClient(jwks_url, cache_keys=True)

    def get_key(self, kid: str) -> Any:
        return self._client.get_signing_key(kid).key


class StaticJWKS:
    """JWKS inline (un objeto ``{"keys": [...]}``), resuelto por ``kid``."""

    def __init__(self, jwks_json: str) -> None:
        data = json.loads(jwks_json)
        self._keys: dict[str, PyJWK] = {}
        for entry in data.get("keys", []):
            kid = entry.get("kid")
            if kid:
                self._keys[kid] = PyJWK.from_dict(entry)

    def get_key(self, kid: str) -> Any:
        jwk = self._keys.get(kid)
        if jwk is None:
            raise KeyError(kid)
        return jwk.key


def select_jwks(settings: Any) -> JWKSProvider:
    """StaticJWKS si hay JWKS inline; si no, RemoteJWKS desde ``auth_jwks_url``."""
    if settings.auth_jwks_json:
        return StaticJWKS(settings.auth_jwks_json)
    return RemoteJWKS(settings.auth_jwks_url)


def select_jwks_occupants(settings: Any, main: JWKSProvider) -> JWKSProvider | None:
    """Proveedor JWKS del pool de OCUPANTES (T-2.03); ``None`` si está deshabilitado.

    Con issuer configurado pero sin JWKS propio, reutiliza el del pool principal
    (dev/test firman ambos pools con la misma clave de sesión). En prod cada pool
    tiene su ``auth_occupants_jwks_url``.
    """
    if not getattr(settings, "auth_occupants_issuer", ""):
        return None
    if settings.auth_occupants_jwks_json:
        return StaticJWKS(settings.auth_occupants_jwks_json)
    if settings.auth_occupants_jwks_url:
        return RemoteJWKS(settings.auth_occupants_jwks_url)
    return main
