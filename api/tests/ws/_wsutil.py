"""Helpers de los tests WS: cliente ``websockets`` + carga de fake_ingest."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import pathlib
from typing import Any

import websockets

_SCRIPTS = pathlib.Path(__file__).resolve().parents[2] / "scripts"


def load_fake_ingest() -> Any:
    """Importa scripts/fake_ingest.py (no está en el pythonpath del paquete)."""
    path = _SCRIPTS / "fake_ingest.py"
    spec = importlib.util.spec_from_file_location("fake_ingest", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


async def connect(base: str) -> Any:
    return await websockets.connect(base + "/ws")


async def send(ws: Any, obj: dict[str, Any]) -> None:
    await ws.send(json.dumps(obj))


async def recv(ws: Any, timeout: float = 2.0) -> dict[str, Any]:
    return json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))


async def auth_subscribe(base: str, token: str, topic: str) -> Any:
    """Abre socket, autentica, espera ``ready`` y se suscribe a ``topic``."""
    ws = await connect(base)
    await send(ws, {"type": "auth", "token": token})
    ready = await recv(ws)
    assert ready["type"] == "ready"
    await send(ws, {"type": "subscribe", "topic": topic})
    return ws
