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

[T-2.129] **Y ahora además lo DICE.** Hasta esta ficha la degradación del strip
sólo se notaba por ausencia: ``DetailPanel`` declara «SIN LIVE» pasada
``FEATURES_STALE_MS``, que es honesto pero no distingue «el gabinete dejó de
mandar» de «la nube no puede leer lo que el gabinete mandó» — y esas dos cosas
se atienden en sitios distintos. El ciclo fallido declara ``live_health`` sobre
SU topic (``features:<site_id>``) y el ciclo bueno siguiente lo apaga, así que
aquí la recuperación se ve en ≤1 s sin sonda ninguna. El socket no se toca: era
desproporcionado tumbar el SOC entero por un tropiezo del sismograma, y con el
frame ya no hay que elegir entre callarse y cerrar.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from sqlalchemy import text

from takab_api.db.session import BACKGROUND_LOCK_TIMEOUT_MS, SessionCtx, get_tenant_conn
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
    topic = f"{p.TOPIC_FEATURES_PREFIX}{site_id}"
    while True:
        try:
            # [T-2.121] Misma política que el hub y que las laterales de
            # auditoría: una sola constante, declarada en `db/session.py`
            # (T-2.130) y pedida por parámetro.
            async with get_tenant_conn(ctx, lock_timeout_ms=BACKGROUND_LOCK_TIMEOUT_MS) as conn:
                rows = (
                    (await conn.execute(_SQL_FEATURES, {"site": site_id, "win": _WINDOW_S}))
                    .mappings()
                    .all()
                )
            # [T-2.129] El ciclo leyó: si venía de un tropiezo, se apaga el aviso.
            # Va antes de `if rows` a propósito — una ventana sin muestras es una
            # respuesta legítima de la base, no una degradación del canal.
            await hub._recuperar([sub], topic)
            if rows:
                frame = p.FeaturesFrame(
                    site_id=site_id,
                    rows=[p.FeatureRow(**dict(r)) for r in rows],
                ).model_dump(mode="json")
                await hub._send(sub, frame)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - un ciclo fallido no mata el poller
            logger.exception("ws: poller de features falló")
            # [T-2.129] Sin sonda: este bucle YA es la sonda (1 Hz). Se declara y
            # el ciclo siguiente que lea apaga el aviso solo.
            await hub._degradar([sub], topic, f"features: {exc.__class__.__name__}")
        await asyncio.sleep(_POLL_INTERVAL_S)
