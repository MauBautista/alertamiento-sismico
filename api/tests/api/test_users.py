"""Gestión de usuarios (T-2.54): la superficie que reparte ACCESO A DATOS.

``custom:tenant_id`` y ``custom:role`` son los dos claims donde se ancla la RLS
(``auth/claims.py``, regla de oro 5). Quien los escribe decide qué ve una persona,
así que esta suite vigila cuatro cosas por encima del CRUD:

1. **Cruce de tenant**: un ``tenant_admin`` que toque un usuario ajeno recibe 404.
2. **Escalada**: un ``tenant_admin`` no otorga roles de plataforma.
3. **Auditoría**: toda escritura deja fila en ``audit_log``, con el diff.
4. **Credenciales**: no entran ni salen por ningún campo.

El directorio se inyecta (``get_user_directory``): estos tests jamás tocan AWS.
"""

from __future__ import annotations

import logging
import os
import uuid

import pytest
from fastapi import FastAPI
from sqlalchemy import text

import auth_utils as au
from takab_api.auth import deps
from takab_api.db.engine import get_engine
from takab_api.main import create_app
from takab_api.routers.users import get_user_directory
from takab_api.routers.users import router as users_router
from takab_api.settings import Settings
from takab_api.users import (
    ATTR_SITE_SCOPE,
    CognitoUserDirectory,
    SimulatedUserDirectory,
    UserRecord,
    build_user_directory,
)

SITE_PRIV = au.DB_SITE_PRIV
SITE_PRIV2 = au.DB_SITE_PRIV2


def _user(
    username: str,
    *,
    tenant: str,
    email: str | None = None,
    role: str = "soc_operator",
    site_scope: str = "*",
    surface: str = "web",
    enabled: bool = True,
) -> UserRecord:
    return UserRecord(
        username=username,
        email=email or f"{username}@takab.test",
        tenant_id=tenant,
        role=role,
        site_scope=site_scope,
        zone_id="",
        surface=surface,
        enabled=enabled,
        status="CONFIRMED",
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


@pytest.fixture
def directory() -> SimulatedUserDirectory:
    return SimulatedUserDirectory(
        [
            _user("u-own", tenant=au.DB_TENANT_PRIV, email="propio@takab.test"),
            _user("u-other", tenant=au.DB_TENANT_PRIV2, email="ajeno@takab.test"),
        ]
    )


@pytest.fixture
def app(directory: SimulatedUserDirectory) -> FastAPI:
    application = create_app()
    application.include_router(users_router)
    application.dependency_overrides[get_user_directory] = lambda: directory
    return application


@pytest.fixture
async def sites(base_data) -> None:
    """`base_data` ya siembra un sitio por tenant; aquí solo se declara la dependencia."""
    return None


def _token(role: str = "tenant_admin", tenant: str = au.DB_TENANT_PRIV, sub: str = "admin-1"):
    return au.bearer(au.make_token(role, tenant=tenant, site_scope="*", user_id=sub))


async def _audit(verb: str) -> list[dict]:
    async with get_engine().begin() as conn:
        rows = (
            await conn.execute(
                text("SELECT tenant_id::text, actor, object, meta FROM audit_log WHERE verb = :v"),
                {"v": verb},
            )
        ).all()
    return [dict(r._mapping) for r in rows]


# --- gate de la acción --------------------------------------------------------


@pytest.mark.parametrize(
    "role", ["takab_support", "soc_operator", "gov_operator", "inspector", "building_admin"]
)
async def test_roles_without_manage_users_are_403(app, sites, role: str) -> None:
    """`takab_support` incluido: soporte lee la plataforma, no reparte identidades."""
    async with au.client_for(app) as c:
        resp = await c.get("/users", headers=_token(role))
    assert resp.status_code == 403


async def test_mobile_surface_cannot_manage_users(app, sites) -> None:
    token = au.bearer(
        au.make_token("tenant_admin", tenant=au.DB_TENANT_PRIV, site_scope="*", surface="mobile")
    )
    async with au.client_for(app) as c:
        resp = await c.get("/users", headers=token)
    assert resp.status_code == 403


async def test_unauthenticated_is_401(app, sites) -> None:
    async with au.client_for(app) as c:
        resp = await c.get("/users")
    assert resp.status_code == 401


# --- lectura acotada al tenant ------------------------------------------------


async def test_tenant_admin_only_sees_own_tenant(app, sites) -> None:
    async with au.client_for(app) as c:
        resp = await c.get("/users", headers=_token())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [u["username"] for u in body["items"]] == ["u-own"]
    assert body["backend"] == "simulated"


async def test_superadmin_sees_every_tenant(app, sites) -> None:
    async with au.client_for(app) as c:
        resp = await c.get("/users", headers=_token("takab_superadmin"))
    assert {u["username"] for u in resp.json()["items"]} == {"u-own", "u-other"}


async def test_user_payload_carries_no_credential_field(app, sites) -> None:
    async with au.client_for(app) as c:
        resp = await c.get("/users", headers=_token())
    forbidden = ("password", "secret", "token", "temporary", "credential")
    for item in resp.json()["items"]:
        for key in item:
            assert not any(word in key.lower() for word in forbidden), key


# --- alta ---------------------------------------------------------------------


async def test_tenant_admin_creates_user_in_own_tenant_and_audits(app, sites, directory) -> None:
    async with au.client_for(app) as c:
        resp = await c.post(
            "/users",
            headers=_token(),
            json={"email": "Nuevo@Takab.Test", "role": "soc_operator", "site_scope": "*"},
        )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["email"] == "nuevo@takab.test"  # normalizado
    assert body["tenant_id"] == au.DB_TENANT_PRIV
    # El cuerpo es EXACTAMENTE el contrato de UserOut: no hay hueco por donde se
    # cuele una credencial. (`status` puede valer FORCE_CHANGE_PASSWORD — es el
    # estado de la cuenta en Cognito, no una clave.)
    assert set(body) == {
        "username",
        "email",
        "tenant_id",
        "role",
        "site_scope",
        "zone_id",
        "surface",
        "enabled",
        "status",
        "created_at",
        "updated_at",
    }

    rows = await _audit("user_create")
    assert len(rows) == 1
    assert rows[0]["tenant_id"] == au.DB_TENANT_PRIV
    assert rows[0]["actor"] == "user:admin-1"
    assert rows[0]["meta"]["role"] == "soc_operator"


async def test_tenant_admin_cannot_create_in_another_tenant(app, sites) -> None:
    async with au.client_for(app) as c:
        resp = await c.post(
            "/users",
            headers=_token(),
            json={
                "email": "invasor@takab.test",
                "role": "soc_operator",
                "tenant_id": au.DB_TENANT_PRIV2,
            },
        )
    assert resp.status_code == 403
    assert await _audit("user_create") == []


@pytest.mark.parametrize("role", ["takab_superadmin", "takab_support"])
async def test_tenant_admin_cannot_grant_platform_roles(app, sites, role: str) -> None:
    """Escalada de privilegios: sin este corte, un tenant_admin se fabrica un
    superadmin y sale de su propio aislamiento en un solo POST."""
    async with au.client_for(app) as c:
        resp = await c.post(
            "/users", headers=_token(), json={"email": "escalada@takab.test", "role": role}
        )
    assert resp.status_code == 403
    assert await _audit("user_create") == []


async def test_superadmin_must_name_the_tenant(app, sites) -> None:
    """Su RLS no lo detendría: el tenant destino tiene que ser explícito."""
    async with au.client_for(app) as c:
        resp = await c.post(
            "/users",
            headers=_token("takab_superadmin"),
            json={"email": "sin-tenant@takab.test", "role": "soc_operator"},
        )
    assert resp.status_code == 400


async def test_occupant_role_is_not_assignable_here(app, sites) -> None:
    """El occupant vive en OTRO pool (ancla pool→rol): crearlo aquí produciría una
    cuenta que se autentica y recibe 401. Se enrola con un código (T-2.53)."""
    async with au.client_for(app) as c:
        resp = await c.post(
            "/users", headers=_token(), json={"email": "vecino@takab.test", "role": "occupant"}
        )
    assert resp.status_code == 422


async def test_site_scope_must_name_sites_of_this_tenant(app, sites) -> None:
    """Un site_id de otro cliente en el alcance dejaría al usuario viendo cero
    estaciones, sin que nadie supiera por qué."""
    async with au.client_for(app) as c:
        alien = await c.post(
            "/users",
            headers=_token(),
            json={"email": "acotado@takab.test", "role": "soc_operator", "site_scope": SITE_PRIV2},
        )
        ghost = await c.post(
            "/users",
            headers=_token(),
            json={
                "email": "acotado2@takab.test",
                "role": "soc_operator",
                "site_scope": str(uuid.uuid4()),
            },
        )
        ok = await c.post(
            "/users",
            headers=_token(),
            json={"email": "acotado3@takab.test", "role": "soc_operator", "site_scope": SITE_PRIV},
        )
    assert alien.status_code == 400
    assert ghost.status_code == 400
    assert ok.status_code == 201, ok.text
    assert ok.json()["site_scope"] == SITE_PRIV


async def test_site_scope_is_normalised(app, sites) -> None:
    async with au.client_for(app) as c:
        resp = await c.post(
            "/users",
            headers=_token(),
            json={
                "email": "dup@takab.test",
                "role": "soc_operator",
                "site_scope": f" {SITE_PRIV} , {SITE_PRIV} ",
            },
        )
    assert resp.status_code == 201, resp.text
    assert resp.json()["site_scope"] == SITE_PRIV


async def test_site_scope_rejects_garbage(app, sites) -> None:
    async with au.client_for(app) as c:
        resp = await c.post(
            "/users",
            headers=_token(),
            json={"email": "malo@takab.test", "role": "soc_operator", "site_scope": "no-es-uuid"},
        )
    assert resp.status_code == 422


async def test_duplicate_email_is_409(app, sites) -> None:
    async with au.client_for(app) as c:
        resp = await c.post(
            "/users", headers=_token(), json={"email": "propio@takab.test", "role": "soc_operator"}
        )
    assert resp.status_code == 409


# --- edición ------------------------------------------------------------------


async def test_patch_writes_site_scope_and_audits_the_diff(app, sites, directory) -> None:
    """Este PATCH es el que desbloquea la Fase B de T-2.45: alguien tiene que poder
    escribir ``custom:site_scope``."""
    async with au.client_for(app) as c:
        resp = await c.patch(
            "/users/u-own", headers=_token(), json={"site_scope": SITE_PRIV, "surface": "both"}
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["site_scope"] == SITE_PRIV
    assert directory.get_user("u-own").site_scope == SITE_PRIV

    rows = await _audit("user_update")
    assert len(rows) == 1
    meta = rows[0]["meta"]
    assert set(meta["changed"]) == {"site_scope", "surface"}
    assert meta["diff"]["site_scope"] == {"from": "*", "to": SITE_PRIV}


async def test_patch_role_moves_the_group_too(app, sites, directory) -> None:
    async with au.client_for(app) as c:
        resp = await c.patch("/users/u-own", headers=_token(), json={"role": "inspector"})
    assert resp.status_code == 200, resp.text
    assert directory.get_user("u-own").role == "inspector"


async def test_patch_enabled_false_is_the_reversible_baja(app, sites, directory) -> None:
    async with au.client_for(app) as c:
        resp = await c.patch("/users/u-own", headers=_token(), json={"enabled": False})
    assert resp.status_code == 200, resp.text
    assert resp.json()["enabled"] is False
    assert (await _audit("user_update"))[0]["meta"]["changed"] == ["enabled"]


async def test_tenant_admin_patching_foreign_user_is_404(app, sites, directory) -> None:
    """404, no 403: un 403 confirmaría que la cuenta existe."""
    async with au.client_for(app) as c:
        resp = await c.patch("/users/u-other", headers=_token(), json={"role": "inspector"})
    assert resp.status_code == 404
    assert directory.get_user("u-other").role == "soc_operator"
    assert await _audit("user_update") == []


async def test_tenant_admin_cannot_escalate_an_existing_user(app, sites, directory) -> None:
    async with au.client_for(app) as c:
        resp = await c.patch("/users/u-own", headers=_token(), json={"role": "takab_superadmin"})
    assert resp.status_code == 403
    assert directory.get_user("u-own").role == "soc_operator"


async def test_patch_cannot_move_a_user_between_tenants(app, sites) -> None:
    """``tenant_id`` no es editable: mover a alguien re-tenantiza su auditoría."""
    async with au.client_for(app) as c:
        resp = await c.patch(
            "/users/u-own", headers=_token(), json={"tenant_id": au.DB_TENANT_PRIV2}
        )
    assert resp.status_code == 422


async def test_patch_empty_body_is_422(app, sites) -> None:
    async with au.client_for(app) as c:
        resp = await c.patch("/users/u-own", headers=_token(), json={})
    assert resp.status_code == 422


async def test_patch_unknown_user_is_404(app, sites) -> None:
    async with au.client_for(app) as c:
        resp = await c.patch("/users/nadie", headers=_token(), json={"surface": "web"})
    assert resp.status_code == 404


# --- reset / invitación / baja ------------------------------------------------


async def test_reset_password_never_returns_a_credential(app, sites) -> None:
    async with au.client_for(app) as c:
        resp = await c.post("/users/u-own/reset-password", headers=_token())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["action"] == "password_reset"
    assert set(body) == {"username", "action", "detail"}
    assert len(await _audit("user_password_reset")) == 1


async def test_resend_invitation_is_audited(app, sites) -> None:
    async with au.client_for(app) as c:
        resp = await c.post("/users/u-own/resend-invitation", headers=_token())
    assert resp.status_code == 200, resp.text
    assert len(await _audit("user_invitation_resent")) == 1


@pytest.mark.parametrize("path", ["reset-password", "resend-invitation"])
async def test_actions_on_foreign_user_are_404(app, sites, path: str) -> None:
    async with au.client_for(app) as c:
        resp = await c.post(f"/users/u-other/{path}", headers=_token())
    assert resp.status_code == 404


async def test_delete_user_is_audited(app, sites, directory) -> None:
    async with au.client_for(app) as c:
        resp = await c.delete("/users/u-own", headers=_token())
    assert resp.status_code == 204
    assert directory.get_user("u-own") is None
    assert len(await _audit("user_delete")) == 1


async def test_delete_foreign_user_is_404(app, sites, directory) -> None:
    async with au.client_for(app) as c:
        resp = await c.delete("/users/u-other", headers=_token())
    assert resp.status_code == 404
    assert directory.get_user("u-other") is not None


async def test_cannot_delete_yourself(app, sites, directory) -> None:
    """Quedarse sin ningún administrador es un modo de fallo, no una acción."""
    async with au.client_for(app) as c:
        resp = await c.delete("/users/u-own", headers=_token(sub="u-own"))
    assert resp.status_code == 409
    assert directory.get_user("u-own") is not None


# --- el proveedor: stand-in explícito que GRITA -------------------------------


def test_build_user_directory_without_pool_is_simulated_and_shouts(caplog) -> None:
    with caplog.at_level(logging.WARNING, logger="takab_api.users"):
        directory = build_user_directory(Settings(cognito_user_pool_id=""))
    assert isinstance(directory, SimulatedUserDirectory)
    assert directory.backend == "simulated"
    assert any("SIMULADO" in r.message for r in caplog.records)


def test_build_user_directory_with_pool_is_cognito() -> None:
    directory = build_user_directory(
        Settings(cognito_user_pool_id="us-east-2_abc123"), client=object()
    )
    assert isinstance(directory, CognitoUserDirectory)
    assert directory.backend == "cognito"


def test_simulated_writes_shout(caplog) -> None:
    directory = SimulatedUserDirectory()
    with caplog.at_level(logging.WARNING, logger="takab_api.users"):
        directory.create_user(
            email="a@b.test",
            tenant_id=au.DB_TENANT_PRIV,
            role="soc_operator",
            site_scope="*",
            zone_id="",
            surface="web",
        )
    assert any("SIMULADA" in r.message for r in caplog.records)


class _FakeCognito:
    """Doble del cliente boto3: registra las llamadas, no habla con AWS."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def _rec(self, op: str, **kw):
        self.calls.append((op, kw))
        return {}

    def admin_create_user(self, **kw):
        self._rec("admin_create_user", **kw)
        return {
            "User": {
                "Username": "cognito-uuid",
                "Attributes": kw.get("UserAttributes", []),
                "Enabled": True,
                "UserStatus": "FORCE_CHANGE_PASSWORD",
            }
        }

    def admin_add_user_to_group(self, **kw):
        return self._rec("admin_add_user_to_group", **kw)

    def admin_remove_user_from_group(self, **kw):
        return self._rec("admin_remove_user_from_group", **kw)

    def admin_update_user_attributes(self, **kw):
        return self._rec("admin_update_user_attributes", **kw)

    def admin_list_groups_for_user(self, **kw):
        self._rec("admin_list_groups_for_user", **kw)
        return {"Groups": [{"GroupName": "soc_operator"}, {"GroupName": "inspector"}]}

    def admin_get_user(self, **kw):
        self._rec("admin_get_user", **kw)
        return {
            "Username": kw["Username"],
            "UserAttributes": [
                {"Name": "email", "Value": "x@y.test"},
                {"Name": "custom:role", "Value": "inspector"},
            ],
            "Enabled": True,
            "UserStatus": "CONFIRMED",
        }


def test_cognito_create_never_sends_a_password_and_joins_the_group() -> None:
    """Sin grupo, ``Claims.from_verified`` rechaza el token: el alta produciría un
    usuario que se autentica y recibe 401 en cada request."""
    fake = _FakeCognito()
    directory = CognitoUserDirectory(user_pool_id="p", region="us-east-2", client=fake)
    directory.create_user(
        email="x@y.test",
        tenant_id=au.DB_TENANT_PRIV,
        role="inspector",
        site_scope="*",
        zone_id="",
        surface="web",
    )
    create = next(kw for op, kw in fake.calls if op == "admin_create_user")
    assert "TemporaryPassword" not in create
    assert create["DesiredDeliveryMediums"] == ["EMAIL"]
    joined = next(kw for op, kw in fake.calls if op == "admin_add_user_to_group")
    assert joined["GroupName"] == "inspector"


def test_cognito_role_change_adds_before_removing() -> None:
    """Entrar al grupo nuevo antes de salir del viejo deja una ventana con DOS
    grupos; al revés dejaría una con NINGUNO, y ahí nadie puede entrar."""
    fake = _FakeCognito()
    directory = CognitoUserDirectory(user_pool_id="p", region="us-east-2", client=fake)
    directory.update_user("u", attributes={ATTR_SITE_SCOPE: "*"}, role="inspector")
    ops = [op for op, _ in fake.calls]
    assert ops.index("admin_add_user_to_group") < ops.index("admin_remove_user_from_group")
    removed = [kw["GroupName"] for op, kw in fake.calls if op == "admin_remove_user_from_group"]
    assert removed == ["soc_operator"]
