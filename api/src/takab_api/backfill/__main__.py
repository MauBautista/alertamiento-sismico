"""Entrypoint del worker de backfill: ``python -m takab_api.backfill``.

Conecta como ``takab_ingest`` (BYPASSRLS); DSN por env ``TAKAB_API_DATABASE_URL``.
SIGTERM/SIGINT ⇒ cierre gracioso. Corre CO-LOCADO con los demás workers desde
la MISMA imagen ("un build, muchos commands")::

    python -m takab_api.backfill

Requiere ``TAKAB_API_QUEUE_URL_BACKFILL`` / ``TAKAB_API_DLQ_URL_BACKFILL`` y
los buckets ``TAKAB_API_TRANSFER_BUCKET`` / ``TAKAB_API_EVIDENCE_BUCKET``.
"""

from __future__ import annotations

import argparse
import logging
import signal
from functools import partial

import psycopg

from takab_api.backfill.consumer import BackfillConsumer
from takab_api.db import pool
from takab_api.ingest.registry import Registry
from takab_api.settings import Settings

log = logging.getLogger("takab_api.backfill")


def build_consumer(settings: Settings) -> BackfillConsumer:
    if not settings.queue_url_backfill or not settings.dlq_url_backfill:
        raise SystemExit(
            "faltan URLs de cola/DLQ de backfill (TAKAB_API_QUEUE_URL_BACKFILL / "
            "TAKAB_API_DLQ_URL_BACKFILL)"
        )
    conn_factory: partial[psycopg.Connection] = partial(pool.connect, settings.database_url)
    registry = Registry(conn_factory, ttl_s=settings.registry_ttl_s)
    return BackfillConsumer(
        settings.queue_url_backfill,
        settings.dlq_url_backfill,
        registry,
        conn_factory,
        settings,
    )


def install_signal_handlers(consumer: BackfillConsumer) -> None:
    """SIGTERM/SIGINT → ``consumer.stop()`` (cierre gracioso)."""

    def _stop(signum: int, _frame: object) -> None:
        log.info("señal %s recibida; cierre gracioso", signal.Signals(signum).name)
        consumer.stop()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="takab_api.backfill", description=__doc__)
    parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    consumer = build_consumer(Settings())
    install_signal_handlers(consumer)
    log.info("worker de backfill iniciado")
    consumer.run()


if __name__ == "__main__":
    main()
