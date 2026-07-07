"""WebSocket live de la API TAKAB (T-1.22 · B4).

Fan-out por LISTEN/NOTIFY con fetch-on-notify: el hub re-consulta cada fila con
los GUCs del suscriptor (Postgres/RLS decide la visibilidad); el payload del
NOTIFY nunca se reenvía. Integración (main.py): pasar ``lifespan`` a ``FastAPI``
y montar ``routers.ws.router``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from takab_api.ws.hub import hub

__all__ = ["hub", "lifespan"]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Arranca/detiene la tarea LISTEN del hub junto con el ciclo de la app."""
    await hub.start()
    try:
        yield
    finally:
        await hub.stop()
