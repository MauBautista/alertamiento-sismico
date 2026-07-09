"""Puente cola→DB de la demo: el ``SqsConsumer`` REAL sobre el spool.

No es un handler escrito a mano. Es exactamente el worker de ingesta de producción
(``python -m takab_api.ingest``): mismo despacho por topic, misma validación contra
``shared/schemas/``, misma resolución de identidad por ``meta_principal`` contra el
registro, mismos handlers, misma DLQ, mismo commit por mensaje. Lo único que cambia
es el cliente de cola: ``SpoolSqsClient`` en vez de boto3 contra SQS.

Esto importa para la honestidad de la demo: si el edge publica un payload que la
IoT Rule/el schema rechazarían, aquí también aterriza en la DLQ.
"""

from __future__ import annotations

import logging
import threading
from functools import partial
from pathlib import Path

import psycopg
from demo.spool import SpoolSqsClient

from takab_api.db import pool
from takab_api.ingest.consumer import SqsConsumer
from takab_api.ingest.handlers import HANDLERS
from takab_api.ingest.registry import Registry
from takab_api.settings import Settings

log = logging.getLogger("demo.bridge")

# URLs ficticias: `SpoolSqsClient` las ignora, pero el consumer las registra en
# sus métricas y en la DLQ. Se nombran para que los logs sean legibles.
QUEUE_URL = "demo://q-events"
DLQ_URL = "demo://q-events-dlq"


def ingest_conn_factory(dsn: str):  # noqa: ANN201 — psycopg.Connection
    """Conexión que escala a ``takab_ingest`` (BYPASSRLS), como el worker real.

    El rol es NOLOGIN en dev, así que se entra como superusuario y se escala con
    ``SET ROLE`` (mismo patrón que ``api/scripts/fake_ingest.py`` y el conftest).
    El ``COMMIT`` fija el rol para el resto de la sesión: un ``ROLLBACK`` posterior
    del consumer (mensaje malo) ya no puede devolvernos al superusuario.
    """

    def _connect() -> psycopg.Connection:
        conn = pool.connect(dsn)
        conn.execute("SET ROLE takab_ingest")
        conn.commit()
        return conn

    return _connect


class Bridge:
    """Corre el consumer real en un hilo, sobre los spools de los gabinetes."""

    def __init__(self, spool_dirs: list[Path], dlq_dir: Path, dsn: str) -> None:
        settings = Settings(database_url=dsn)
        self.sqs = SpoolSqsClient(list(spool_dirs), dlq_dir)
        conn_factory = ingest_conn_factory(dsn)
        registry = Registry(partial(conn_factory), ttl_s=settings.registry_ttl_s)
        self.consumer = SqsConsumer(
            QUEUE_URL,
            DLQ_URL,
            HANDLERS,
            registry,
            conn_factory,
            settings,
            per_message_commit=True,  # cola de eventos (G5)
            sqs_client=self.sqs,
            # >0 para que `receive_message` ceda CPU cuando la cola está vacía;
            # el spool no hace long-polling real, sólo una espera corta.
            wait_time_s=1,
        )
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Arranca el bucle del consumer REAL (`run()`, con su cierre gracioso)."""
        self._thread = threading.Thread(target=self.consumer.run, daemon=True, name="demo-bridge")
        self._thread.start()

    def drain(self, timeout_s: float = 20.0) -> bool:
        """Espera a que la cola quede vacía. False si expira (algo se atoró)."""
        clock = threading.Event()
        waited = 0.0
        while waited < timeout_s:
            if self.sqs.pending_count == 0:
                clock.wait(0.4)  # margen para el batch en vuelo y su commit
                if self.sqs.pending_count == 0:
                    return True
            clock.wait(0.1)
            waited += 0.1
        return False

    def stop(self) -> None:
        self.consumer.stop()
        if self._thread is not None:
            self._thread.join(timeout=5)

    @property
    def dlq_count(self) -> int:
        return self.sqs.dlq_count
