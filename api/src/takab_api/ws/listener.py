"""Tarea LISTEN de fondo del WebSocket live (T-1.22 · B4).

Una única tarea con una ``AsyncConnection`` de psycopg dedicada (autocommit) que
hace ``LISTEN takab_live`` e itera ``notifies()``. Cada NOTIFY (payload mínimo de
la migración 0004) se entrega a ``hub.dispatch`` que re-consulta la fila con los
GUCs del suscriptor. Conexión aparte de SQLAlchemy: LISTEN no se multiplexa en el
pool de requests. Reconecta con backoff ante caídas; ``hub._ready`` desbloquea a
``hub.start`` en cuanto el canal queda activo (evita la carrera "inserto antes de
que el LISTEN esté escuchando").
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

from takab_api.settings import Settings

if TYPE_CHECKING:
    from takab_api.ws.hub import Hub

logger = logging.getLogger("takab_api.ws")

_RECONNECT_BACKOFF_S = 1.0


def _raw_dsn(database_url: str) -> str:
    """DSN psycopg crudo (LISTEN no pasa por SQLAlchemy): quita el ``+psycopg``."""
    return database_url.replace("postgresql+psycopg://", "postgresql://")


async def run_listener(hub: Hub) -> None:
    """LISTEN takab_live → ``hub.dispatch`` por cada notify, con reconexión."""
    import psycopg

    dsn = _raw_dsn(Settings().database_url)
    while hub._running:
        conn = None
        try:
            conn = await psycopg.AsyncConnection.connect(dsn, autocommit=True)
            await conn.execute("LISTEN takab_live")
            hub._ready.set()
            async for notify in conn.notifies():
                try:
                    payload = json.loads(notify.payload)
                except (ValueError, TypeError):
                    logger.warning("ws: NOTIFY con payload no-JSON")
                    continue
                try:
                    await hub.dispatch(payload)
                except Exception:  # noqa: BLE001 - un notify no debe tumbar el loop
                    logger.exception("ws: fallo despachando notify")
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - reconecta ante caída de la conexión
            logger.exception("ws: LISTEN caído; reintentando")
            await asyncio.sleep(_RECONNECT_BACKOFF_S)
        finally:
            if conn is not None:
                await conn.close()
