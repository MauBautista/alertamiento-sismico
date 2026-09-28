"""T-9.20 · D-42 — qué roles se pueden ASIGNAR tras bajar de 10 a 7.

- Un rol viejo (``soc_operator``/``security_guard``/``building_admin``) ya no se
  asigna: 422. Los alias solo existen para que los TOKENS viejos sigan entrando
  durante la ventana; dar de alta a alguien nuevo con uno sería alargarla a mano.
- ``GET /users/assignable-roles`` publica la lista con su etiqueta, para que la
  web no la escriba a mano (``UsersCard.ROLES`` era un espejo sin guarda). Un rol
  de cliente no ve los internos: no puede otorgarlos (``PLATFORM_ROLES``).
"""

from __future__ import annotations

import os

import pytest
from fastapi import FastAPI

import auth_utils as au
from takab_api.auth import deps
from takab_api.auth.roles import ALIAS_HEREDADOS, CANONICAL_ROLES, ETIQUETA
from takab_api.db.engine import get_engine
from takab_api.main import create_app
from takab_api.routers.users import get_user_directory
from takab_api.routers.users import router as users_router
from takab_api.schemas.users import ASSIGNABLE_ROLES, PLATFORM_ROLES
from takab_api.users import SimulatedUserDirectory

ADMIN_SUB = "aaaa1111-1111-1111-1111-111111111111"


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


@pytest.fixture
def app() -> FastAPI:
    application = create_app()
    application.include_router(users_router)
    application.dependency_overrides[get_user_directory] = lambda: SimulatedUserDirectory([])
    return application


def _token(role: str) -> dict[str, str]:
    return au.bearer(
        au.make_token(role, tenant=au.DB_TENANT_PRIV, site_scope="*", user_id=ADMIN_SUB)
    )


def test_asignables_son_los_canonicos_menos_occupant() -> None:
    assert set(ASSIGNABLE_ROLES) == set(CANONICAL_ROLES) - {"occupant"}
    assert not set(ASSIGNABLE_ROLES) & set(ALIAS_HEREDADOS)


@pytest.mark.parametrize("viejo", sorted(ALIAS_HEREDADOS))
async def test_crear_con_rol_viejo_es_422(app, base_data, viejo: str) -> None:
    async with au.client_for(app) as c:
        resp = await c.post(
            "/users",
            headers=_token("tenant_admin"),
            json={"email": f"{viejo}@takab.test", "role": viejo},
        )
    assert resp.status_code == 422, resp.text


@pytest.mark.parametrize("viejo", sorted(ALIAS_HEREDADOS))
async def test_cambiar_a_rol_viejo_es_422(app, base_data, viejo: str) -> None:
    async with au.client_for(app) as c:
        resp = await c.patch("/users/u-x", headers=_token("tenant_admin"), json={"role": viejo})
    assert resp.status_code == 422, resp.text


async def test_assignable_roles_del_administrador_sin_internos(app, base_data) -> None:
    async with au.client_for(app) as c:
        resp = await c.get("/users/assignable-roles", headers=_token("tenant_admin"))
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    roles = [i["role"] for i in items]
    assert roles == [r for r in ASSIGNABLE_ROLES if r not in PLATFORM_ROLES]
    assert all(i["label"] == ETIQUETA[i["role"]] for i in items)
    assert "tenant_admin" in roles and "brigadista" in roles


async def test_assignable_roles_del_superadmin_con_internos(app, base_data) -> None:
    async with au.client_for(app) as c:
        resp = await c.get("/users/assignable-roles", headers=_token("takab_superadmin"))
    assert resp.status_code == 200, resp.text
    assert [i["role"] for i in resp.json()["items"]] == list(ASSIGNABLE_ROLES)


async def test_assignable_roles_exige_manage_users(app, base_data) -> None:
    async with au.client_for(app) as c:
        resp = await c.get("/users/assignable-roles", headers=_token("inspector"))
    assert resp.status_code == 403
