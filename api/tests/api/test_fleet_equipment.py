"""Perfil de equipamiento por gateway (T-2.31).

``gateways.equipment`` declara qué actuadores están INSTALADOS en el sitio (no
toda estación tiene gas/ascensores/puertas). Contrato: objeto de 5 bools con
default todo-true (compat retro), claves desconocidas rechazadas (422 — un typo
en 'gas_valve' no puede convertirse en "gas instalado" silencioso), y la
escritura jamás cruza tenants (mismo eje que test_fleet_admin).
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine
from takab_api.routers.fleet import router as fleet_router
from takab_api.routers.sites import router as sites_router

# Prefijo 65: no colisiona con seeds (1/2/3/9/a/b/c), async (7), B1 (8) ni fleet_admin (6*).
T_A = "65111111-1111-1111-1111-111111111111"
T_B = "65222222-2222-2222-2222-222222222222"
S_A = "65a00000-0000-0000-0000-0000000000a1"
S_B = "65b00000-0000-0000-0000-0000000000b1"
G_B = "65d00000-0000-0000-0000-0000000000d1"

_GEOM = "ST_SetSRID(ST_MakePoint(-98.20,19.04),4326)::geography"
_TENANTS = (T_A, T_B)
_CLEANUP = (
    text("DELETE FROM gateways WHERE tenant_id = ANY(:t)"),
    text("DELETE FROM sites WHERE tenant_id = ANY(:t)"),
    text("TRUNCATE audit_log"),
    text("DELETE FROM tenants WHERE tenant_id = ANY(:t)"),
)

ALL_TRUE = {
    "siren": True,
    "strobe": True,
    "gas_valve": True,
    "elevator": True,
    "door_retainer": True,
}


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    from takab_api.auth import deps

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
    await _cleanup()
    engine = get_engine()
    async with engine.begin() as conn:
        for tid, code in ((T_A, "EQ_A"), (T_B, "EQ_B")):
            await conn.execute(
                text(
                    "INSERT INTO tenants (tenant_id, code, name, visibility) "
                    "VALUES (:id, :code, 'T-2.31', 'private')"
                ),
                {"id": tid, "code": code},
            )
        for sid, tid, code in ((S_A, T_A, "EQSA"), (S_B, T_B, "EQSB")):
            await conn.execute(
                text(
                    "INSERT INTO sites (site_id, tenant_id, code, name, geom) "
                    f"VALUES (:sid, :tid, :code, 'Sitio', {_GEOM})"
                ),
                {"sid": sid, "tid": tid, "code": code},
            )
        await conn.execute(
            text(
                "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial) "
                "VALUES (:g, :t, :s, 'SN-EQ-B-1')"
            ),
            {"g": G_B, "t": T_B, "s": S_B},
        )
    yield
    await _cleanup()
    await engine.dispose()
    get_engine.cache_clear()


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(sites_router)
    app.include_router(fleet_router)
    return app


def _tok(role: str = "tenant_admin", tenant: str = T_A) -> dict[str, str]:
    return au.bearer(au.make_token(role, tenant=tenant, site_scope="*"))


async def _post(path: str, body: dict, token: dict[str, str]):
    async with au.client_for(_app()) as c:
        return await c.post(path, json=body, headers=token)


async def _put(path: str, body: dict, token: dict[str, str]):
    async with au.client_for(_app()) as c:
        return await c.put(path, json=body, headers=token)


async def _get(path: str, token: dict[str, str]):
    async with au.client_for(_app()) as c:
        return await c.get(path, headers=token)


async def test_gateway_equipment_defaults_all_true(seed: None) -> None:
    """Sin declarar equipamiento, TODO instalado: la flota existente no cambia."""
    resp = await _post("/fleet/gateways", {"site_id": S_A, "serial": "SN-EQ-1"}, _tok())
    assert resp.status_code == 201, resp.text
    assert resp.json()["equipment"] == ALL_TRUE


async def test_gateway_equipment_roundtrip_create_list_update(seed: None) -> None:
    """Alta sin gas/ascensor → persiste → se lista → PUT lo cambia (optimista)."""
    partial = ALL_TRUE | {"gas_valve": False, "elevator": False}
    created = await _post(
        "/fleet/gateways",
        {"site_id": S_A, "serial": "SN-EQ-2", "equipment": partial},
        _tok(),
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["equipment"] == partial

    listing = (await _get("/fleet/gateways", _tok())).json()
    mine = next(g for g in listing if g["gateway_id"] == body["gateway_id"])
    assert mine["equipment"] == partial

    updated = await _put(
        f"/fleet/gateways/{body['gateway_id']}",
        {
            "site_id": S_A,
            "serial": "SN-EQ-2",
            "equipment": ALL_TRUE | {"door_retainer": False},
            "base_row_version": body["row_version"],
        },
        _tok(),
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["equipment"]["door_retainer"] is False
    assert updated.json()["equipment"]["gas_valve"] is True


async def test_gateway_equipment_partial_body_fills_with_true(seed: None) -> None:
    """Un objeto parcial completa con true: solo se declara lo que FALTA."""
    resp = await _post(
        "/fleet/gateways",
        {"site_id": S_A, "serial": "SN-EQ-3", "equipment": {"gas_valve": False}},
        _tok(),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["equipment"] == ALL_TRUE | {"gas_valve": False}


async def test_gateway_equipment_unknown_key_is_422(seed: None) -> None:
    """Un typo no puede volverse "instalado" silencioso: clave desconocida ⇒ 422."""
    resp = await _post(
        "/fleet/gateways",
        {"site_id": S_A, "serial": "SN-EQ-4", "equipment": {"gas_valv": False}},
        _tok(),
    )
    assert resp.status_code == 422, resp.text


async def test_gateway_equipment_cross_tenant_update_is_404(seed: None) -> None:
    """El gabinete de B no existe para el token de A (RLS): editar su equipamiento tampoco."""
    resp = await _put(
        f"/fleet/gateways/{G_B}",
        {"site_id": S_B, "serial": "SN-EQ-B-1", "equipment": ALL_TRUE},
        _tok(tenant=T_A),
    )
    assert resp.status_code == 404, resp.text
