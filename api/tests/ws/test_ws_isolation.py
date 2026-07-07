"""Aislamiento multi-tenant del WS (T-1.22 · B4 — regla de oro #5).

Un socket del tenant B NUNCA recibe frames del tenant A. Un gov_operator solo
recibe incidentes de tenants ``gov_shared`` (nunca de un tenant privado). La
autoridad es la re-consulta RLS del hub con los GUCs del suscriptor; el payload
del NOTIFY jamás se reenvía.
"""

from __future__ import annotations

import asyncio
import os

import pytest

import auth_utils as au
from tests.ws import _wsutil as w
from tests.ws.conftest import (
    WS_SITE_A,
    WS_SITE_B,
    WS_SITE_G,
    WS_TENANT_A,
    WS_TENANT_AGENCY,
    WS_TENANT_B,
    WS_TENANT_G,
)

pytestmark = pytest.mark.asyncio

_fake = w.load_fake_ingest()

# margen tras el punto de sincronía (el socket testigo ya recibió) para afirmar
# que el socket aislado NO recibió: si hubiera fuga, llegaría en el mismo dispatch.
_GRACE_S = 0.5


def _quake(tenant: str, site: str) -> dict[str, str]:
    conn = _fake.connect(_fake.raw_dsn(os.environ["DATABASE_URL"]))
    try:
        return _fake.insert_quake(conn, tenant=tenant, site=site, sensor=tenant, gateway=tenant)
    finally:
        conn.close()


async def test_tenant_b_never_receives_tenant_a(ws_server: str) -> None:
    tok_a = au.make_token("soc_operator", tenant=WS_TENANT_A)
    tok_b = au.make_token("soc_operator", tenant=WS_TENANT_B)
    ws_a = await w.auth_subscribe(ws_server, tok_a, "incidents")
    ws_b = await w.auth_subscribe(ws_server, tok_b, "incidents")
    try:
        ids = await asyncio.to_thread(_quake, WS_TENANT_A, WS_SITE_A)
        # A (testigo) recibe → punto de sincronía.
        frame_a = await w.recv(ws_a, timeout=2.0)
        assert frame_a["incident_id"] == ids["incident_id"]
        # B no recibe nada (ni el incidente ni sus acciones).
        with pytest.raises(asyncio.TimeoutError):
            await w.recv(ws_b, timeout=_GRACE_S)
    finally:
        await ws_a.close()
        await ws_b.close()


async def test_gov_receives_gov_shared_not_private(ws_server: str) -> None:
    tok_gov = au.make_token("gov_operator", tenant=WS_TENANT_AGENCY)
    tok_g = au.make_token("soc_operator", tenant=WS_TENANT_G)
    ws_gov = await w.auth_subscribe(ws_server, tok_gov, "incidents")
    ws_g = await w.auth_subscribe(ws_server, tok_g, "incidents")
    try:
        # incidente en tenant PRIVADO A → gov NO debe verlo.
        ids_priv = await asyncio.to_thread(_quake, WS_TENANT_A, WS_SITE_A)
        assert ids_priv["incident_id"]
        with pytest.raises(asyncio.TimeoutError):
            await w.recv(ws_gov, timeout=_GRACE_S)

        # incidente en tenant GOV_SHARED → gov SÍ lo ve (y el dueño también).
        ids_gov = await asyncio.to_thread(_quake, WS_TENANT_G, WS_SITE_G)
        frame_owner = await w.recv(ws_g, timeout=2.0)
        assert frame_owner["incident_id"] == ids_gov["incident_id"]
        frame_gov = await w.recv(ws_gov, timeout=2.0)
        assert frame_gov["type"] == "incident"
        assert frame_gov["incident_id"] == ids_gov["incident_id"]
        assert frame_gov["tenant_id"] == WS_TENANT_G
    finally:
        await ws_gov.close()
        await ws_g.close()


async def test_gov_isolation_uses_requery_not_payload(ws_server: str) -> None:
    """Sanity extra: dos incidentes B seguidos no cruzan a A por caché de clase."""
    tok_a = au.make_token("soc_operator", tenant=WS_TENANT_A)
    ws_a = await w.auth_subscribe(ws_server, tok_a, "incidents")
    try:
        await asyncio.to_thread(_quake, WS_TENANT_B, WS_SITE_B)
        await asyncio.to_thread(_quake, WS_TENANT_B, WS_SITE_B)
        with pytest.raises(asyncio.TimeoutError):
            await w.recv(ws_a, timeout=_GRACE_S)
    finally:
        await ws_a.close()
