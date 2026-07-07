"""Worker del orquestador de notificaciones (T-1.21 · B6).

Bucle LISTEN ``takab_live`` (incidentes nuevos) + ``takab_failopen`` (señal de
fail-open de T-1.19) + poll periódico de respaldo; cada wake ⇒
``run_notify_pass``. Mismo contrato de resiliencia que el incident engine:
reconecta con backoff indefinidamente; su caída JAMÁS afecta la actuación
local del edge (la sirena en sitio es el canal primario de vida — §5.6).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING

import psycopg

from takab_api.db import pool
from takab_api.notify.orchestrator import run_notify_pass
from takab_api.notify.providers import NotifyProvider, build_providers

if TYPE_CHECKING:
    from takab_api.settings import Settings

logger = logging.getLogger("takab_api.notify")

_RECONNECT_BACKOFF_S = 1.0


class NotifyWorker:
    """Orquestador en bucle. Firma espejo de ``IncidentEngine``:
    ``NotifyWorker(conn_factory, settings, *, poll_s=2.0, providers=None)``."""

    def __init__(
        self,
        conn_factory: Callable[[], psycopg.Connection],
        settings: Settings,
        *,
        poll_s: float = 2.0,
        providers: dict[str, NotifyProvider] | None = None,
    ) -> None:
        self._conn_factory = conn_factory
        self._settings = settings
        self._poll_s = poll_s
        self._providers = providers if providers is not None else build_providers(settings)
        self._stop = threading.Event()

    def run(self) -> None:
        """Escucha y despacha hasta ``stop()``; reconecta con backoff."""
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
                    run_notify_pass(work_conn, self._settings, self._providers)
                except psycopg.OperationalError:
                    logger.exception("notify: DB no disponible; reconecta")
                    self._safe_close(work_conn)
                    self._safe_close(listen_conn)
                    work_conn = None
                    listen_conn = None
                    self._stop.wait(_RECONNECT_BACKOFF_S)
                except Exception:
                    logger.exception("notify: error inesperado en el ciclo")
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
        """Cierre gracioso (idempotente, seguro desde señales)."""
        self._stop.set()

    def _drain_notifies(self, listen_conn: psycopg.Connection) -> None:
        """Espera hasta ``poll_s`` (o el primer NOTIFY); el pass decide el trabajo
        real por idempotencia, así que un NOTIFY perdido lo cubre el poll."""
        for _note in listen_conn.notifies(timeout=self._poll_s, stop_after=1):
            pass

    def _connect_listen(self) -> psycopg.Connection:
        conn = pool.with_retry(self._conn_factory)
        conn.autocommit = True
        conn.execute("LISTEN takab_live")
        conn.execute("LISTEN takab_failopen")
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
