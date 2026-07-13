"""POST/GET /drills (T-1.60): simulacro institucional — jamás toca incidents.

Reutiliza el arnés del command service (fleet con gateway comandable, publisher
fake, claves HMAC inline): el drill emite comandos firmados REALES por sitio.
"""

# ruff: noqa: F811  (fixtures de pytest importadas por nombre)
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine
from takab_api.main import create_app
from takab_api.routers.commands import get_publisher
from takab_api.routers.commands import router as commands_router
from takab_api.routers.drills import router as drills_router

# Arnés compartido con el router de comandos (fixtures gateway/publisher).
from tests.api.test_commands_router import (  # noqa: F401  (fixtures por nombre)
    KEY,
    THING,
    _FakePublisher,
    gateway,
    publisher,
)


@pytest.fixture
def app(publisher: _FakePublisher) -> FastAPI:
    application = create_app()
    application.include_router(drills_router)
    application.include_router(commands_router)
    application.dependency_overrides[get_publisher] = lambda: publisher
    return application


@pytest.fixture(autouse=True)
def _hmac_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TAKAB_API_COMMAND_HMAC_SECRET_PREFIX", raising=False)
    monkeypatch.setenv("TAKAB_API_COMMAND_HMAC_KEYS_JSON", json.dumps({THING: KEY}))


def _token(role: str = "tenant_admin", tenant: str = au.DB_TENANT_PRIV) -> dict[str, str]:
    return au.bearer(au.make_token(role, tenant=tenant, site_scope="*"))


async def _count(sql: str) -> int:
    engine = get_engine()
    async with engine.begin() as conn:
        return (await conn.execute(text(sql))).scalar_one()


async def test_post_drills_emite_drill_start_firmado_por_sitio(client, gateway, publisher):
    r = await client.post(
        "/drills",
        json={"site_ids": [au.DB_SITE_PRIV], "duration_s": 120, "note": "simulacro trimestral"},
        headers=_token(),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["active"] is True and body["duration_s"] == 120
    assert len(body["sites"]) == 1
    assert body["sites"][0]["command_id"] is not None
    # El envelope firmado salió con la duración DENTRO del payload canónico.
    assert len(publisher.published) == 1
    envelope = publisher.published[0][1]
    assert envelope["payload"]["action"] == "drill_start"
    assert envelope["payload"]["duration_s"] == 120
    assert envelope["payload"]["event_id"] == f"DRILL-{body['drill_id']}"


async def test_un_drill_jamas_crea_incidentes(client, gateway, publisher):
    before = await _count("SELECT count(*) FROM incidents")
    r = await client.post("/drills", json={"duration_s": 60}, headers=_token())
    assert r.status_code == 201
    assert await _count("SELECT count(*) FROM incidents") == before
    assert await _count("SELECT count(*) FROM incident_actions") == 0
    assert await _count("SELECT count(*) FROM dictamens") == 0


@pytest.mark.parametrize("role", ["soc_operator", "gov_operator", "inspector", "building_admin"])
async def test_roles_sin_drill_start_403(client, gateway, role):
    r = await client.post("/drills", json={"duration_s": 60}, headers=_token(role))
    assert r.status_code == 403


async def test_tenant_sin_gabinetes_comandables_409(client, base_data):
    # El tenant B solo tiene sitios SIN gateway comandable (base_data).
    r = await client.post(
        "/drills", json={"duration_s": 60}, headers=_token(tenant=au.DB_TENANT_PRIV2)
    )
    assert r.status_code == 409


async def test_registro_visible_para_gov_y_active_para_consola(client, gateway, publisher):
    created = await client.post(
        "/drills", json={"site_ids": [au.DB_SITE_PRIV], "duration_s": 300}, headers=_token()
    )
    drill_id = created.json()["drill_id"]

    # gov_operator LEE el registro de su ámbito (RLS gov_shared: tenant privado
    # ajeno ⇒ lista vacía, jamás 403 — el endpoint es de consola).
    gov = await client.get("/drills", headers=_token("gov_operator", tenant=au.DB_TENANT_GOV))
    assert gov.status_code == 200

    # El propio tenant ve su drill con el acuse por sitio (derivado de commands).
    mine = await client.get("/drills", headers=_token())
    items = mine.json()["items"]
    assert any(d["drill_id"] == drill_id for d in items)
    row = next(d for d in items if d["drill_id"] == drill_id)
    assert row["sites"][0]["command_status"] == "pending"  # aún sin ack del edge

    # El banner de la consola: cualquier rol del SOC ve el drill activo.
    active = await client.get("/drills/active", headers=_token("soc_operator"))
    assert active.status_code == 200
    assert active.json()["drill"]["drill_id"] == drill_id


async def test_stop_marca_fin_y_publica_drill_stop(client, gateway, publisher):
    created = await client.post(
        "/drills", json={"site_ids": [au.DB_SITE_PRIV], "duration_s": 300}, headers=_token()
    )
    drill_id = created.json()["drill_id"]
    publisher.published.clear()

    stopped = await client.post(f"/drills/{drill_id}/stop", headers=_token())
    assert stopped.status_code == 200, stopped.text
    body = stopped.json()
    assert body["active"] is False and body["stopped_at"] is not None
    assert len(publisher.published) == 1
    assert publisher.published[0][1]["payload"]["action"] == "drill_stop"

    # Idempotente: un segundo stop devuelve el drill sin re-publicar.
    again = await client.post(f"/drills/{drill_id}/stop", headers=_token())
    assert again.status_code == 200
    assert len(publisher.published) == 1

    # Y el banner se apaga.
    active = await client.get("/drills/active", headers=_token("soc_operator"))
    assert active.json()["drill"] is None
