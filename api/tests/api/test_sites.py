"""Tests del catálogo de sitios (T-1.22 · B1): 200, detalle+zonas, RLS y autz."""

from __future__ import annotations

import os

import pytest
from fastapi import FastAPI
from sqlalchemy import text

import auth_utils as au
from takab_api.auth import deps
from takab_api.db.engine import get_engine
from takab_api.routers.sites import router as sites_router

# UUIDs B1 (prefijo 8: no colisiona con los seeds sync 1/2/3/9/a/b/c ni async 7).
T_A = "81111111-1111-1111-1111-111111111111"  # private
T_B = "82222222-2222-2222-2222-222222222222"  # private (fuga cross-tenant)
T_GOV = "83333333-3333-3333-3333-333333333333"  # gov_shared
S_A = "8a000000-0000-0000-0000-0000000000a1"
S_B = "8b000000-0000-0000-0000-0000000000b1"
S_GOV = "8c000000-0000-0000-0000-0000000000c1"
Z_A = "8e000000-0000-0000-0000-0000000000e1"

_GEOM = "ST_SetSRID(ST_MakePoint(-99.13,19.43),4326)::geography"
_TENANTS = (T_A, T_B, T_GOV)
_CLEANUP = (
    text("DELETE FROM zones WHERE tenant_id = ANY(:t)"),
    text("DELETE FROM sites WHERE tenant_id = ANY(:t)"),
    text("DELETE FROM tenants WHERE tenant_id = ANY(:t)"),
)


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
        for stmt in _CLEANUP:
            await conn.execute(stmt, {"t": list(_TENANTS)})


@pytest.fixture
async def seed() -> None:
    """3 tenants (A/B private, G gov_shared) + un sitio cada uno + una zona en A."""
    await _cleanup()
    engine = get_engine()
    async with engine.begin() as conn:
        for tid, code, vis in (
            (T_A, "B1SITE_A", "private"),
            (T_B, "B1SITE_B", "private"),
            (T_GOV, "B1SITE_G", "gov_shared"),
        ):
            await conn.execute(
                text(
                    "INSERT INTO tenants (tenant_id, code, name, visibility) "
                    "VALUES (:id, :code, 'B1', :vis)"
                ),
                {"id": tid, "code": code, "vis": vis},
            )
        for sid, tid, code in ((S_A, T_A, "SA"), (S_B, T_B, "SB"), (S_GOV, T_GOV, "SG")):
            await conn.execute(
                text(
                    "INSERT INTO sites (site_id, tenant_id, code, name, geom) "
                    f"VALUES (:sid, :tid, :code, 'Sitio', {_GEOM})"
                ),
                {"sid": sid, "tid": tid, "code": code},
            )
        await conn.execute(
            text(
                "INSERT INTO zones (zone_id, tenant_id, site_id, name, level_code) "
                "VALUES (:z, :t, :s, 'Planta baja', 'PB')"
            ),
            {"z": Z_A, "t": T_A, "s": S_A},
        )
    yield
    await _cleanup()
    await engine.dispose()
    get_engine.cache_clear()


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(sites_router)
    return app


async def _get(path: str, token: str):
    async with au.client_for(_app()) as c:
        return await c.get(path, headers=au.bearer(token))


async def test_list_sites_scoped_to_tenant(seed: None) -> None:
    resp = await _get("/sites", au.make_token("soc_operator", tenant=T_A))
    assert resp.status_code == 200
    body = resp.json()
    ids = {s["site_id"] for s in body}
    assert ids == {S_A}  # solo el sitio del tenant A (RLS)
    site = body[0]
    assert site["lat"] == pytest.approx(19.43)
    assert site["lon"] == pytest.approx(-99.13)


async def test_get_site_detail_with_zones(seed: None) -> None:
    resp = await _get(f"/sites/{S_A}", au.make_token("soc_operator", tenant=T_A))
    assert resp.status_code == 200
    body = resp.json()
    assert body["site_id"] == S_A
    assert [z["zone_id"] for z in body["zones"]] == [Z_A]
    assert body["zones"][0]["level_code"] == "PB"


async def test_rls_tenant_a_cannot_see_b_site(seed: None) -> None:
    resp = await _get(f"/sites/{S_B}", au.make_token("soc_operator", tenant=T_A))
    assert resp.status_code == 404


async def test_superadmin_sees_all_sites(seed: None) -> None:
    resp = await _get("/sites", au.make_token("takab_superadmin", tenant=T_A))
    assert resp.status_code == 200
    ids = {s["site_id"] for s in resp.json()}
    assert {S_A, S_B, S_GOV} <= ids  # interno TAKAB ve todos los tenants


async def test_mobile_only_role_forbidden(seed: None) -> None:
    resp = await _get("/sites", au.make_token("occupant", tenant=T_A, surface="mobile"))
    assert resp.status_code == 403


async def test_unauthenticated_rejected() -> None:
    async with au.client_for(_app()) as c:
        resp = await c.get("/sites")
    assert resp.status_code == 401
