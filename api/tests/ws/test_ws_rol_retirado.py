"""T-9.20 · D-42 — la baja de los roles viejos en el canal live.

Pasada ``roles_heredados_hasta``, un token con rol viejo cierra ``4401`` con MOTIVO
``rol_retirado`` (el mismo detalle que el 401 de REST), y ANTES que el tope de
sesión: un ``4440`` mandaría a la persona a re-entrar para chocar con lo mismo.
Con la ventana abierta, el rol viejo entra canonizado.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

import pytest
import websockets

import auth_utils as au
from takab_api.auth import deps
from tests.ws import _wsutil as w
from tests.ws.conftest import WS_TENANT_A

pytestmark = pytest.mark.asyncio

DAY = 86_400


async def _cierre(ws_server: str, token: str) -> tuple[int | None, str | None]:
    ws = await w.connect(ws_server)
    try:
        await w.send(ws, {"type": "auth", "token": token})
        with pytest.raises(websockets.ConnectionClosed):
            while True:
                await asyncio.wait_for(ws.recv(), timeout=4.0)
        return ws.close_code, ws.close_reason
    finally:
        await ws.close()


def _baja_pasada(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "TAKAB_API_ROLES_HEREDADOS_HASTA", (date.today() - timedelta(days=2)).isoformat()
    )
    deps._reset_caches()


async def test_rol_viejo_en_ventana_abierta_recibe_ready(ws_server: str) -> None:
    tok = au.make_token("soc_operator", tenant=WS_TENANT_A)
    ws = await w.connect(ws_server)
    try:
        await w.send(ws, {"type": "auth", "token": tok})
        assert await w.recv(ws) == {"type": "ready"}
    finally:
        await ws.close()


async def test_pasada_la_baja_cierra_4401_con_motivo_rol_retirado(
    ws_server: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _baja_pasada(monkeypatch)
    tok = au.make_token("soc_operator", tenant=WS_TENANT_A)
    assert await _cierre(ws_server, tok) == (4401, "rol_retirado")


async def test_rol_retirado_gana_a_la_sesion_caducada(
    ws_server: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _baja_pasada(monkeypatch)
    tok = au.make_token("security_guard", tenant=WS_TENANT_A, surface="mobile", auth_age=40 * DAY)
    assert await _cierre(ws_server, tok) == (4401, "rol_retirado")


async def test_pasada_la_baja_el_canonico_sigue_entrando(
    ws_server: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _baja_pasada(monkeypatch)
    tok = au.make_token("tenant_admin", tenant=WS_TENANT_A)
    ws = await w.connect(ws_server)
    try:
        await w.send(ws, {"type": "auth", "token": tok})
        assert await w.recv(ws) == {"type": "ready"}
    finally:
        await ws.close()
