"""Entrega live de incidentes y features por WS (T-1.22 · B4, gate #5 / G4).

Un incidente escrito por ``takab_ingest`` (vía fake_ingest → dispara los triggers
de la migración 0004) llega al socket suscrito en <2 s. El feed de features 1 s
llega por el poller sobre la vista segura.
"""

from __future__ import annotations

import asyncio
import os
import time

import pytest

import auth_utils as au
from tests.ws import _wsutil as w
from tests.ws.conftest import WS_GW_A, WS_SENSOR_A, WS_SITE_A, WS_TENANT_A

pytestmark = pytest.mark.asyncio

_fake = w.load_fake_ingest()


def _dsn() -> str:
    return _fake.raw_dsn(os.environ["DATABASE_URL"])


def _quake_a() -> dict[str, str]:
    conn = _fake.connect(_dsn())
    try:
        return _fake.insert_quake(
            conn,
            tenant=WS_TENANT_A,
            site=WS_SITE_A,
            sensor=WS_SENSOR_A,
            gateway=WS_GW_A,
        )
    finally:
        conn.close()


def _feature_a() -> None:
    conn = _fake.connect(_dsn())
    try:
        _fake.insert_feature(
            conn, tenant=WS_TENANT_A, site=WS_SITE_A, sensor=WS_SENSOR_A, pga_g=0.2
        )
    finally:
        conn.close()


async def test_incident_reaches_subscriber_under_2s(ws_server: str) -> None:
    tok = au.make_token("soc_operator", tenant=WS_TENANT_A)
    ws = await w.auth_subscribe(ws_server, tok, "incidents")
    try:
        t0 = time.monotonic()
        ids = await asyncio.to_thread(_quake_a)
        frame = await w.recv(ws, timeout=2.0)
        elapsed = time.monotonic() - t0
        assert frame["type"] == "incident"
        assert frame["incident_id"] == ids["incident_id"]
        assert frame["tenant_id"] == WS_TENANT_A
        assert frame["site_id"] == WS_SITE_A
        assert elapsed < 2.0
    finally:
        await ws.close()


async def test_incident_action_frames_follow(ws_server: str) -> None:
    tok = au.make_token("soc_operator", tenant=WS_TENANT_A)
    ws = await w.auth_subscribe(ws_server, tok, "incidents")
    try:
        ids = await asyncio.to_thread(_quake_a)
        types: list[str] = []
        # incident + 2 incident_actions (siren_on, gas_closed) = 3 frames.
        for _ in range(3):
            types.append((await w.recv(ws, timeout=2.0))["type"])
        assert types[0] == "incident"
        assert types.count("incident_action") == 2
        assert ids["incident_id"]
    finally:
        await ws.close()


async def test_features_poller_pushes_frame(ws_server: str) -> None:
    tok = au.make_token("soc_operator", tenant=WS_TENANT_A)
    await asyncio.to_thread(_feature_a)
    ws = await w.auth_subscribe(ws_server, tok, f"features:{WS_SITE_A}")
    try:
        frame = await w.recv(ws, timeout=3.0)
        assert frame["type"] == "features"
        assert frame["site_id"] == WS_SITE_A
        assert len(frame["rows"]) >= 1
        assert frame["rows"][0]["channel"] == "EHZ"
    finally:
        await ws.close()
