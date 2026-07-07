"""GET /me: cada rol recibe sus rutas/acciones (RBAC §2/§7); sin token → 401."""

from __future__ import annotations

import pytest

import auth_utils as au
from takab_api.auth.matrix import ACTIONS, allowed_actions, allowed_routes

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


async def test_me_openapi_publishes_typed_response(client) -> None:
    """El 200 de /me se publica tipado (MeResponse) para el sdk-ts (T-1.26).

    Sin ``response_model`` el OpenAPI emite un objeto libre y el cliente TS
    generado queda como ``{[key: string]: unknown}`` — inservible para guards.
    """
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200
    spec = resp.json()
    media = spec["paths"]["/me"]["get"]["responses"]["200"]["content"]["application/json"]
    assert media["schema"].get("$ref") == "#/components/schemas/MeResponse"
    me_props = spec["components"]["schemas"]["MeResponse"]["properties"]
    assert set(me_props) == {
        "sub",
        "tenant_id",
        "role",
        "site_scope",
        "surface",
        "allowed_routes",
        "allowed_actions",
    }
    # allowed_actions con claves fijas (espejo de matrix.ACTIONS), no dict libre.
    action_props = spec["components"]["schemas"]["MeActions"]["properties"]
    assert set(action_props) == set(ACTIONS)


async def test_me_without_token_is_401(client) -> None:
    resp = await client.get("/me")
    assert resp.status_code == 401
    assert resp.headers.get("WWW-Authenticate") == "Bearer"


async def test_me_with_invalid_token_is_401(client) -> None:
    resp = await client.get("/me", headers=au.bearer(au.expired_token("soc_operator")))
    assert resp.status_code == 401
