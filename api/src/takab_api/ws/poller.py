"""Poller de features live por sitio (T-1.22 · B4).

Por cada topic ``features:<site_id>`` suscrito, una tarea 1 Hz consulta
``waveform_features_1s_secure`` (la vista security_barrier — regla dura: la API
JAMÁS lee la tabla base) sobre una ventana corta reciente, con los GUCs del
suscriptor, y empuja un frame columnar. Si RLS/el JOIN a ``sites`` de la vista
oculta el sitio (otro tenant), la consulta vuelve vacía y no se envía nada.

Regla de oro 9: el "sismograma live" del SOC es un strip de features 1 s
(procesamiento edge), NO waveform crudo 100 sps.

[T-2.121] **Tope de espera por lock, y por qué aquí NO se cierra el socket.**
Un ACCESS EXCLUSIVE ajeno sobre la tabla base de la vista dejaba a cada ciclo
dentro de la consulta indefinidamente, reteniendo su conexión: con el pool en
5+5, diez sitios vigilados bastaban para que un request REST cualquiera se
quedara sin conexión (medido: ``TimeoutError`` del pool a los 30 s). Con el tope
el ciclo cede, lo registra y vuelve solo en cuanto la tabla se libera.

La degradación del strip ya es VISIBLE sin tocar nada más: sin frames,
``DetailPanel`` (``web/src/features/console``) declara «SIN LIVE» pasada
``FEATURES_STALE_MS`` — y ese silencio es honesto, porque de este topic sí se
espera una muestra por segundo. Tumbar el socket del SOC entero (lo que sí hace
el hub cuando pierde una invalidación de incidente) sería desproporcionado para
un tropiezo del sismograma.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from sqlalchemy import text

from takab_api.audit import LATERAL_LOCK_TIMEOUT
from takab_api.db.session import SessionCtx, get_tenant_conn
from takab_api.ws import protocol as p

if TYPE_CHECKING:
    from takab_api.ws.hub import Hub, Subscriber

logger = logging.getLogger("takab_api.ws")

_POLL_INTERVAL_S = 1.0
_WINDOW_S = 2

# Ventana corta reciente del sitio: la API lee SOLO por la vista segura.
_SQL_FEATURES = text(
    "SELECT ts, channel, pga_g, pgv_cms, rms, stalta, energy, clipping "
    "FROM waveform_features_1s_secure "
    "WHERE site_id = CAST(:site AS uuid) "
    "AND ts > now() - make_interval(secs => :win) ORDER BY ts"
)


async def poll_features(hub: Hub, sub: Subscriber, site_id: str) -> None:
    """Bucle 1 Hz: consulta la vista segura y empuja un ``features`` frame."""
    ctx = SessionCtx.from_claims(sub.claims)
    while True:
        try:
            async with get_tenant_conn(ctx) as conn:
                # [T-2.121] Misma política que el hub y que las laterales de
                # auditoría (`audit.LATERAL_LOCK_TIMEOUT`): una sola constante.
                await conn.execute(LATERAL_LOCK_TIMEOUT)
                rows = (
                    (await conn.execute(_SQL_FEATURES, {"site": site_id, "win": _WINDOW_S}))
                    .mappings()
                    .all()
                )
            if rows:
                frame = p.FeaturesFrame(
                    site_id=site_id,
                    rows=[p.FeatureRow(**dict(r)) for r in rows],
                ).model_dump(mode="json")
                await hub._send(sub, frame)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - un ciclo fallido no mata el poller
            logger.exception("ws: poller de features falló")
        await asyncio.sleep(_POLL_INTERVAL_S)
