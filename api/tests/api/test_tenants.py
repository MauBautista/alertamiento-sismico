"""Tests del catálogo de tenants (T-1.22 · B1): visibilidad por rol (RBAC §2)."""

from __future__ import annotations

import os

import pytest
from fastapi import FastAPI
from sqlalchemy import text

import auth_utils as au
from takab_api.auth import deps
from takab_api.db.engine import get_engine
from takab_api.routers.tenants import router as tenants_router

T_A = "81111111-1111-1111-1111-111111111111"  # private
T_B = "82222222-2222-2222-2222-222222222222"  # private
T_GOV = "83333333-3333-3333-3333-333333333333"  # gov_shared

_TENANTS = (T_A, T_B, T_GOV)
_CLEANUP = text("DELETE FROM tenants WHERE tenant_id = ANY(:t)")


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
        await conn.execute(_CLEANUP, {"t": list(_TENANTS)})


@pytest.fixture
async def seed() -> None:
    """3 tenants: A/B private, G gov_shared."""
    await _cleanup()
    engine = get_engine()
    async with engine.begin() as conn:
        for tid, code, vis in (
            (T_A, "B1TEN_A", "private"),
            (T_B, "B1TEN_B", "private"),
            (T_GOV, "B1TEN_G", "gov_shared"),
        ):
            await conn.execute(
                text(
                    "INSERT INTO tenants (tenant_id, code, name, visibility) "
                    "VALUES (:id, :code, 'B1', :vis)"
                ),
                {"id": tid, "code": code, "vis": vis},
            )
    yield
    await _cleanup()
    await engine.dispose()
    get_engine.cache_clear()


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(tenants_router)
    return app


async def _get(token: str):
    async with au.client_for(_app()) as c:
        return await c.get("/tenants", headers=au.bearer(token))


async def test_superadmin_sees_all_tenants(seed: None) -> None:
    resp = await _get(au.make_token("takab_superadmin", tenant=T_A))
    assert resp.status_code == 200
    ids = {t["tenant_id"] for t in resp.json()}
    assert {T_A, T_B, T_GOV} <= ids
    row = next(t for t in resp.json() if t["tenant_id"] == T_GOV)
    assert row["visibility"] == "gov_shared"
    assert row["isolation_mode"] == "logical"


async def test_support_sees_all_tenants(seed: None) -> None:
    resp = await _get(au.make_token("takab_support", tenant=T_A))
    assert resp.status_code == 200
    ids = {t["tenant_id"] for t in resp.json()}
    assert {T_A, T_B, T_GOV} <= ids


async def test_tenant_admin_sees_only_own_row(seed: None) -> None:
    resp = await _get(au.make_token("tenant_admin", tenant=T_A))
    assert resp.status_code == 200
    ids = {t["tenant_id"] for t in resp.json()}
    assert ids == {T_A}  # RLS: solo su propia fila (no B, no G)


@pytest.mark.parametrize("role", ["soc_operator", "gov_operator", "inspector", "building_admin"])
async def test_role_without_multitenant_forbidden(seed: None, role: str) -> None:
    resp = await _get(au.make_token(role, tenant=T_A))
    assert resp.status_code == 403


async def test_unauthenticated_rejected() -> None:
    async with au.client_for(_app()) as c:
        resp = await c.get("/tenants")
    assert resp.status_code == 401
