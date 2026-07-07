"""Parseo de claims verificados a un contexto de seguridad inmutable.

``site_scope`` es **default-deny** ([ANALISIS-00], RBAC §5.2): ausente/vacío =
cero sitios; ``"*"`` = todo el tenant (sentinel ``ALL_SITES``); CSV = conjunto.
``role`` debe pertenecer a ``cognito:groups`` o es un token forjado.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from takab_api.auth.tokens import AuthError

_SURFACES = frozenset({"web", "mobile", "both"})


class _AllSites:
    """Sentinel: acceso a todos los sitios del tenant (``site_scope == '*'``)."""

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - solo depuración
        return "ALL_SITES"


ALL_SITES = _AllSites()

# Un site_scope es o el sentinel ALL_SITES o un conjunto (posiblemente vacío).
SiteScope = frozenset  # alias documental


def _parse_site_scope(raw: Any) -> frozenset[str] | _AllSites:
    if raw is None:
        return frozenset()
    if isinstance(raw, (list, tuple)):
        raw = ",".join(str(x) for x in raw)
    raw = str(raw).strip()
    if raw == "":
        return frozenset()
    if raw == "*":
        return ALL_SITES
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


@dataclass(frozen=True)
class Claims:
    """Contexto de seguridad del request derivado del ID token."""

    sub: str
    groups: tuple[str, ...]
    tenant_id: str
    role: str
    site_scope: frozenset[str] | _AllSites
    zone_id: str
    surface: str

    @classmethod
    def from_verified(cls, claims: dict[str, Any]) -> Claims:
        groups = tuple(claims.get("cognito:groups") or ())
        role = claims.get("custom:role") or ""
        if role not in groups:
            raise AuthError("role not in groups")

        surface = claims.get("custom:surface") or ""
        if surface not in _SURFACES:
            raise AuthError(f"invalid surface: {surface!r}")

        # Integridad de tenant_id (regla de oro #5): el token no trae una segunda
        # fuente para corroborarlo, así que su binding es upstream — el app client
        # SPA de Cognito omite los custom:* de write_attributes, de modo que solo
        # el admin puede fijar custom:tenant_id (como cognito:groups). Ver
        # infra/terraform/modules/identity/main.tf y specs/cognito-pool-v1.md §3.
        return cls(
            sub=claims.get("sub") or "",
            groups=groups,
            tenant_id=claims.get("custom:tenant_id") or "",
            role=role,
            site_scope=_parse_site_scope(claims.get("custom:site_scope")),
            zone_id=claims.get("custom:zone_id") or "",
            surface=surface,
        )


def scope_filter(claims: Claims) -> frozenset[str] | None:
    """``None`` = sin filtro (ALL_SITES); si no, el conjunto para ``site_id = ANY(...)``.

    Un conjunto vacío filtra a cero filas (default-deny), que es lo correcto.
    """
    if claims.site_scope is ALL_SITES:
        return None
    return claims.site_scope
