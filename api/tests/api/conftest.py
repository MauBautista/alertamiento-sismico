"""Fixtures de los tests HTTP de B2 (incidents/events/dictamens/rule_sets).

Mismo patrón que ``tests/auth/conftest.py``: entorno alineado al keypair/JWKS de
test, engine async por test (pytest-asyncio usa un loop por función), siembra
COMMITEADA (bypass RLS como superusuario) y limpieza por TRUNCATE al terminar
(las tablas de negocio son append-only: DELETE lo prohíbe un trigger, TRUNCATE no).
La app monta los routers de B2 sobre ``create_app`` sin tocar ``main.py``.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from sqlalchemy import text

import auth_utils as au
from takab_api.auth import deps
from takab_api.db.engine import get_engine
from takab_api.main import create_app
from takab_api.routers.dictamens import router as dictamens_router
from takab_api.routers.events import router as events_router
from takab_api.routers.incidents import router as incidents_router
from takab_api.routers.rule_sets import router as rule_sets_router

_GEOM = "ST_SetSRID(ST_MakePoint(-99.13,19.43),4326)::geography"

# Sensores commiteados (prefijo 7 → no colisiona con seeds sync/auth previos).
SENSOR_PRIV = "7a200000-0000-0000-0000-0000000000a2"
SENSOR_PRIV2 = "7b200000-0000-0000-0000-0000000000b2"


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


# Tablas que estos tests COMMITEAN. CASCADE resuelve las dependencias FK entre
# ellas; tenants/sites/sensors se dejan sembrados (idempotentes) como en auth.
_TRUNCATE_WRITTEN = text(
    "TRUNCATE seismic_events, incidents, incident_actions, dictamens, "
    "evidence_objects, quorum_votes, rule_sets, audit_log, "
    "commands, gateway_config_state, user_profiles, reference_earthquakes, "
    "drills, drill_sites CASCADE"
)


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
async def base_data(db_engine) -> None:
    """Siembra tenants (A/B private, G gov_shared) + un sitio y sensor por tenant."""
    engine = get_engine()
    async with engine.begin() as conn:
        for tid, code, vis in (
            (au.DB_TENANT_PRIV, "B2_A", "private"),
            (au.DB_TENANT_PRIV2, "B2_B", "private"),
            (au.DB_TENANT_GOV, "B2_G", "gov_shared"),
        ):
            await conn.execute(
                text(
                    "INSERT INTO tenants (tenant_id, code, name, visibility) "
                    "VALUES (:id, :code, 'B2 test', :vis) "
                    "ON CONFLICT (tenant_id) DO NOTHING"
                ),
                {"id": tid, "code": code, "vis": vis},
            )
        for sid, tid, code in (
            (au.DB_SITE_PRIV, au.DB_TENANT_PRIV, "B2SA"),
            (au.DB_SITE_PRIV2, au.DB_TENANT_PRIV2, "B2SB"),
            (au.DB_SITE_GOV, au.DB_TENANT_GOV, "B2SG"),
        ):
            await conn.execute(
                text(
                    "INSERT INTO sites (site_id, tenant_id, code, name, geom) "
                    f"VALUES (:sid, :tid, :code, 'Sitio', {_GEOM}) "
                    "ON CONFLICT (site_id) DO NOTHING"
                ),
                {"sid": sid, "tid": tid, "code": code},
            )
        for snid, tid, sid in (
            (SENSOR_PRIV, au.DB_TENANT_PRIV, au.DB_SITE_PRIV),
            (SENSOR_PRIV2, au.DB_TENANT_PRIV2, au.DB_SITE_PRIV2),
        ):
            await conn.execute(
                text(
                    "INSERT INTO sensors (sensor_id, tenant_id, site_id, kind, model) "
                    "VALUES (:id, :tid, :sid, 'ground', 'RS4D') "
                    "ON CONFLICT (sensor_id) DO NOTHING"
                ),
                {"id": snid, "tid": tid, "sid": sid},
            )


@pytest.fixture
def make_incident(base_data) -> Callable[..., Awaitable[str]]:
    """Crea un incidente commiteado y devuelve su id."""

    async def _make(
        tenant_id: str,
        site_id: str,
        *,
        opened_at: datetime | None = None,
        severity: str = "warning",
        state: str = "open",
        trigger: str = "sasmex",
        event_id: str | None = None,
        incident_id: str | None = None,
    ) -> str:
        engine = get_engine()
        iid = incident_id or str(uuid.uuid4())
        ts = opened_at or datetime.now(UTC)
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO incidents (incident_id, event_uuid, tenant_id, site_id, "
                    "event_id, opened_at, severity, state, trigger) "
                    "VALUES (:i, gen_random_uuid(), :t, :s, :evt, :o, :sev, :st, :trg)"
                ),
                {
                    "i": iid,
                    "t": tenant_id,
                    "s": site_id,
                    "evt": event_id,
                    "o": ts,
                    "sev": severity,
                    "st": state,
                    "trg": trigger,
                },
            )
        return iid

    return _make


@pytest.fixture
def make_action(base_data) -> Callable[..., Awaitable[None]]:
    """Añade una fila a incident_actions (timeline append-only)."""

    async def _make(incident_id: str, tenant_id: str, *, kind: str, actor: str) -> None:
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO incident_actions (incident_id, tenant_id, kind, actor) "
                    "VALUES (:i, :t, :k, :a)"
                ),
                {"i": incident_id, "t": tenant_id, "k": kind, "a": actor},
            )

    return _make


@pytest.fixture
def make_event(base_data) -> Callable[..., Awaitable[str]]:
    """Crea un seismic_event (dato de red) y devuelve su event_id textual."""

    async def _make(
        *,
        source: str = "local_quorum",
        detected_at: datetime | None = None,
        magnitude: float | None = None,
        event_id: str | None = None,
    ) -> str:
        engine = get_engine()
        eid = event_id or f"EVT-{uuid.uuid4().hex[:12]}"
        ts = detected_at or datetime.now(UTC)
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO seismic_events (event_id, source, magnitude, detected_at) "
                    "VALUES (:e, :src, :mag, :ts)"
                ),
                {"e": eid, "src": source, "mag": magnitude, "ts": ts},
            )
        return eid

    return _make


@pytest.fixture
def make_vote(base_data) -> Callable[..., Awaitable[None]]:
    """Añade un voto de quórum al evento (con delta_s)."""

    async def _make(
        event_id: str,
        sensor_id: str,
        *,
        pga_g: float = 0.12,
        delta_s: float | None = 0.4,
        counted: bool = True,
        detected_at: datetime | None = None,
    ) -> None:
        engine = get_engine()
        ts = detected_at or datetime.now(UTC)
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO quorum_votes "
                    "(event_id, sensor_id, detected_at, pga_g, delta_s, counted) "
                    "VALUES (:e, :s, :ts, :pga, :d, :c)"
                ),
                {"e": event_id, "s": sensor_id, "ts": ts, "pga": pga_g, "d": delta_s, "c": counted},
            )

    return _make


@pytest.fixture
def make_dictamen(base_data) -> Callable[..., Awaitable[str]]:
    """Inserta un dictamen commiteado (para probar la cadena/lectura)."""

    async def _make(
        tenant_id: str,
        incident_id: str,
        *,
        status: str = "inhabit_monitor",
        signed_by: str | None = None,
        supersedes: str | None = None,
    ) -> str:
        engine = get_engine()
        did = str(uuid.uuid4())
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO dictamens (dictamen_id, tenant_id, incident_id, status, "
                    "basis, signed_by, supersedes_dictamen_id) "
                    "VALUES (:d, :t, :i, :st, '{}'::jsonb, "
                    "CAST(:sb AS uuid), CAST(:sup AS uuid))"
                ),
                {
                    "d": did,
                    "t": tenant_id,
                    "i": incident_id,
                    "st": status,
                    "sb": signed_by,
                    "sup": supersedes,
                },
            )
        return did

    return _make


@pytest.fixture
def app() -> FastAPI:
    """App de test: ``create_app`` + los routers de B2 (integración = fase 2)."""
    application = create_app()
    application.include_router(incidents_router)
    application.include_router(events_router)
    application.include_router(dictamens_router)
    application.include_router(rule_sets_router)
    return application


@pytest.fixture
async def client(app: FastAPI):
    async with au.client_for(app) as c:
        yield c
