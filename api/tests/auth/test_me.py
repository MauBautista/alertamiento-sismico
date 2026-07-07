"""GET /me: cada rol recibe sus rutas/acciones (RBAC §2/§7); sin token → 401."""

from __future__ import annotations

import pytest

import auth_utils as au
from takab_api.auth.matrix import allowed_actions, allowed_routes

ALL_ROLES = [
    "takab_superadmin",
    "takab_support",
    "tenant_admin",
    "soc_operator",
    "gov_operator",
    "inspector",
    "building_admin",
    "brigadista",
    "security_guard",
    "occupant",
]

MOBILE_ONLY = {"brigadista", "security_guard", "occupant"}


@pytest.mark.parametrize("role", ALL_ROLES)
async def test_me_returns_role_matrix(client, role: str) -> None:
    token = au.make_token(role, tenant=au.TENANT_A, site_scope="*")
    resp = await client.get("/me", headers=au.bearer(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == role
    assert body["tenant_id"] == au.TENANT_A
    assert body["site_scope"] == "*"
    assert body["allowed_routes"] == allowed_routes(role)
    assert body["allowed_actions"] == allowed_actions(role)


@pytest.mark.parametrize("role", sorted(MOBILE_ONLY))
async def test_mobile_only_roles_have_empty_routes(client, role: str) -> None:
    token = au.make_token(role, tenant=au.TENANT_A, surface="mobile", site_scope="")
    resp = await client.get("/me", headers=au.bearer(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["allowed_routes"] == []
    # site_scope default-deny: ausente/"" → lista vacía (no "*").
    assert body["site_scope"] == []


async def test_site_scope_csv_is_sorted_list(client) -> None:
    scope = f"{au.DB_SITE_PRIV2},{au.DB_SITE_PRIV}"
    token = au.make_token("inspector", tenant=au.TENANT_A, site_scope=scope)
    resp = await client.get("/me", headers=au.bearer(token))
    assert resp.status_code == 200
    assert resp.json()["site_scope"] == sorted([au.DB_SITE_PRIV, au.DB_SITE_PRIV2])


async def test_me_without_token_is_401(client) -> None:
    resp = await client.get("/me")
    assert resp.status_code == 401
    assert resp.headers.get("WWW-Authenticate") == "Bearer"


async def test_me_with_invalid_token_is_401(client) -> None:
    resp = await client.get("/me", headers=au.bearer(au.expired_token("soc_operator")))
    assert resp.status_code == 401
