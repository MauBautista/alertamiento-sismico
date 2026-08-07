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
from functools import partial
from typing import TYPE_CHECKING

import psycopg

from takab_api.db import pool
from takab_api.notify.orchestrator import run_notify_pass
from takab_api.notify.providers import NotifyProvider, build_providers
from takab_api.ops.metrics import GhostGauge, count_ghosts, count_retired_alive

if TYPE_CHECKING:
    from takab_api.settings import Settings

logger = logging.getLogger("takab_api.notify")

_RECONNECT_BACKOFF_S = 1.0


def build_ghost_gauge(settings: Settings) -> GhostGauge:
    """Medidor de fantasmas listo para el bucle; inerte si no está habilitado.

    boto3 se importa DENTRO a propósito: con la métrica apagada —que es el caso
    en local y en los tests— este módulo no arrastra AWS ni ejecuta su resolución
    de credenciales al importarse.
    """
    client = None
    if settings.ops_metrics_enabled:
        try:
            import boto3

            client = boto3.client("cloudwatch", region_name=settings.aws_region)
        except Exception:
            # Sin cliente el medidor queda inerte y el worker sigue notificando:
            # perder una métrica de inventario no puede costar un aviso de sismo.
            logger.warning("no se pudo crear el cliente de CloudWatch", exc_info=True)
    # [B3] Las DOS cifras del mismo instante: la urgente (la que tiene alarma) y
    # la total (la que impide que acotar la alarma equivalga a borrar el estado).
    # El umbral de "vivo" es UNO —el de SIN ENLACE— para las dos.
    alive_s = settings.sin_enlace_min * 60.0
    return GhostGauge(
        namespace=settings.ops_metrics_namespace,
        every_s=settings.ops_metrics_interval_s,
        client=client,
        counter=partial(count_ghosts, alive_s=alive_s),
        total_counter=partial(count_retired_alive, alive_s=alive_s),
    )


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
        ghost_gauge: GhostGauge | None = None,
    ) -> None:
        self._conn_factory = conn_factory
        self._settings = settings
        self._poll_s = poll_s
        self._providers = providers if providers is not None else build_providers(settings)
        self._stop = threading.Event()
        # [T-2.60.a] La métrica del gabinete retirado que sigue latiendo viaja de
        # gorra en este bucle. Va aquí y no en un worker propio porque `notify` ya
        # despierta cada pocos segundos con una conexión caliente, y montar un
        # proceso entero para publicar un entero por minuto sería desproporcionado.
        # Se inyecta como colaborador (`ghost_gauge`) para poder probar el bucle
        # sin AWS delante.
        self._ghost_gauge = ghost_gauge if ghost_gauge is not None else build_ghost_gauge(settings)

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
                    # DESPUÉS del pase, nunca antes: avisar de un sismo manda
                    # sobre publicar una métrica de inventario. `maybe_publish`
                    # se estrangula sola y no lanza (contrato de GhostGauge).
                    self._ghost_gauge.maybe_publish(conn=work_conn)
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
