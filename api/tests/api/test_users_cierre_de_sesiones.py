"""T-8.02 · D-38 — deshabilitar una cuenta CIERRA sus sesiones.

Con D-38 un brigadista o un inspector no vuelve a teclear su contraseña en 30 días
(el ocupante, en 90). Eso convierte al refresh token en una llave de un mes: si se
pierde el teléfono, la baja reversible (``PATCH {"enabled": false}``) tiene que
matar también las sesiones que ya están abiertas, no solo impedir las nuevas. De
ahí el ``AdminUserGlobalSignOut``.

**Orden: primero se cierran las sesiones y DESPUÉS se deshabilita.** Al revés, un
fallo del cierre dejaría la cuenta deshabilitada con las sesiones vivas, y el
reintento del operador sería un no-op: el router solo llama al directorio cuando
``enabled`` CAMBIA, y ya estaría en ``false``. El hueco quedaría abierto y en
silencio. Con este orden, un fallo del cierre no ha cambiado nada todavía: la API
devuelve el error, no escribe bitácora (la transacción se revierte) y el reintento
vuelve a hacer las dos cosas.

**Lo que esto NO cierra, dicho aquí para que nadie lo lea como hecho:** el ID token
ya emitido lo verifica la API localmente (firma + ``exp``); el cierre global de
Cognito no lo alcanza. Vive hasta su ``exp`` (``id_token_validity = 60`` min).
"""

from __future__ import annotations

import logging
import os

import pytest
from fastapi import FastAPI
from sqlalchemy import text

import auth_utils as au
from takab_api.auth import deps
from takab_api.db.engine import get_engine
from takab_api.main import create_app
from takab_api.routers.users import get_user_directory
from takab_api.routers.users import router as users_router
from takab_api.users import CognitoUserDirectory, SimulatedUserDirectory, UserRecord
from takab_api.users.directory import DirectoryError

ADMIN_SUB = "aaaa1111-1111-1111-1111-111111111111"


def _user(username: str, *, tenant: str = au.DB_TENANT_PRIV, enabled: bool = True) -> UserRecord:
    return UserRecord(
        username=username,
        email=f"{username}@takab.test",
        tenant_id=tenant,
        role="brigadista",
        site_scope="*",
        zone_id="",
        surface="mobile",
        enabled=enabled,
        status="CONFIRMED",
    )


# --- Cognito real (cliente doble) -----------------------------------------------


class _FakeCognito:
    """Doble del cliente boto3: registra el ORDEN de las llamadas."""

    def __init__(self, *, fail_on: str | None = None) -> None:
        self.calls: list[str] = []
        self._fail_on = fail_on

    def _rec(self, op: str) -> dict:
        self.calls.append(op)
        if op == self._fail_on:
            from botocore.exceptions import ClientError

            raise ClientError({"Error": {"Code": "InternalErrorException"}}, op)
        return {}

    def admin_user_global_sign_out(self, **kw):
        return self._rec("admin_user_global_sign_out")

    def admin_disable_user(self, **kw):
        return self._rec("admin_disable_user")

    def admin_enable_user(self, **kw):
        return self._rec("admin_enable_user")

    def admin_get_user(self, **kw):
        self.calls.append("admin_get_user")
        return {
            "Username": kw["Username"],
            "UserAttributes": [{"Name": "custom:role", "Value": "brigadista"}],
            "Enabled": "admin_disable_user" not in self.calls,
            "UserStatus": "CONFIRMED",
        }


def _cognito(fake: _FakeCognito) -> CognitoUserDirectory:
    return CognitoUserDirectory(user_pool_id="p", region="us-east-2", client=fake)


def test_deshabilitar_cierra_las_sesiones_ANTES_de_deshabilitar() -> None:
    fake = _FakeCognito()
    record = _cognito(fake).set_enabled("u", False)
    ops = [op for op in fake.calls if op != "admin_get_user"]
    assert ops == ["admin_user_global_sign_out", "admin_disable_user"]
    assert record.enabled is False


def test_habilitar_NO_cierra_sesiones() -> None:
    fake = _FakeCognito()
    _cognito(fake).set_enabled("u", True)
    assert "admin_user_global_sign_out" not in fake.calls
    assert "admin_enable_user" in fake.calls


def test_si_el_cierre_falla_NO_se_deshabilita_y_el_error_sube(caplog) -> None:
    """Nada a medias: la cuenta sigue exactamente como estaba y el operador lo sabe."""
    fake = _FakeCognito(fail_on="admin_user_global_sign_out")
    with caplog.at_level(logging.ERROR, logger="takab_api.users"):
        with pytest.raises(DirectoryError):
            _cognito(fake).set_enabled("u", False)
    assert "admin_disable_user" not in fake.calls
    assert any("sesiones" in r.message for r in caplog.records)


def test_si_falla_el_disable_tras_el_cierre_el_error_sube_y_se_registra(caplog) -> None:
    """Sesiones ya cerradas pero la cuenta sigue habilitada: benigno (la persona
    solo tiene que volver a entrar), pero no puede pasar en silencio."""
    fake = _FakeCognito(fail_on="admin_disable_user")
    with caplog.at_level(logging.WARNING, logger="takab_api.users"):
        with pytest.raises(DirectoryError):
            _cognito(fake).set_enabled("u", False)
    assert fake.calls[0] == "admin_user_global_sign_out"
    assert any("habilitada" in r.message for r in caplog.records)


# --- el directorio simulado -----------------------------------------------------


def test_simulado_registra_el_cierre_y_GRITA(caplog) -> None:
    directory = SimulatedUserDirectory([_user("u-1")])
    with caplog.at_level(logging.WARNING, logger="takab_api.users"):
        directory.set_enabled("u-1", False)
    assert directory.signed_out == ["u-1"]
    assert any("cierre de sesiones SIMULADO" in r.message for r in caplog.records)


def test_simulado_habilitar_no_cierra_sesiones() -> None:
    directory = SimulatedUserDirectory([_user("u-1", enabled=False)])
    directory.set_enabled("u-1", True)
    assert directory.signed_out == []


class _CierreRoto(SimulatedUserDirectory):
    """Simulado cuyo cierre de sesiones falla (p. ej. IAM sin el permiso)."""

    def _global_sign_out(self, username: str) -> None:
        raise DirectoryError(
            "admin_user_global_sign_out: AccessDeniedException", code="AccessDeniedException"
        )


def test_simulado_con_cierre_roto_no_deshabilita() -> None:
    directory = _CierreRoto([_user("u-1")])
    with pytest.raises(DirectoryError):
        directory.set_enabled("u-1", False)
    assert directory.get_user("u-1").enabled is True


# --- por HTTP: el operador se entera --------------------------------------------


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


def _app(directory: SimulatedUserDirectory) -> FastAPI:
    application = create_app()
    application.include_router(users_router)
    application.dependency_overrides[get_user_directory] = lambda: directory
    return application


def _token() -> dict[str, str]:
    return au.bearer(
        au.make_token("tenant_admin", tenant=au.DB_TENANT_PRIV, site_scope="*", user_id=ADMIN_SUB)
    )


async def _audits(obj: str) -> list[dict]:
    async with get_engine().begin() as conn:
        rows = (
            await conn.execute(
                text("SELECT verb, meta FROM audit_log WHERE object = :o"), {"o": obj}
            )
        ).all()
    return [dict(r._mapping) for r in rows]


async def test_baja_por_la_consola_cierra_las_sesiones(base_data) -> None:
    directory = SimulatedUserDirectory([_user("u-baja")])
    async with au.client_for(_app(directory)) as c:
        resp = await c.patch("/users/u-baja", headers=_token(), json={"enabled": False})
    assert resp.status_code == 200, resp.text
    assert directory.signed_out == ["u-baja"]


async def test_baja_con_cierre_roto_es_error_visible_y_la_cuenta_sigue_igual(base_data) -> None:
    directory = _CierreRoto([_user("u-roto")])
    async with au.client_for(_app(directory)) as c:
        resp = await c.patch("/users/u-roto", headers=_token(), json={"enabled": False})
    # AccessDenied ⇒ 502 «la API no tiene permiso sobre el pool»: fallo NUESTRO.
    assert resp.status_code == 502, resp.text
    assert directory.get_user("u-roto").enabled is True
    # Sin cambio no hay fila que diga que lo hubo.
    assert not [a for a in await _audits("user:u-roto") if a["verb"] == "user_update"]
