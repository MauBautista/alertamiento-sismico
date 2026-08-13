"""Entrypoint del worker de ingesta: ``python -m takab_api.ingest --queue …``.

Conecta como ``takab_ingest`` (BYPASSRLS): la DSN llega por env
``TAKAB_API_DATABASE_URL`` — en dev/cloud se inyecta con las credenciales de
``takab_ingest`` de Secrets Manager. SIGTERM/SIGINT ⇒ cierre gracioso: se
termina el batch en curso (commit incluido) y se sale.
"""

from __future__ import annotations

import argparse
import logging
import signal
from functools import partial

import psycopg

from takab_api.db import pool
from takab_api.db.session import WORKER_LOCK_TIMEOUT_MS
from takab_api.ingest.consumer import SqsConsumer
from takab_api.ingest.registry import Registry
from takab_api.settings import Settings

log = logging.getLogger("takab_api.ingest")


def build_consumer(queue: str, settings: Settings) -> SqsConsumer:
    """Arma el consumer de ``events`` (commit por mensaje, G5) o ``telemetry``
    (commit por batch)."""
    # Import aquí: el router real vive en handlers.py (fase B en paralelo).
    from takab_api.ingest.handlers import HANDLERS

    per_message_commit = queue == "events"
    if per_message_commit:
        queue_url, dlq_url = settings.queue_url_events, settings.dlq_url_events
    else:
        queue_url, dlq_url = settings.queue_url_telemetry, settings.dlq_url_telemetry
    if not queue_url or not dlq_url:
        raise SystemExit(
            f"faltan URLs de cola/DLQ para {queue!r} (TAKAB_API_QUEUE_URL_* / TAKAB_API_DLQ_URL_*)"
        )

    # [T-2.132] El tope de espera por lock del worker. Va aquí y no en
    # `pool.connect` por defecto porque este worker es el ÚNICO que tiene detrás
    # la política de reintento en el sitio que lo hace seguro: sin ella, el tope
    # convierte cada bloqueo en una recepción de SQS quemada y, a la quinta, un
    # mensaje válido en la DLQ (medido en T-2.130). El número sale de
    # `db/session.py`, donde vive la política entera.
    conn_factory: partial[psycopg.Connection] = partial(
        pool.connect, settings.database_url, lock_timeout_ms=WORKER_LOCK_TIMEOUT_MS
    )
    registry = Registry(conn_factory, ttl_s=settings.registry_ttl_s)
    return SqsConsumer(
        queue_url,
        dlq_url,
        HANDLERS,
        registry,
        conn_factory,
        settings,
        per_message_commit,
    )


def install_signal_handlers(consumer: SqsConsumer) -> None:
    """SIGTERM/SIGINT → ``consumer.stop()`` (termina el batch en curso y sale)."""

    def _stop(signum: int, _frame: object) -> None:
        log.info("señal %s recibida; cierre gracioso", signal.Signals(signum).name)
        consumer.stop()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="takab_api.ingest", description=__doc__)
    parser.add_argument("--queue", choices=("events", "telemetry"), required=True)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    consumer = build_consumer(args.queue, Settings())
    install_signal_handlers(consumer)
    log.info("worker de ingesta iniciado (queue=%s)", args.queue)
    consumer.run()


if __name__ == "__main__":
    main()
