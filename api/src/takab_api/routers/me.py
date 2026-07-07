"""GET /me — identidad + rutas/acciones del rol (RBAC §2/§7). No toca la DB."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from takab_api.auth.claims import ALL_SITES, Claims
from takab_api.auth.deps import get_claims
from takab_api.auth.matrix import allowed_actions, allowed_routes

router = APIRouter()


@router.get("/me")
def me(claims: Claims = Depends(get_claims)) -> dict[str, Any]:
    """Perfil del portador del token: qué ve y qué puede hacer en el SOC web.

    ``site_scope`` sale como ``"*"`` (todo el tenant) o lista ordenada de sitios
    (posiblemente vacía = default-deny). Un rol móvil-only devuelve rutas vacías.
    """
    if claims.site_scope is ALL_SITES:
        site_scope: Any = "*"
    else:
        site_scope = sorted(claims.site_scope)
    return {
        "sub": claims.sub,
        "tenant_id": claims.tenant_id,
        "role": claims.role,
        "site_scope": site_scope,
        "surface": claims.surface,
        "allowed_routes": allowed_routes(claims.role),
        "allowed_actions": allowed_actions(claims.role),
    }
