"""Verificación del ID token de Cognito.

Solo RS256. Verifica firma (clave del ``kid``), issuer, audience, exp/nbf
(leeway 0) y ``token_use == 'id'`` (Cognito pone ``custom:*`` solo en el ID
token). Cualquier fallo ⇒ ``AuthError`` (status 401 + razón).
"""

from __future__ import annotations

from typing import Any

import jwt

from takab_api.auth.jwks import JWKSProvider

# Único algoritmo aceptado: rechazamos 'none'/'HS*' antes de decodificar.
_ALG = "RS256"


class AuthError(Exception):
    """Fallo de autenticación. ``status`` = HTTP, ``reason`` = causa legible."""

    status = 401

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def decode_verify(token: str, settings: Any, jwks: JWKSProvider) -> dict[str, Any]:
    """Devuelve los claims verificados o lanza ``AuthError`` 401."""
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise AuthError("malformed token header") from exc

    if header.get("alg") != _ALG:
        raise AuthError(f"unsupported alg: {header.get('alg')!r}")

    kid = header.get("kid")
    if not kid:
        raise AuthError("missing kid")

    try:
        key = jwks.get_key(kid)
    except Exception as exc:  # KeyError / errores del cliente JWKS
        raise AuthError("unknown signing key") from exc

    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=[_ALG],
            issuer=settings.auth_issuer,
            audience=settings.auth_audience,
            leeway=0,
            options={"require": ["exp", "iat"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("token expired") from exc
    except jwt.ImmatureSignatureError as exc:
        raise AuthError("token not yet valid") from exc
    except jwt.InvalidIssuerError as exc:
        raise AuthError("invalid issuer") from exc
    except jwt.InvalidAudienceError as exc:
        raise AuthError("invalid audience") from exc
    except jwt.InvalidSignatureError as exc:
        raise AuthError("invalid signature") from exc
    except jwt.PyJWTError as exc:
        raise AuthError("invalid token") from exc

    if claims.get("token_use") != "id":
        raise AuthError("token_use is not id")

    return claims
