"""Authz del WebSocket ``/ws`` (T-1.22 · B4 + T-2.08 — regla de oro #5).

El canal live impone allowlist topic×rol DEFAULT-DENY (spec móvil §5.3):
- Consola C4I (RBAC §2) y tácticos móviles (brigadista/security_guard con
  surface móvil — RBAC §3 ``panel_read``) suscriben incidents/site_state/
  features, siempre acotados a ``site_scope``;
- ``occupant`` queda FUERA del WS: su handshake cierra 4401 (push + REST);
- tope de pollers de features por socket (no tareas ilimitadas contra el pool).
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest
import websockets

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


async def test_occupant_cerrado_en_el_handshake(ws_server: str) -> None:
    """[T-2.08] El occupant queda FUERA del WS (spec §5.3: push despertador +
    REST verdad): token VÁLIDO pero sin topic posible ⇒ close 4401 inmediato —
    el canal no mantiene sockets ociosos que jamás podrán suscribirse."""
    tok = au.make_token("occupant", tenant=WS_TENANT_A, surface="mobile")
    ws = await w.connect(ws_server)
    await w.send(ws, {"type": "auth", "token": tok})
    with pytest.raises(websockets.exceptions.ConnectionClosed) as exc:
        await w.recv(ws)
    assert exc.value.rcvd is not None and exc.value.rcvd.code == 4401


async def test_brigadista_movil_entra_acotado_a_su_sitio(ws_server: str) -> None:
    """[T-2.08] Táctico móvil (RBAC §3 ``panel_read``): suscribe los topics de
    la consola; ``features`` fuera de su ``site_scope`` ⇒ rechazo default-deny;
    dentro ⇒ el poller entrega el strip (mismo payload que la consola)."""
    tok = au.make_token("brigadista", tenant=WS_TENANT_A, surface="mobile", site_scope=WS_SITE_A)
    ws = await _auth_ready(ws_server, tok)
    try:
        # topics de canal ancho: aceptados en silencio (solo el error responde)
        for topic in ("incidents", "site_state"):
            await w.send(ws, {"type": "subscribe", "topic": topic})
        # fuera de su alcance: rechazo explícito
        await w.send(ws, {"type": "subscribe", "topic": f"features:{WS_SITE_B}"})
        denied = await w.recv(ws, timeout=2.0)
        assert denied["type"] == "error"
        # dentro de su alcance: datos reales
        await asyncio.to_thread(_seed_feature_a)
        await w.send(ws, {"type": "subscribe", "topic": f"features:{WS_SITE_A}"})
        frame = await w.recv(ws, timeout=3.0)
        assert frame["type"] == "features"
        assert frame["site_id"] == WS_SITE_A
    finally:
        await ws.close()


async def test_brigadista_surface_web_denegado(ws_server: str) -> None:
    """[T-2.08] La allowlist exige surface móvil al táctico: un token anómalo
    con surface=web no suscribe nada (default-deny, jamás 'por si acaso')."""
    tok = au.make_token("brigadista", tenant=WS_TENANT_A, surface="web", site_scope=WS_SITE_A)
    ws = await _auth_ready(ws_server, tok)
    try:
        await w.send(ws, {"type": "subscribe", "topic": "site_state"})
        assert (await w.recv(ws, timeout=2.0))["type"] == "error"
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
