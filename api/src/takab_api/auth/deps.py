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

import logging
from collections.abc import AsyncIterator, Callable
from functools import lru_cache

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.audit import audit_async
from takab_api.auth.claims import Claims
from takab_api.auth.jwks import JWKSProvider, select_jwks, select_jwks_occupants
from takab_api.auth.scope import ConsoleScope, console_scope
from takab_api.auth.tokens import (
    POOL_OCUPANTES,
    POOL_PRINCIPAL,
    AuthError,
    decode_verify_any,
)
from takab_api.db.session import SessionCtx, get_tenant_conn
from takab_api.settings import Settings

# Superficies del token que pueden usar el SOC web.
log = logging.getLogger("takab_api.auth")

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
        # [T-2.84.b] La procedencia entra en el contexto de seguridad, no se
        # descarta aquí: el pool es quien porta la política de MFA y el camino de
        # comando de actuadores la exige (`auth/mfa.py`, regla de oro 8).
        claims = Claims.from_verified(verified, pool=pool)
        if pool == POOL_OCUPANTES and claims.role != "occupant":
            raise AuthError("el pool de ocupantes solo emite occupant")
        if pool == POOL_PRINCIPAL and claims.role == "occupant" and _jwks_occupants() is not None:
            raise AuthError("occupant debe autenticarse en el pool de ocupantes")
        return claims
    except AuthError as exc:
        raise HTTPException(
            status_code=exc.status, detail=exc.reason, headers=_BEARER_CHALLENGE
        ) from exc


def require_roles(
    *roles: str, inner: Callable[..., Claims] = get_claims
) -> Callable[[Claims], Claims]:
    """Devuelve una dependencia que exige ``claims.role`` ∈ ``roles`` (o 403).

    ``inner`` permite anteponer otra guarda sobre el mismo ``Claims`` sin duplicar
    la resolución del token (FastAPI cachea ``get_claims`` por request). Lo usa el
    camino de comando de actuadores para exigir la constancia de MFA **antes** que
    el rol: la fuerza de la autenticación es una propiedad de la credencial y no
    puede quedar condicionada al catálogo de roles (T-2.84.b, ``auth/mfa.py``).
    """
    allowed = frozenset(roles)

    def _dep(claims: Claims = Depends(inner)) -> Claims:
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


# --- Alcance por sitio de la consola (T-2.45) ---------------------------------

#: Huecos de alcance ya auditados en ESTE proceso, como ``(tenant_id, sub)``.
#:
#: La regla de oro 10 es logging por transición de estado, no por intervalo: auditar el
#: hueco en cada request lo convertiría en ruido de alto volumen sobre una tabla que no
#: se poda nunca (regla 11). Una fila por usuario y por proceso basta para que el hueco
#: sea contable, y el reinicio del proceso lo vuelve a levantar.
_scope_gaps_seen: set[tuple[str, str]] = set()


def _reset_scope_gaps_for_tests() -> None:
    _scope_gaps_seen.clear()


async def get_console_scope(
    claims: Claims = Depends(get_claims),
    conn: AsyncConnection = Depends(get_session),
) -> ConsoleScope:
    """Alcance por sitio del request, auditando el hueco la primera vez que se ve."""
    scope = console_scope(claims, enforced=_settings().console_scope_enforced)
    key = (claims.tenant_id, claims.sub)
    if scope.gap and key not in _scope_gaps_seen:
        _scope_gaps_seen.add(key)
        try:
            await audit_async(
                conn,
                tenant_id=claims.tenant_id,
                actor=f"user:{claims.sub}",
                verb="scope_gap",
                obj=f"role:{claims.role}",
                meta={"reason": "custom:site_scope no aprovisionado", "enforced": False},
            )
        except Exception:  # noqa: BLE001 - auditar el hueco no puede tumbar la consola
            _scope_gaps_seen.discard(key)
            log.warning("no se pudo auditar el scope_gap de %s", claims.sub, exc_info=True)
    return scope
