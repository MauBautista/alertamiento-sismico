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


def _parse_aud(value: str) -> str | list[str]:
    """Audiences aceptados para un pool. Coma-separado ⇒ lista: el pool principal
    lo comparten el cliente WEB y el MÓVIL (``aud`` distinto por cliente), y PyJWT
    valida OK si el ``aud`` del token coincide con CUALQUIERA de la lista. Un valor
    único (o vacío) se pasa tal cual ⇒ comportamiento idéntico al histórico."""
    parts = [a.strip() for a in value.split(",") if a.strip()]
    return parts if len(parts) > 1 else value


def _decode(
    token: str, *, issuer: str, audience: str | list[str], jwks: JWKSProvider
) -> dict[str, Any]:
    """Verificación DURA contra una config concreta de pool (firma/iss/aud/exp)."""
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
            issuer=issuer,
            audience=audience,
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


def decode_verify(token: str, settings: Any, jwks: JWKSProvider) -> dict[str, Any]:
    """Devuelve los claims verificados contra el pool PRINCIPAL o lanza 401."""
    return _decode(
        token, issuer=settings.auth_issuer, audience=_parse_aud(settings.auth_audience), jwks=jwks
    )


def decode_verify_any(
    token: str,
    settings: Any,
    jwks_main: JWKSProvider,
    jwks_occupants: JWKSProvider | None,
) -> tuple[dict[str, Any], str]:
    """``(claims, pool)`` con ``pool ∈ {'main','occupants'}`` — dual-issuer T-2.03.

    El ``iss`` SIN verificar solo ENRUTA a la config del pool; la verificación
    dura (firma/iss/aud/exp/token_use) ocurre contra esa config. Con el pool de
    ocupantes deshabilitado (issuer vacío) el comportamiento single-issuer queda
    intacto. El ancla pool→rol vive en ``deps.get_claims`` (necesita ``Claims``).
    """
    occ_issuer = getattr(settings, "auth_occupants_issuer", "") or ""
    if occ_issuer and jwks_occupants is not None:
        try:
            unverified = jwt.decode(token, options={"verify_signature": False})
        except jwt.PyJWTError as exc:
            raise AuthError("malformed token") from exc
        if unverified.get("iss") == occ_issuer:
            claims = _decode(
                token,
                issuer=occ_issuer,
                audience=_parse_aud(settings.auth_occupants_audience),
                jwks=jwks_occupants,
            )
            return claims, "occupants"
    return decode_verify(token, settings, jwks_main), "main"
