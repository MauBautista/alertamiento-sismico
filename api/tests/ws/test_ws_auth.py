"""Auth del WebSocket ``/ws`` (T-1.22 · B4, gate #5).

El primer frame DEBE ser ``{"type":"auth","token":…}`` dentro de
``ws_auth_timeout_s``; si no llega o el token es inválido, el servidor cierra con
code 4401. El token nunca viaja por query string ni subprotocolo.
"""

from __future__ import annotations

import asyncio

import pytest
import websockets

import auth_utils as au
from tests.ws import _wsutil as w
from tests.ws.conftest import WS_TENANT_A

pytestmark = pytest.mark.asyncio


async def test_no_auth_within_timeout_closes_4401(ws_server: str) -> None:
    ws = await w.connect(ws_server)
    try:
        with pytest.raises(websockets.ConnectionClosed):
            # timeout de auth = 1.0 s (conftest); esperamos el close del servidor.
            await asyncio.wait_for(ws.recv(), timeout=3.0)
        assert ws.close_code == 4401
    finally:
        await ws.close()


async def test_invalid_token_closes_4401(ws_server: str) -> None:
    ws = await w.connect(ws_server)
    try:
        await w.send(ws, {"type": "auth", "token": "not-a-jwt"})
        with pytest.raises(websockets.ConnectionClosed):
            await asyncio.wait_for(ws.recv(), timeout=3.0)
        assert ws.close_code == 4401
    finally:
        await ws.close()


async def test_expired_token_closes_4401(ws_server: str) -> None:
    ws = await w.connect(ws_server)
    try:
        await w.send(ws, {"type": "auth", "token": au.expired_token(tenant=WS_TENANT_A)})
        with pytest.raises(websockets.ConnectionClosed):
            await asyncio.wait_for(ws.recv(), timeout=3.0)
        assert ws.close_code == 4401
    finally:
        await ws.close()


async def test_valid_auth_gets_ready(ws_server: str) -> None:
    tok = au.make_token("soc_operator", tenant=WS_TENANT_A)
    ws = await w.connect(ws_server)
    try:
        await w.send(ws, {"type": "auth", "token": tok})
        ready = await w.recv(ws)
        assert ready == {"type": "ready"}
    finally:
        await ws.close()


async def test_bad_topic_gets_error_frame(ws_server: str) -> None:
    tok = au.make_token("soc_operator", tenant=WS_TENANT_A)
    ws = await w.connect(ws_server)
    try:
        await w.send(ws, {"type": "auth", "token": tok})
        assert (await w.recv(ws))["type"] == "ready"
        await w.send(ws, {"type": "subscribe", "topic": "features:not-a-uuid"})
        err = await w.recv(ws)
        assert err["type"] == "error"
    finally:
        await ws.close()
