"""Authz del WebSocket ``/ws`` (T-1.22 · B4 — regla de oro #5 / RBAC §2, §5.2).

El canal live impone el MISMO gate que el REST equivalente:
- rol con Consola C4I (RBAC §2): un rol móvil-only recibe error al suscribirse a
  cualquier topic (el REST le daría 403);
- ``features:<site_id>`` respeta el ``site_scope`` default-deny del token;
- tope de pollers de features por socket (no tareas ilimitadas contra el pool).
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest

import auth_utils as au
from takab_api.auth import deps
from tests.ws import _wsutil as w
from tests.ws.conftest import WS_SENSOR_A, WS_SITE_A, WS_SITE_B, WS_TENANT_A

pytestmark = pytest.mark.asyncio

_fake = w.load_fake_ingest()


def _seed_feature_a() -> None:
    conn = _fake.connect(_fake.raw_dsn(os.environ["DATABASE_URL"]))
    try:
        _fake.insert_feature(
            conn, tenant=WS_TENANT_A, site=WS_SITE_A, sensor=WS_SENSOR_A, pga_g=0.2
        )
    finally:
        conn.close()


async def _auth_ready(ws_server: str, token: str):
    ws = await w.connect(ws_server)
    await w.send(ws, {"type": "auth", "token": token})
    assert (await w.recv(ws))["type"] == "ready"
    return ws


async def test_mobile_only_role_denied_on_every_topic(ws_server: str) -> None:
    # occupant es móvil-only (RBAC §2/§3: sin Consola C4I ni salud gabinete ni
    # features). El token es válido; ninguna suscripción debe entregar datos.
    tok = au.make_token("occupant", tenant=WS_TENANT_A)
    ws = await _auth_ready(ws_server, tok)
    try:
        for topic in ("incidents", "site_state", f"features:{WS_SITE_A}"):
            await w.send(ws, {"type": "subscribe", "topic": topic})
            resp = await w.recv(ws, timeout=2.0)
            assert resp["type"] == "error", f"topic {topic} no fue rechazado"
    finally:
        await ws.close()


async def test_features_site_scope_denies_out_of_scope(ws_server: str) -> None:
    # soc_operator acotado a WS_SITE_A: features de otro sitio → rechazo; su
    # propio sitio → poller activo (recibe el strip sembrado).
    tok = au.make_token("soc_operator", tenant=WS_TENANT_A, site_scope=WS_SITE_A)
    ws = await _auth_ready(ws_server, tok)
    try:
        await w.send(ws, {"type": "subscribe", "topic": f"features:{WS_SITE_B}"})
        denied = await w.recv(ws, timeout=2.0)
        assert denied["type"] == "error"

        await asyncio.to_thread(_seed_feature_a)
        await w.send(ws, {"type": "subscribe", "topic": f"features:{WS_SITE_A}"})
        frame = await w.recv(ws, timeout=3.0)
        assert frame["type"] == "features"
        assert frame["site_id"] == WS_SITE_A
    finally:
        await ws.close()


async def test_features_poller_cap_per_socket(ws_server: str) -> None:
    # Con site_scope='*' el gate de scope no aplica; el tope por socket sí acota
    # cuántos pollers puede abrir un único cliente.
    cap = deps._settings().ws_max_feature_pollers
    tok = au.make_token("soc_operator", tenant=WS_TENANT_A, site_scope="*")
    ws = await _auth_ready(ws_server, tok)
    try:
        # Hasta el tope: sitios aleatorios (RLS → vacío, sin frame ni error).
        for _ in range(cap):
            await w.send(ws, {"type": "subscribe", "topic": f"features:{uuid.uuid4()}"})
        # Uno más allá del tope → error explícito.
        await w.send(ws, {"type": "subscribe", "topic": f"features:{uuid.uuid4()}"})
        resp = await w.recv(ws, timeout=2.0)
        assert resp["type"] == "error"
    finally:
        await ws.close()
