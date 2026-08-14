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
from takab_api.db.session import WORKER_LOCK_TIMEOUT_MS
from takab_api.ingest.registry import Registry
from takab_api.settings import Settings

log = logging.getLogger("takab_api.backfill")


def build_consumer(settings: Settings) -> BackfillConsumer:
    if not settings.queue_url_backfill or not settings.dlq_url_backfill:
        raise SystemExit(
            "faltan URLs de cola/DLQ de backfill (TAKAB_API_QUEUE_URL_BACKFILL / "
            "TAKAB_API_DLQ_URL_BACKFILL)"
        )
    # [T-2.139] El tope de espera por lock, y llega AHORA y no antes porque el
    # orden es la ficha: `T-2.132` midió que acotar la espera sin la política de
    # reintento debajo convierte cada bloqueo en una recepción de SQS quemada y,
    # a la quinta, un mensaje válido en la DLQ. Con `BACKFILL_TRANSIENT_POLICY`
    # ya puesta, ese 55P03 se reintenta en el sitio y ceder deja de costar datos.
    #
    # El número es el MISMO de la ingesta (`WORKER_LOCK_TIMEOUT_MS`) a propósito:
    # una sola política, no dos que se creen una. Y si algo, aquí cede con más
    # razón — la transacción que este worker sostiene mientras espera es la más
    # grande del sistema (el objeto entero, miles de filas), o sea el peor
    # extremo lejano posible de un ciclo que Postgres no detecta (`T-2.73.c`).
    #
    # SIN `statement_timeout_ms`, y eso está medido, no supuesto: ver el veredicto
    # de `T-2.139` en `db/session.py::WORKER_STATEMENT_TIMEOUT_MS`.
    conn_factory: partial[psycopg.Connection] = partial(
        pool.connect,
        settings.database_url,
        lock_timeout_ms=WORKER_LOCK_TIMEOUT_MS,
    )
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
