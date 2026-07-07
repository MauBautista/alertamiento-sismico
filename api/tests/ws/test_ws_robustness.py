"""Robustez del WebSocket ``/ws`` (T-1.22 · B4).

- Expiración del token en vuelo: el socket deja de recibir cuando el token vence
  (el REST equivalente daría 401 en cada request tras el exp).
- Frame binario: en la fase de auth cierra 4401 (previsto); tras auth responde un
  ErrorFrame de protocolo y mantiene el socket vivo (no desconexión abrupta).
"""

from __future__ import annotations

import asyncio

import pytest
import websockets

import auth_utils as au
from tests.ws import _wsutil as w
from tests.ws.conftest import WS_TENANT_A

pytestmark = pytest.mark.asyncio


async def test_expired_token_mid_socket_closes_4401(ws_server: str) -> None:
    tok = au.make_token("soc_operator", tenant=WS_TENANT_A, exp_delta=2)
    ws = await w.connect(ws_server)
    try:
        await w.send(ws, {"type": "auth", "token": tok})
        assert (await w.recv(ws))["type"] == "ready"
        # Pasado el exp (~2 s) sin frame entrante, el servidor cierra.
        with pytest.raises(websockets.ConnectionClosed):
            await asyncio.wait_for(ws.recv(), timeout=6.0)
        assert ws.close_code == 4401
    finally:
        await ws.close()


async def test_binary_frame_in_auth_closes_4401(ws_server: str) -> None:
    ws = await w.connect(ws_server)
    try:
        await ws.send(b"\x00\x01\x02")  # frame binario en la fase de auth
        with pytest.raises(websockets.ConnectionClosed):
            await asyncio.wait_for(ws.recv(), timeout=3.0)
        assert ws.close_code == 4401
    finally:
        await ws.close()


async def test_binary_frame_after_auth_gets_error_and_survives(ws_server: str) -> None:
    tok = au.make_token("soc_operator", tenant=WS_TENANT_A)
    ws = await w.connect(ws_server)
    try:
        await w.send(ws, {"type": "auth", "token": tok})
        assert (await w.recv(ws))["type"] == "ready"
        await ws.send(b"\x00\x01")  # binario tras auth → ErrorFrame, sin cerrar
        err = await w.recv(ws, timeout=2.0)
        assert err["type"] == "error"
        # El socket sigue vivo: un topic inválido devuelve otro ErrorFrame.
        await w.send(ws, {"type": "subscribe", "topic": "nope"})
        again = await w.recv(ws, timeout=2.0)
        assert again["type"] == "error"
    finally:
        await ws.close()
