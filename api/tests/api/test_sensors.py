"""Tests del catálogo de sensores (T-1.22 · B1): 200, RLS por sitio, param y autz."""

from __future__ import annotations

import os

import pytest
from fastapi import FastAPI
from sqlalchemy import text

import auth_utils as au
from takab_api.auth import deps
from takab_api.db.engine import get_engine
from takab_api.routers.sensors import router as sensors_router

T_A = "81111111-1111-1111-1111-111111111111"
T_B = "82222222-2222-2222-2222-222222222222"
S_A = "8a000000-0000-0000-0000-0000000000a1"
S_B = "8b000000-0000-0000-0000-0000000000b1"
SEN_A = "8f000000-0000-0000-0000-0000000000f1"
SEN_B = "8f000000-0000-0000-0000-0000000000f2"

_GEOM = "ST_SetSRID(ST_MakePoint(-99.13,19.43),4326)::geography"
_TENANTS = (T_A, T_B)
_CLEANUP = (
    text("DELETE FROM sensors WHERE tenant_id = ANY(:t)"),
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
    """2 tenants privados + un sitio y un sensor en cada uno."""
    await _cleanup()
    engine = get_engine()
    async with engine.begin() as conn:
        for tid, code in ((T_A, "B1SEN_A"), (T_B, "B1SEN_B")):
            await conn.execute(
                text("INSERT INTO tenants (tenant_id, code, name) VALUES (:id, :code, 'B1')"),
                {"id": tid, "code": code},
            )
        for sid, tid in ((S_A, T_A), (S_B, T_B)):
            await conn.execute(
                text(
                    "INSERT INTO sites (site_id, tenant_id, code, name, geom) "
                    f"VALUES (:sid, :tid, :code, 'Sitio', {_GEOM})"
                ),
                {"sid": sid, "tid": tid, "code": sid[:6]},
            )
        for sen, tid, sid, serial in (
            (SEN_A, T_A, S_A, "SEN-A"),
            (SEN_B, T_B, S_B, "SEN-B"),
        ):
            await conn.execute(
                text(
                    "INSERT INTO sensors (sensor_id, tenant_id, site_id, kind, model, serial) "
                    "VALUES (:sen, :t, :s, 'ground', 'RS4D', :serial)"
                ),
                {"sen": sen, "t": tid, "s": sid, "serial": serial},
            )
    yield
    await _cleanup()
    await engine.dispose()
    get_engine.cache_clear()


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(sensors_router)
    return app


async def _get(path: str, token: str):
    async with au.client_for(_app()) as c:
        return await c.get(path, headers=au.bearer(token))


async def test_list_sensors_by_site(seed: None) -> None:
    resp = await _get(f"/sensors?site_id={S_A}", au.make_token("soc_operator", tenant=T_A))
    assert resp.status_code == 200
    body = resp.json()
    assert [s["sensor_id"] for s in body] == [SEN_A]
    sensor = body[0]
    assert sensor["kind"] == "ground"
    assert sensor["model"] == "RS4D"
    assert sensor["channels"] == ["EHZ", "ENZ", "ENN", "ENE"]
    assert sensor["sample_rate"] == 100


async def test_rls_other_tenant_site_returns_empty(seed: None) -> None:
    # Tenant A pide el sitio de B: RLS tapa sus sensores -> lista vacía (no fuga).
    resp = await _get(f"/sensors?site_id={S_B}", au.make_token("soc_operator", tenant=T_A))
    assert resp.status_code == 200
    assert resp.json() == []


async def test_missing_site_id_is_422(seed: None) -> None:
    resp = await _get("/sensors", au.make_token("soc_operator", tenant=T_A))
    assert resp.status_code == 422


async def test_mobile_only_role_forbidden(seed: None) -> None:
    resp = await _get(
        f"/sensors?site_id={S_A}", au.make_token("occupant", tenant=T_A, surface="mobile")
    )
    assert resp.status_code == 403


async def test_unauthenticated_rejected() -> None:
    async with au.client_for(_app()) as c:
        resp = await c.get(f"/sensors?site_id={S_A}")
    assert resp.status_code == 401
