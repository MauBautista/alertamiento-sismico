"""Fixtures de los tests de auth fase B (HTTP + DB async, sin Cognito real).

- ``_auth_env`` (autouse, sync): fija issuer/audience/JWKS inline + clave de firma
  dev + DSN async en el entorno y limpia los caches de auth/engine. Vale también
  para los tests sync de fase A (no les afecta: usan ``au.test_settings`` explícito).
- ``db_engine`` (async): dispone el engine async por test (pytest-asyncio usa un
  loop por función; reutilizar conexiones entre loops rompería). Los tests que
  tocan DB deben pedir este fixture (directa o transitivamente).
- ``base_tenants`` + ``make_incident``: siembra (super, bypass RLS) para ejercitar
  RLS por tenant y la vía de gobierno.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Awaitable, Callable

import pytest
from fastapi import FastAPI
from sqlalchemy import text

import auth_utils as au
from takab_api.auth import deps
from takab_api.db.engine import get_engine
from takab_api.main import create_app

_GEOM = "ST_SetSRID(ST_MakePoint(-99.13,19.43),4326)::geography"


@pytest.fixture(autouse=True)
def _auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Alinea el entorno con el keypair/JWKS de test y limpia caches."""
    monkeypatch.setenv("TAKAB_API_AUTH_ISSUER", au.ISSUER)
    monkeypatch.setenv("TAKAB_API_AUTH_AUDIENCE", au.AUDIENCE)
    monkeypatch.setenv("TAKAB_API_AUTH_JWKS_JSON", au.jwks_json())
    monkeypatch.setenv("TAKAB_API_AUTH_DEV_PRIVATE_KEY", au.dev_private_key_pem())
    dsn = os.environ.get("DATABASE_URL")
    if dsn:
        monkeypatch.setenv("TAKAB_API_DATABASE_URL", dsn)
    deps._reset_caches()
    get_engine.cache_clear()
    yield
    deps._reset_caches()


# Tablas que los tests HTTP commitean (no hay rollback tras el request). Son
# append-only: DELETE está prohibido por trigger, así que se limpian con TRUNCATE
# como superusuario (el trigger no dispara en TRUNCATE) para no contaminar los
# count(*) globales de la suite sync de ingesta (T-1.17).
_TRUNCATE_WRITTEN = text("TRUNCATE incidents, incident_actions, audit_log CASCADE")


@pytest.fixture
async def db_engine():
    """Engine async fresco en el loop del test; limpia lo commiteado y se dispone."""
    yield
    if get_engine.cache_info().currsize:
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.execute(_TRUNCATE_WRITTEN)
        await engine.dispose()
    get_engine.cache_clear()


@pytest.fixture
async def base_tenants(db_engine) -> None:
    """Siembra 3 tenants (A/B private, G gov_shared) + un sitio por cada uno."""
    engine = get_engine()
    async with engine.begin() as conn:
        for tid, code, vis in (
            (au.DB_TENANT_PRIV, "AUTHB_A", "private"),
            (au.DB_TENANT_PRIV2, "AUTHB_B", "private"),
            (au.DB_TENANT_GOV, "AUTHB_G", "gov_shared"),
        ):
            await conn.execute(
                text(
                    "INSERT INTO tenants (tenant_id, code, name, visibility) "
                    "VALUES (:id, :code, 'Auth test', :vis) ON CONFLICT (tenant_id) DO NOTHING"
                ),
                {"id": tid, "code": code, "vis": vis},
            )
        for sid, tid, code in (
            (au.DB_SITE_PRIV, au.DB_TENANT_PRIV, "SA"),
            (au.DB_SITE_PRIV2, au.DB_TENANT_PRIV2, "SB"),
            (au.DB_SITE_GOV, au.DB_TENANT_GOV, "SG"),
        ):
            await conn.execute(
                text(
                    "INSERT INTO sites (site_id, tenant_id, code, name, geom) "
                    f"VALUES (:sid, :tid, :code, 'Sitio', {_GEOM}) "
                    "ON CONFLICT (site_id) DO NOTHING"
                ),
                {"sid": sid, "tid": tid, "code": code},
            )


@pytest.fixture
def make_incident(base_tenants) -> Callable[[str, str], Awaitable[str]]:
    """Factoría async: crea un incidente ABIERTO nuevo y devuelve su id (str)."""

    async def _make(tenant_id: str, site_id: str) -> str:
        engine = get_engine()
        iid = str(uuid.uuid4())
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO incidents (incident_id, event_uuid, tenant_id, site_id, "
                    "opened_at, severity, trigger) "
                    "VALUES (:i, gen_random_uuid(), :t, :s, now(), 'warning', 'sasmex')"
                ),
                {"i": iid, "t": tenant_id, "s": site_id},
            )
        return iid

    return _make


@pytest.fixture
def app() -> FastAPI:
    """App construida con el entorno de test ya fijado por ``_auth_env``."""
    return create_app()


@pytest.fixture
async def client(app: FastAPI):
    async with au.client_for(app) as c:
        yield c
