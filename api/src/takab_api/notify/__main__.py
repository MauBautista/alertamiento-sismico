"""Entrypoint del orquestador de notificaciones: ``python -m takab_api.notify``.

Conecta como ``takab_ingest`` (BYPASSRLS); DSN por env ``TAKAB_API_DATABASE_URL``
(Secrets Manager en cloud). SIGTERM/SIGINT ⇒ cierre gracioso. Corre CO-LOCADO
con los demás workers desde la MISMA imagen (``api/Dockerfile`` — "un build,
muchos commands")::

    python -m takab_api.notify [--poll-interval 2.0]

Providers: SES real (sandbox) si ``TAKAB_API_NOTIFY_EMAIL_FROM`` está
configurado; WhatsApp/SMS simulados en dev (decisión ratificada plan maestro).
"""

from __future__ import annotations

import argparse
import logging
import signal
from functools import partial

import psycopg

from takab_api.db import pool
from takab_api.notify.worker import NotifyWorker
from takab_api.settings import Settings

log = logging.getLogger("takab_api.notify")


def build_worker(settings: Settings, *, poll_s: float) -> NotifyWorker:
    conn_factory: partial[psycopg.Connection] = partial(pool.connect, settings.database_url)
    return NotifyWorker(conn_factory, settings, poll_s=poll_s)


def install_signal_handlers(worker: NotifyWorker) -> None:
    """SIGTERM/SIGINT → ``worker.stop()`` (cierre gracioso)."""

    def _stop(signum: int, _frame: object) -> None:
        log.info("señal %s recibida; cierre gracioso", signal.Signals(signum).name)
        worker.stop()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="takab_api.notify", description=__doc__)
    parser.add_argument("--poll-interval", type=float, default=2.0, dest="poll_s")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    worker = build_worker(Settings(), poll_s=args.poll_s)
    install_signal_handlers(worker)
    log.info("orquestador de notificaciones iniciado (poll=%ss)", args.poll_s)
    worker.run()


if __name__ == "__main__":
    main()
