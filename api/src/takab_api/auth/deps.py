"""Dependencias FastAPI de auth (T-1.18 · fase B).

Ensambla la verificación de token (fase A: tokens/claims/jwks) con la sesión DB
async (fase A: db.session) para exponer a los routers:

- ``get_claims``          — extrae y valida el Bearer → ``Claims`` (o 401).
- ``require_roles(*r)``    — factoría de guard por rol (403 si ``role`` ∉ ``r``).
- ``require_web_surface``  — 403 si la superficie del token no habilita web.
- ``get_session``         — abre ``get_tenant_conn`` con los GUCs del request.

El ``JWKSProvider`` y los ``Settings`` se cachean a nivel módulo (no se
reconstruyen por request); en tests se limpian los caches al fijar el entorno.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from functools import lru_cache

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.auth.claims import Claims
from takab_api.auth.jwks import JWKSProvider, select_jwks, select_jwks_occupants
from takab_api.auth.tokens import AuthError, decode_verify_any
from takab_api.db.session import SessionCtx, get_tenant_conn
from takab_api.settings import Settings

# Superficies del token que pueden usar el SOC web.
_WEB_SURFACES = frozenset({"web", "both"})

# Superficies del token que pueden usar la app móvil (T-2.03).
_MOBILE_SURFACES = frozenset({"mobile", "both"})

# Reto para el cliente ante 401 (RFC 6750).
_BEARER_CHALLENGE = {"WWW-Authenticate": "Bearer"}


@lru_cache(maxsize=1)
def _settings() -> Settings:
    return Settings()


@lru_cache(maxsize=1)
def _jwks() -> JWKSProvider:
    return select_jwks(_settings())


@lru_cache(maxsize=1)
def _jwks_occupants() -> JWKSProvider | None:
    return select_jwks_occupants(_settings(), _jwks())


def _reset_caches() -> None:
    """Limpia los caches de settings/JWKS (uso en tests al cambiar el entorno)."""
    _settings.cache_clear()
    _jwks.cache_clear()
    _jwks_occupants.cache_clear()


def get_claims(request: Request) -> Claims:
    """Valida ``Authorization: Bearer <id_token>`` → ``Claims``; si no, 401.

    Dual-issuer (T-2.03, decisión #7) con ANCLA pool→rol: un token del pool de
    ocupantes SOLO puede portar ``role=occupant`` y un ``occupant`` SOLO puede
    venir de ese pool — el cruce en cualquier dirección es 401 (token forjado o
    usuario dado de alta en el pool equivocado; specs/cognito-pool-v1.md §5.2).
    """
    header = request.headers.get("Authorization") or ""
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=401, detail="missing bearer token", headers=_BEARER_CHALLENGE
        )
    try:
        verified, pool = decode_verify_any(token.strip(), _settings(), _jwks(), _jwks_occupants())
        claims = Claims.from_verified(verified)
        if pool == "occupants" and claims.role != "occupant":
            raise AuthError("el pool de ocupantes solo emite occupant")
        if pool == "main" and claims.role == "occupant" and _jwks_occupants() is not None:
            raise AuthError("occupant debe autenticarse en el pool de ocupantes")
        return claims
    except AuthError as exc:
        raise HTTPException(
            status_code=exc.status, detail=exc.reason, headers=_BEARER_CHALLENGE
        ) from exc


def require_roles(*roles: str) -> Callable[[Claims], Claims]:
    """Devuelve una dependencia que exige ``claims.role`` ∈ ``roles`` (o 403)."""
    allowed = frozenset(roles)

    def _dep(claims: Claims = Depends(get_claims)) -> Claims:
        if claims.role not in allowed:
            raise HTTPException(status_code=403, detail="rol sin acceso a este recurso")
        return claims

    return _dep


def require_web_surface(claims: Claims = Depends(get_claims)) -> Claims:
    """403 si la superficie del token no habilita web (móvil-only → fuera del SOC)."""
    if claims.surface not in _WEB_SURFACES:
        raise HTTPException(status_code=403, detail="superficie no habilita web")
    return claims


def require_mobile_surface(claims: Claims = Depends(get_claims)) -> Claims:
    """403 si la superficie del token no habilita la app móvil (T-2.03)."""
    if claims.surface not in _MOBILE_SURFACES:
        raise HTTPException(status_code=403, detail="superficie no habilita móvil")
    return claims


async def get_session(
    claims: Claims = Depends(get_claims),
) -> AsyncIterator[AsyncConnection]:
    """Conexión async con rol ``takab_app`` + GUCs del request en la transacción.

    Commit al terminar el request sin error; rollback si el handler lanza. Es la
    dependencia que usan los routers que tocan datos con RLS por tenant.
    """
    async with get_tenant_conn(SessionCtx.from_claims(claims)) as conn:
        yield conn
