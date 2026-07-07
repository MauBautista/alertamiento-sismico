"""Entrypoint del motor de incidentes: ``python -m takab_api.incident``.

Conecta como ``takab_ingest`` (BYPASSRLS): la DSN llega por env
``TAKAB_API_DATABASE_URL`` — en cloud se inyecta con las credenciales de
``takab_ingest`` de Secrets Manager. SIGTERM/SIGINT ⇒ cierre gracioso: el bucle
sale tras el wake en curso. Cloud-only y post-hoc: nunca bloquea la actuación
local del edge.

Operación (plan §C.1): corre CO-LOCADO en el mismo EC2 que los workers de
ingesta, desde la MISMA imagen (ver ``api/Dockerfile`` — "un build, muchos
commands"); sólo cambia el command del contenedor::

    python -m takab_api.incident [--poll-interval 5.0] [--lookback 300.0]

``--lookback`` (s) DEBE exceder el spread de arribos inter-ciudad (~17 s a
110 km) + latencia; ``--poll-interval`` es la cadencia del poll de respaldo por
si se pierde un NOTIFY de ``takab_live``.
"""

from __future__ import annotations

import argparse
import logging
import signal
from functools import partial

import psycopg

from takab_api.db import pool
from takab_api.incident.engine import IncidentEngine
from takab_api.settings import Settings

log = logging.getLogger("takab_api.incident")


def build_engine(settings: Settings, *, poll_s: float, lookback_s: float) -> IncidentEngine:
    conn_factory: partial[psycopg.Connection] = partial(pool.connect, settings.database_url)
    return IncidentEngine(conn_factory, settings, poll_s=poll_s, lookback_s=lookback_s)


def install_signal_handlers(engine: IncidentEngine) -> None:
    """SIGTERM/SIGINT → ``engine.stop()`` (cierre gracioso)."""

    def _stop(signum: int, _frame: object) -> None:
        log.info("señal %s recibida; cierre gracioso", signal.Signals(signum).name)
        engine.stop()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="takab_api.incident", description=__doc__)
    parser.add_argument("--poll-interval", type=float, default=5.0, dest="poll_s")
    parser.add_argument("--lookback", type=float, default=300.0, dest="lookback_s")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    engine = build_engine(Settings(), poll_s=args.poll_s, lookback_s=args.lookback_s)
    install_signal_handlers(engine)
    log.info("motor de incidentes iniciado (poll=%ss lookback=%ss)", args.poll_s, args.lookback_s)
    engine.run()


if __name__ == "__main__":
    main()
