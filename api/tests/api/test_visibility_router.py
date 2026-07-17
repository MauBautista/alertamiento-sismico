"""API de grants de visibilidad (T-1.73): CRUD + authz (solo superadmin) + validación.

Usa el catálogo prefijo 8 (disjunto del seed DEV), como el resto de tests/api/.
"""

from __future__ import annotations

import os

import pytest
from fastapi import FastAPI
from sqlalchemy import text

import auth_utils as au
from takab_api.auth import deps
from takab_api.db.engine import get_engine
from takab_api.routers.visibility import router as visibility_router

T_A = "81111111-1111-1111-1111-111111111111"  # private
T_B = "82222222-2222-2222-2222-222222222222"  # private
T_GOV = "83333333-3333-3333-3333-333333333333"  # gov_shared
_TENANTS = (T_A, T_B, T_GOV)


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAKAB_API_AUTH_ISSUER", au.ISSUER)
    monkeypatch.setenv("TAKAB_API_AUTH_AUDIENCE", au.AUDIENCE)
    monkeypatch.setenv("TAKAB_API_AUTH_JWKS_JSON", au.jwks_json())
    dsn = os.environ.get("DATABASE_URL")
    if dsn:
        monkeypatch.setenv("TAKAB_API_DATABASE_URL", dsn)
    deps._reset_caches()
    get_engine.cache_clear()
    yield
    deps._reset_caches()


async def _cleanup() -> None:
    async with get_engine().begin() as conn:
        # los grants caen por CASCADE al borrar tenants; explícito por claridad.
        await conn.execute(
            text("DELETE FROM visibility_grants WHERE grantee_tenant_id = ANY(:t)"),
            {"t": list(_TENANTS)},
        )
        await conn.execute(
            text("DELETE FROM tenants WHERE tenant_id = ANY(:t)"), {"t": list(_TENANTS)}
        )


@pytest.fixture
async def seed() -> None:
    await _cleanup()
    engine = get_engine()
    async with engine.begin() as conn:
        for tid, code, vis in (
            (T_A, "V_A", "private"),
            (T_B, "V_B", "private"),
            (T_GOV, "V_G", "gov_shared"),
        ):
            await conn.execute(
                text(
                    "INSERT INTO tenants (tenant_id, code, name, visibility) VALUES (:id,:c,'V',:v)"
                ),
                {"id": tid, "c": code, "v": vis},
            )
    yield
    await _cleanup()
    await engine.dispose()
    get_engine.cache_clear()


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(visibility_router)
    return app


def _su() -> str:
    return au.make_token("takab_superadmin", tenant=T_A)


async def _post(token: str, body: dict):
    async with au.client_for(_app()) as c:
        return await c.post("/visibility-grants", headers=au.bearer(token), json=body)


async def _get(token: str, query: str = ""):
    async with au.client_for(_app()) as c:
        return await c.get(f"/visibility-grants{query}", headers=au.bearer(token))


async def _delete(token: str, grant_id: str):
    async with au.client_for(_app()) as c:
        return await c.delete(f"/visibility-grants/{grant_id}", headers=au.bearer(token))


async def test_superadmin_creates_and_lists_grant(seed: None) -> None:
    resp = await _post(
        _su(), {"grantee_tenant_id": T_B, "target_tenant_id": T_A, "can_view_metadata": True}
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["grantee_tenant_id"] == T_B
    assert body["target_tenant_id"] == T_A
    assert body["target_all"] is False
    assert body["can_view_metadata"] is True
    assert body["can_view_data"] is False

    lst = await _get(_su())
    assert lst.status_code == 200
    assert any(g["grant_id"] == body["grant_id"] for g in lst.json())


async def test_upsert_updates_existing_grant(seed: None) -> None:
    a = await _post(
        _su(), {"grantee_tenant_id": T_B, "target_tenant_id": T_A, "can_view_metadata": True}
    )
    b = await _post(
        _su(),
        {
            "grantee_tenant_id": T_B,
            "target_tenant_id": T_A,
            "can_view_metadata": True,
            "can_view_data": True,
        },
    )
    assert a.status_code == 201 and b.status_code == 201
    assert a.json()["grant_id"] == b.json()["grant_id"]  # mismo grant, actualizado
    assert b.json()["can_view_data"] is True


async def test_delete_grant_then_404(seed: None) -> None:
    gid = (
        await _post(
            _su(), {"grantee_tenant_id": T_B, "target_tenant_id": T_A, "can_view_data": True}
        )
    ).json()["grant_id"]
    assert (await _delete(_su(), gid)).status_code == 204
    assert (await _delete(_su(), gid)).status_code == 404


async def test_target_all_grant(seed: None) -> None:
    resp = await _post(
        _su(), {"grantee_tenant_id": T_B, "target_all": True, "can_view_metadata": True}
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["target_all"] is True
    assert resp.json()["target_tenant_id"] is None


@pytest.mark.parametrize("role", ["tenant_admin", "takab_support", "soc_operator", "gov_operator"])
async def test_non_superadmin_forbidden(seed: None, role: str) -> None:
    tok = au.make_token(role, tenant=T_A, site_scope="*", surface="web")
    assert (
        await _post(tok, {"grantee_tenant_id": T_B, "target_all": True, "can_view_metadata": True})
    ).status_code == 403
    assert (await _get(tok)).status_code == 403


async def test_invalid_target_shape_is_422(seed: None) -> None:
    # ni target específico ni ALL
    assert (
        await _post(_su(), {"grantee_tenant_id": T_B, "can_view_metadata": True})
    ).status_code == 422
    # ambos a la vez
    assert (
        await _post(
            _su(),
            {
                "grantee_tenant_id": T_B,
                "target_tenant_id": T_A,
                "target_all": True,
                "can_view_metadata": True,
            },
        )
    ).status_code == 422


async def test_self_grant_is_422(seed: None) -> None:
    r = await _post(
        _su(), {"grantee_tenant_id": T_A, "target_tenant_id": T_A, "can_view_metadata": True}
    )
    assert r.status_code == 422


async def test_empty_grant_is_422(seed: None) -> None:
    r = await _post(_su(), {"grantee_tenant_id": T_B, "target_tenant_id": T_A})
    assert r.status_code == 422


async def test_nonexistent_tenant_is_400(seed: None) -> None:
    ghost = "00000000-0000-0000-0000-0000000000ff"
    r = await _post(
        _su(), {"grantee_tenant_id": T_B, "target_tenant_id": ghost, "can_view_metadata": True}
    )
    assert r.status_code == 400  # viola la FK → integrity_error
