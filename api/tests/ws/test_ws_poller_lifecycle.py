"""Ciclo de vida de los pollers de features (T-1.22 · B4).

Regresión del zombie: cuando el propio poller detecta el socket muerto (su
``_send`` falla → ``unregister`` → ``_cancel_pollers`` se topa con su PROPIA
tarea), la tarea debe TERMINAR — no resucitar y seguir consultando la DB a 1 Hz
tras quedar desreferenciada (fuga de tareas + agotamiento del pool).
"""

from __future__ import annotations

import asyncio
import os

import pytest
from starlette.websockets import WebSocketState

from takab_api.auth.claims import ALL_SITES, Claims
from takab_api.db.engine import get_engine
from takab_api.ws.hub import hub
from tests.ws import _wsutil as w
from tests.ws.conftest import WS_SENSOR_A, WS_SITE_A, WS_TENANT_A

pytestmark = pytest.mark.asyncio

_fake = w.load_fake_ingest()


class _DeadWS:
    """WebSocket falso cuyo ``send_json`` siempre falla (socket medio-abierto)."""

    application_state = WebSocketState.CONNECTED

    def __init__(self) -> None:
        self.sends = 0

    async def send_json(self, frame: dict) -> None:
        self.sends += 1
        raise RuntimeError("socket muerto")


def _claims_a() -> Claims:
    return Claims(
        sub="u1",
        groups=("soc_operator",),
        tenant_id=WS_TENANT_A,
        role="soc_operator",
        site_scope=ALL_SITES,
        zone_id="",
        surface="web",
    )


def _seed_feature() -> None:
    conn = _fake.connect(_fake.raw_dsn(os.environ["DATABASE_URL"]))
    try:
        _fake.insert_feature(
            conn, tenant=WS_TENANT_A, site=WS_SITE_A, sensor=WS_SENSOR_A, pga_g=0.2
        )
    finally:
        conn.close()


async def test_features_poller_dies_on_dead_socket(ws_seed) -> None:
    await asyncio.to_thread(_seed_feature)
    dead = _DeadWS()
    sub = hub.register(dead, _claims_a())
    topic = f"features:{WS_SITE_A}"
    await hub.subscribe(sub, topic)
    task = sub.pollers[topic]
    try:
        # El poller consulta, encuentra la fila, intenta enviar → falla →
        # unregister → se cancela a sí mismo. Con el fix, la tarea TERMINA.
        for _ in range(50):
            if task.done():
                break
            await asyncio.sleep(0.1)
        assert task.done(), "el poller quedó zombie tras el socket muerto"
        assert dead.sends >= 1
        assert sub not in hub._subs
        assert not sub.pollers
    finally:
        if not task.done():
            task.cancel()
        hub._subs.discard(sub)
        if get_engine.cache_info().currsize:
            await get_engine().dispose()
        get_engine.cache_clear()
