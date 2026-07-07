"""Autenticación TAKAB: verificación de ID token, claims y matriz de acceso (T-1.18)."""

from takab_api.auth.claims import ALL_SITES, Claims, scope_filter
from takab_api.auth.jwks import JWKSProvider, RemoteJWKS, StaticJWKS, select_jwks
from takab_api.auth.matrix import (
    ROLE_ACTION_MATRIX,
    ROLE_ROUTE_MATRIX,
    allowed_actions,
    allowed_routes,
)
from takab_api.auth.tokens import AuthError, decode_verify

__all__ = [
    "ALL_SITES",
    "ROLE_ACTION_MATRIX",
    "ROLE_ROUTE_MATRIX",
    "AuthError",
    "Claims",
    "JWKSProvider",
    "RemoteJWKS",
    "StaticJWKS",
    "allowed_actions",
    "allowed_routes",
    "decode_verify",
    "scope_filter",
    "select_jwks",
]
