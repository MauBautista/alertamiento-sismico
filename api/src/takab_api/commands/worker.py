"""Worker del config sync + expiración de comandos (T-1.23 · B9).

LISTEN ``takab_live`` (el trigger de 0006 emite ``t='rule_set'`` al activar o
cambiar un rule_set → publica ≤60 s) + poll de respaldo. Mismo contrato de
resiliencia que los demás workers: reconexión con backoff; su caída jamás toca
la actuación local del edge.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING

import psycopg

from takab_api.commands.publisher import CommandPublisher, IotDataPublisher
from takab_api.commands.sync import run_config_sync_pass
from takab_api.db import pool

if TYPE_CHECKING:
    from takab_api.settings import Settings

logger = logging.getLogger("takab_api.commands")

_RECONNECT_BACKOFF_S = 1.0


class ConfigSyncWorker:
    """Sync de config firmada en bucle (patrón de ``NotifyWorker``)."""

    def __init__(
        self,
        conn_factory: Callable[[], psycopg.Connection],
        settings: Settings,
        *,
        poll_s: float = 30.0,  # respaldo del NOTIFY: garantiza el SLA ≤60 s
        publisher: CommandPublisher | None = None,
    ) -> None:
        self._conn_factory = conn_factory
        self._settings = settings
        self._poll_s = poll_s
        self._publisher = publisher if publisher is not None else IotDataPublisher(settings)
        self._stop = threading.Event()

    def run(self) -> None:
        listen_conn: psycopg.Connection | None = None
        work_conn: psycopg.Connection | None = None
        try:
            while not self._stop.is_set():
                try:
                    if listen_conn is None or listen_conn.closed:
                        listen_conn = self._connect_listen()
                    self._drain_notifies(listen_conn)
                    if self._stop.is_set():
                        break
                    work_conn = self._ensure_work(work_conn)
                    run_config_sync_pass(work_conn, self._settings, self._publisher)
                except psycopg.OperationalError:
                    logger.exception("config sync: DB no disponible; reconecta")
                    self._safe_close(work_conn)
                    self._safe_close(listen_conn)
                    work_conn = None
                    listen_conn = None
                    self._stop.wait(_RECONNECT_BACKOFF_S)
                except Exception:
                    logger.exception("config sync: error inesperado en el ciclo")
                    if work_conn is not None:
                        try:
                            work_conn.rollback()
                        except psycopg.Error:
                            self._safe_close(work_conn)
                            work_conn = None
                    self._stop.wait(1.0)
        finally:
            self._safe_close(listen_conn)
            self._safe_close(work_conn)

    def stop(self) -> None:
        self._stop.set()

    def _drain_notifies(self, listen_conn: psycopg.Connection) -> None:
        for _note in listen_conn.notifies(timeout=self._poll_s, stop_after=1):
            pass

    def _connect_listen(self) -> psycopg.Connection:
        conn = pool.with_retry(self._conn_factory)
        conn.autocommit = True
        conn.execute("LISTEN takab_live")
        return conn

    def _ensure_work(self, work_conn: psycopg.Connection | None) -> psycopg.Connection:
        if work_conn is None or work_conn.closed:
            return pool.with_retry(self._conn_factory)
        return work_conn

    @staticmethod
    def _safe_close(conn: psycopg.Connection | None) -> None:
        if conn is not None:
            try:
                conn.close()
            except psycopg.Error:
                pass
