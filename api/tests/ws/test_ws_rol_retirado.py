"""T-9.81 · D-42 — la baja de los roles viejos en el canal live.

Un token con rol viejo cierra SIEMPRE ``4401`` con MOTIVO ``rol_retirado`` (el mismo
detalle que el 401 de REST), sin fecha que lo abra, y ANTES que el tope de sesión: un
``4440`` mandaría a la persona a re-entrar para chocar con lo mismo.
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


@pytest.mark.parametrize(
    ("viejo", "surface"),
    [("soc_operator", "web"), ("security_guard", "mobile"), ("building_admin", "both")],
)
async def test_rol_viejo_cierra_4401_con_motivo_rol_retirado(
    ws_server: str, viejo: str, surface: str
) -> None:
    tok = au.make_token(viejo, tenant=WS_TENANT_A, surface=surface)
    assert await _cierre(ws_server, tok) == (4401, "rol_retirado")


async def test_la_variable_vieja_con_fecha_futura_no_abre_nada(
    ws_server: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(
        "TAKAB_API_ROLES_HEREDADOS_HASTA", (date.today() + timedelta(days=365)).isoformat()
    )
    deps._reset_caches()
    tok = au.make_token("soc_operator", tenant=WS_TENANT_A)
    assert await _cierre(ws_server, tok) == (4401, "rol_retirado")


async def test_rol_retirado_gana_a_la_sesion_caducada(ws_server: str) -> None:
    tok = au.make_token("security_guard", tenant=WS_TENANT_A, surface="mobile", auth_age=40 * DAY)
    assert await _cierre(ws_server, tok) == (4401, "rol_retirado")


async def test_el_canonico_sigue_entrando(ws_server: str) -> None:
    tok = au.make_token("tenant_admin", tenant=WS_TENANT_A)
    ws = await w.connect(ws_server)
    try:
        await w.send(ws, {"type": "auth", "token": tok})
        assert await w.recv(ws) == {"type": "ready"}
    finally:
        await ws.close()
