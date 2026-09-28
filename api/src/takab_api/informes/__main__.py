"""Entrypoint del informe automático: ``python -m takab_api.informes`` (T-9.42 · D-48).

Conecta como ``takab_ingest`` (BYPASSRLS): la DSN llega por env
``TAKAB_API_DATABASE_URL`` (Secrets Manager en cloud, `db-ingest.env`), porque
escribe evidencia de TODOS los tenants — el mismo motivo que ``backfill``.
SIGTERM/SIGINT ⇒ cierre gracioso: el bucle sale tras la pasada en curso. Corre
CO-LOCADO con los demás workers desde la MISMA imagen::

    python -m takab_api.informes [--poll-interval 30.0]

Es un proceso APARTE del motor de incidentes a propósito: un PDF tarda segundos
(render, S3, y la IA si está encendida), y el bucle de aquél sostiene la actuación
comandada por el quórum. Lo que tarde un informe no puede retrasar un comando.
"""

from __future__ import annotations

import argparse
import logging
import signal
import threading
from collections.abc import Callable
from functools import partial

import psycopg

from takab_api.db import pool
from takab_api.informes.pasada import run_informes_pass
from takab_api.settings import Settings

log = logging.getLogger("takab_api.informes")


class InformesWorker:
    """Una pasada cada ``poll_s``; un fallo de la pasada se registra y no mata el bucle."""

    def __init__(
        self,
        conn_factory: Callable[[], psycopg.Connection],
        settings: Settings,
        *,
        poll_s: float,
    ) -> None:
        self._conn_factory = conn_factory
        self._settings = settings
        self._poll_s = poll_s
        self._stop = threading.Event()

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                run_informes_pass(self._conn_factory, self._settings)
            except Exception:  # noqa: BLE001 - la vuelta siguiente reintenta
                log.exception("informes: la pasada falló; se reintenta en la siguiente")
            self._stop.wait(self._poll_s)

    def stop(self) -> None:
        self._stop.set()


def build_worker(settings: Settings, *, poll_s: float) -> InformesWorker:
    return InformesWorker(partial(pool.connect, settings.database_url), settings, poll_s=poll_s)


def install_signal_handlers(worker: InformesWorker) -> None:
    """SIGTERM/SIGINT → ``worker.stop()`` (cierre gracioso)."""

    def _stop(signum: int, _frame: object) -> None:
        log.info("señal %s recibida; cierre gracioso", signal.Signals(signum).name)
        worker.stop()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="takab_api.informes", description=__doc__)
    parser.add_argument("--poll-interval", type=float, default=30.0, dest="poll_s")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    worker = build_worker(Settings(), poll_s=args.poll_s)
    install_signal_handlers(worker)
    log.info("informe automático iniciado (poll=%ss)", args.poll_s)
    worker.run()


if __name__ == "__main__":
    main()
