"""Entrypoint del config sync: ``python -m takab_api.commands``.

Conecta como ``takab_ingest`` (BYPASSRLS); DSN por env ``TAKAB_API_DATABASE_URL``.
SIGTERM/SIGINT ⇒ cierre gracioso. Corre CO-LOCADO con los demás workers desde
la MISMA imagen ("un build, muchos commands")::

    python -m takab_api.commands [--poll-interval 30.0]

La clave HMAC llega por ``TAKAB_API_COMMAND_HMAC_KEY`` (Secrets Manager en
cloud); sin clave el worker corre fail-closed (solo expira comandos).
"""

from __future__ import annotations

import argparse
import logging
import signal
from functools import partial

import psycopg

from takab_api.commands.worker import ConfigSyncWorker
from takab_api.db import pool
from takab_api.settings import Settings

log = logging.getLogger("takab_api.commands")


def build_worker(settings: Settings, *, poll_s: float) -> ConfigSyncWorker:
    conn_factory: partial[psycopg.Connection] = partial(pool.connect, settings.database_url)
    return ConfigSyncWorker(conn_factory, settings, poll_s=poll_s)


def install_signal_handlers(worker: ConfigSyncWorker) -> None:
    """SIGTERM/SIGINT → ``worker.stop()`` (cierre gracioso)."""

    def _stop(signum: int, _frame: object) -> None:
        log.info("señal %s recibida; cierre gracioso", signal.Signals(signum).name)
        worker.stop()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="takab_api.commands", description=__doc__)
    parser.add_argument("--poll-interval", type=float, default=30.0, dest="poll_s")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    worker = build_worker(Settings(), poll_s=args.poll_s)
    install_signal_handlers(worker)
    log.info("config sync iniciado (poll=%ss)", args.poll_s)
    worker.run()


if __name__ == "__main__":
    main()
