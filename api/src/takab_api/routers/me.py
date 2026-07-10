"""GET /me — identidad + rutas/acciones del rol (RBAC §2/§7). No toca la DB.

/me/profile (T-1.48) — nombre de operador editable. Deliberadamente SEPARADO de
GET /me: /me sigue siendo claims puros sin conexión a DB (latencia y contrato
intactos); el perfil es presentación y vive en ``user_profiles`` bajo RLS
self-write (cualquier rol web edita SU nombre — la política acota la fila).
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.audit import audit_async
from takab_api.auth.claims import ALL_SITES, Claims
from takab_api.auth.deps import get_claims, get_session, require_web_surface
from takab_api.auth.matrix import allowed_actions, allowed_routes
from takab_api.schemas.me import MeActions, MeResponse, ProfileOut, ProfilePutIn

router = APIRouter()


@router.get("/me", response_model=MeResponse)
def me(claims: Claims = Depends(get_claims)) -> MeResponse:
    """Perfil del portador del token: qué ve y qué puede hacer en el SOC web.

    ``site_scope`` sale como ``"*"`` (todo el tenant) o lista ordenada de sitios
    (posiblemente vacía = default-deny). Un rol móvil-only devuelve rutas vacías.
    """
    site_scope: Literal["*"] | list[str]
    if claims.site_scope is ALL_SITES:
        site_scope = "*"
    else:
        site_scope = sorted(claims.site_scope)
    return MeResponse(
        sub=claims.sub,
        tenant_id=claims.tenant_id,
        role=claims.role,
        site_scope=site_scope,
        surface=claims.surface,
        allowed_routes=allowed_routes(claims.role),
        allowed_actions=MeActions(**allowed_actions(claims.role)),
    )


_SELECT_PROFILE = text(
    "SELECT user_sub, display_name, updated_at FROM user_profiles "
    "WHERE user_sub = CAST(:sub AS uuid)"
)

_UPSERT_PROFILE = text(
    "INSERT INTO user_profiles (user_sub, tenant_id, display_name) "
    "VALUES (CAST(:sub AS uuid), CAST(:tenant AS uuid), :name) "
    "ON CONFLICT (user_sub) DO UPDATE "
    "SET display_name = EXCLUDED.display_name, updated_at = now() "
    "RETURNING user_sub, display_name, updated_at"
)


@router.get("/me/profile", response_model=ProfileOut)
async def get_profile(
    claims: Claims = Depends(require_web_surface),
    conn: AsyncConnection = Depends(get_session),
) -> ProfileOut:
    """Perfil de presentación del portador. Sin fila = campos null (200)."""
    row = (await conn.execute(_SELECT_PROFILE, {"sub": claims.sub})).first()
    if row is None:
        return ProfileOut(user_sub=claims.sub, display_name=None, updated_at=None)
    return ProfileOut(
        user_sub=row.user_sub, display_name=row.display_name, updated_at=row.updated_at
    )


@router.put("/me/profile", response_model=ProfileOut)
async def put_profile(
    body: ProfilePutIn,
    claims: Claims = Depends(require_web_surface),
    conn: AsyncConnection = Depends(get_session),
) -> ProfileOut:
    """Upsert del nombre PROPIO (RLS self-write acota la fila). Auditado."""
    row = (
        await conn.execute(
            _UPSERT_PROFILE,
            {"sub": claims.sub, "tenant": claims.tenant_id, "name": body.display_name},
        )
    ).first()
    await audit_async(
        conn,
        tenant_id=claims.tenant_id,
        actor=f"user:{claims.sub}",
        verb="profile_update",
        obj=f"user:{claims.sub}",
        meta={"display_name": body.display_name},
    )
    return ProfileOut(
        user_sub=row.user_sub, display_name=row.display_name, updated_at=row.updated_at
    )
