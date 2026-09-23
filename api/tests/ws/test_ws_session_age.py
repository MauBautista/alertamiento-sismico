"""T-8.02 · D-38 — el tope de sesión en el canal live.

Dos códigos de cierre y NO son intercambiables, porque el cliente hace cosas
distintas con cada uno (``shared/sdk-ts/src/live.ts``):

- ``4401`` — token inválido o vencido: RENOVABLE. El cliente pide un token nuevo
  una vez y reconecta.
- ``4440`` — la sesión llegó a su tope (``auth_time`` + edad máxima del rol): NO
  renovable. Renovar el token no sirve —el refresco no mueve ``auth_time``— y
  reintentarlo sería un bucle; el cliente manda a la persona a iniciar sesión.

El plazo del socket vivo es ``min(exp, session_deadline)``: el que llegue antes
decide el código.
"""

from __future__ import annotations

import asyncio

import pytest
import websockets

import auth_utils as au
from takab_api.routers.ws import WS_SESSION_EXPIRED
from tests.ws import _wsutil as w
from tests.ws.conftest import WS_TENANT_A

pytestmark = pytest.mark.asyncio

DAY = 86_400


async def _close_code(ws_server: str, token: str, *, wait: float = 4.0) -> int | None:
    ws = await w.connect(ws_server)
    try:
        await w.send(ws, {"type": "auth", "token": token})
        with pytest.raises(websockets.ConnectionClosed):
            while True:  # puede llegar `ready` antes del cierre
                await asyncio.wait_for(ws.recv(), timeout=wait)
        return ws.close_code
    finally:
        await ws.close()


async def test_el_codigo_es_el_del_contrato() -> None:
    """``shared/sdk-ts/src/live.ts::WS_SESSION_EXPIRED`` dice 4440."""
    assert WS_SESSION_EXPIRED == 4440


async def test_sesion_ya_caducada_en_el_handshake_cierra_4440(ws_server: str) -> None:
    tok = au.make_token("soc_operator", tenant=WS_TENANT_A, auth_age=DAY + 1)
    assert await _close_code(ws_server, tok) == 4440


async def test_brigadista_caducado_en_el_handshake_cierra_4440(ws_server: str) -> None:
    tok = au.make_token("brigadista", tenant=WS_TENANT_A, surface="mobile", auth_age=31 * DAY)
    assert await _close_code(ws_server, tok) == 4440


async def test_sesion_vigente_recibe_ready(ws_server: str) -> None:
    tok = au.make_token("soc_operator", tenant=WS_TENANT_A, auth_age=DAY - 60)
    ws = await w.connect(ws_server)
    try:
        await w.send(ws, {"type": "auth", "token": tok})
        assert await w.recv(ws) == {"type": "ready"}
    finally:
        await ws.close()


async def test_la_sesion_que_termina_con_el_socket_abierto_cierra_4440(ws_server: str) -> None:
    """El tope llega ANTES que el exp del token ⇒ 4440 (no renovable)."""
    tok = au.make_token("soc_operator", tenant=WS_TENANT_A, auth_age=DAY - 2, exp_delta=3600)
    ws = await w.connect(ws_server)
    try:
        await w.send(ws, {"type": "auth", "token": tok})
        assert await w.recv(ws) == {"type": "ready"}
        with pytest.raises(websockets.ConnectionClosed):
            await asyncio.wait_for(ws.recv(), timeout=6.0)
        assert ws.close_code == 4440
    finally:
        await ws.close()


async def test_el_token_que_vence_antes_que_la_sesion_sigue_cerrando_4401(
    ws_server: str,
) -> None:
    """El exp del token llega ANTES que el tope ⇒ 4401 como siempre (renovable)."""
    tok = au.make_token("soc_operator", tenant=WS_TENANT_A, exp_delta=2)
    ws = await w.connect(ws_server)
    try:
        await w.send(ws, {"type": "auth", "token": tok})
        assert await w.recv(ws) == {"type": "ready"}
        with pytest.raises(websockets.ConnectionClosed):
            await asyncio.wait_for(ws.recv(), timeout=6.0)
        assert ws.close_code == 4401
    finally:
        await ws.close()


async def test_token_sin_auth_time_cierra_4401(ws_server: str) -> None:
    """Sin ``auth_time`` el token es inválido (no «sesión caducada»)."""
    tok = au.make_token("soc_operator", tenant=WS_TENANT_A, drop=("auth_time",))
    assert await _close_code(ws_server, tok) == 4401
