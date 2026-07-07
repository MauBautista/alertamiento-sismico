"""Fixtures del WebSocket live (T-1.22 · B4).

El WS + LISTEN/NOTIFY + poller necesitan un servidor real y una conexión de
escucha viva → se levanta uvicorn EN el loop del test (no en un hilo) para tener
control async con timeouts (``asyncio.wait_for``). El cliente es la librería
``websockets`` (transitiva de uvicorn[standard]). La app de test monta el
``lifespan`` del hub + el router ``/ws``; NO usa ``main.create_app`` porque la
integración de /ws en main.py es de otra fase.

Semilla COMMITEADA (el WS lee en conexiones aparte, no en la txn del test):
3 tenants (A/B private, G gov_shared) + un tenant "agencia" para el gov_operator,
sitios, un sensor y un gateway en A. Teardown: TRUNCATE de lo que la suite
escribe (append-only → DELETE lo prohíbe el trigger; TRUNCATE no lo dispara).
"""

from __future__ import annotations

import asyncio
import os

import psycopg
import pytest
import uvicorn
from fastapi import FastAPI

import auth_utils as au
from takab_api.auth import deps
from takab_api.db.engine import get_engine
from takab_api.routers.ws import router as ws_router
from takab_api.ws import lifespan

# UUIDs propios (prefijo 6 → no colisionan: sync 1/2/3/9/a/b/c, auth_utils/B2 7,
# B1 catálogo 8, test_db_session d/5; B3 usa 60700000, que evitamos).
WS_TENANT_A = "61111111-1111-1111-1111-111111111111"
WS_TENANT_B = "62222222-2222-2222-2222-222222222222"
WS_TENANT_G = "63333333-3333-3333-3333-333333333333"
WS_TENANT_AGENCY = "69999999-9999-9999-9999-999999999999"
WS_SITE_A = "6a000000-0000-0000-0000-0000000000a1"
WS_SITE_B = "6b000000-0000-0000-0000-0000000000b1"
WS_SITE_G = "6c000000-0000-0000-0000-0000000000c1"
WS_SENSOR_A = "6a200000-0000-0000-0000-0000000000a2"
WS_GW_A = "6a100000-0000-0000-0000-0000000000a3"

_TENANT_IDS = [WS_TENANT_A, WS_TENANT_B, WS_TENANT_G, WS_TENANT_AGENCY]
_GEOM = "ST_SetSRID(ST_MakePoint(-99.13,19.43),4326)::geography"
_TRUNCATE = (
    "TRUNCATE incidents, incident_actions, audit_log, seismic_events, "
    "device_health, waveform_features_1s CASCADE"
)


def _raw_dsn() -> str:
    url = os.environ.get("DATABASE_URL", au_default())
    return url.replace("postgresql+psycopg://", "postgresql://")


def au_default() -> str:
    return "postgresql+psycopg://takab:takab_dev@127.0.0.1:5433/takab"


@pytest.fixture(autouse=True)
def _ws_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Entorno de auth de test + timeout de auth corto; limpia caches."""
    monkeypatch.setenv("TAKAB_API_AUTH_ISSUER", au.ISSUER)
    monkeypatch.setenv("TAKAB_API_AUTH_AUDIENCE", au.AUDIENCE)
    monkeypatch.setenv("TAKAB_API_AUTH_JWKS_JSON", au.jwks_json())
    monkeypatch.setenv("TAKAB_API_AUTH_DEV_PRIVATE_KEY", au.dev_private_key_pem())
    monkeypatch.setenv("TAKAB_API_WS_AUTH_TIMEOUT_S", "1.0")
    dsn = os.environ.get("DATABASE_URL")
    if dsn:
        monkeypatch.setenv("TAKAB_API_DATABASE_URL", dsn)
    deps._reset_caches()
    get_engine.cache_clear()
    yield
    deps._reset_caches()


@pytest.fixture
def ws_seed() -> None:
    """Siembra committeada de tenants/sitios/sensor/gateway; limpia al terminar."""
    conn = psycopg.connect(_raw_dsn(), autocommit=True)
    conn.execute("RESET ROLE")
    for tid, code, vis in (
        (WS_TENANT_A, "WSB_A", "private"),
        (WS_TENANT_B, "WSB_B", "private"),
        (WS_TENANT_G, "WSB_G", "gov_shared"),
        (WS_TENANT_AGENCY, "WSB_AG", "private"),
    ):
        conn.execute(
            "INSERT INTO tenants (tenant_id, code, name, visibility) "
            "VALUES (%s,%s,'WS test',%s) ON CONFLICT (tenant_id) DO NOTHING",
            (tid, code, vis),
        )
    for sid, tid in ((WS_SITE_A, WS_TENANT_A), (WS_SITE_B, WS_TENANT_B), (WS_SITE_G, WS_TENANT_G)):
        conn.execute(
            "INSERT INTO sites (site_id, tenant_id, code, name, geom) "
            f"VALUES (%s,%s,%s,'Sitio',{_GEOM}) ON CONFLICT (site_id) DO NOTHING",
            (sid, tid, sid[:6]),
        )
    conn.execute(
        "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial) "
        "VALUES (%s,%s,%s,'WS-SER-A') ON CONFLICT (gateway_id) DO NOTHING",
        (WS_GW_A, WS_TENANT_A, WS_SITE_A),
    )
    conn.execute(
        "INSERT INTO sensors (sensor_id, tenant_id, site_id, kind, model) "
        "VALUES (%s,%s,%s,'ground','RS4D') ON CONFLICT (sensor_id) DO NOTHING",
        (WS_SENSOR_A, WS_TENANT_A, WS_SITE_A),
    )
    try:
        yield
    finally:
        # Deja la DB como la encontró: primero el negocio/series (append-only →
        # TRUNCATE, que no dispara el trigger), luego el catálogo hijo→padre.
        conn.execute("RESET ROLE")
        conn.execute(_TRUNCATE)
        conn.execute("DELETE FROM sensors WHERE tenant_id = ANY(%s)", (_TENANT_IDS,))
        conn.execute("DELETE FROM gateways WHERE tenant_id = ANY(%s)", (_TENANT_IDS,))
        conn.execute("DELETE FROM sites WHERE tenant_id = ANY(%s)", (_TENANT_IDS,))
        conn.execute("DELETE FROM tenants WHERE tenant_id = ANY(%s)", (_TENANT_IDS,))
        conn.close()


@pytest.fixture
async def ws_server(ws_seed) -> str:
    """Levanta uvicorn en el loop del test; entrega la base ws://host:port."""
    app = FastAPI(lifespan=lifespan)
    app.include_router(ws_router)
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", lifespan="on")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    try:
        while not server.started:
            await asyncio.sleep(0.01)
        port = server.servers[0].sockets[0].getsockname()[1]
        yield f"ws://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await task
        if get_engine.cache_info().currsize:
            await get_engine().dispose()
        get_engine.cache_clear()
