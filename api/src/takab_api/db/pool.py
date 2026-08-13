"""Conexión psycopg3 síncrona — workers de ingesta y consumidores futuros.

Los workers de ingesta conectan como ``takab_ingest`` (BYPASSRLS) y NO usan
``set_app_context``; ese helper espeja el contexto RLS que la API fija por
request (mismas claves que ``api/tests/conftest.py::use``).
"""

from __future__ import annotations

import time
from collections.abc import Callable

import psycopg
from psycopg.rows import dict_row


def connect(dsn: str, *, lock_timeout_ms: int | None = None) -> psycopg.Connection:
    """Conexión transaccional con filas dict. Acepta DSN estilo SQLAlchemy.

    [T-2.132] ``lock_timeout_ms`` fija el tope de espera por lock de la conexión.
    Tres decisiones que no se ven en la firma:

    · **El valor NO se escribe aquí.** Sale de ``db/session.py``
      (``WORKER_LOCK_TIMEOUT_MS``), donde ya viven el del request y el del
      segundo plano: la única forma de que dos políticas no deriven es que sean
      una.
    · **Va como parámetro de arranque** (``-c lock_timeout=…``), no como
      ``SET``. Un ``SET`` no local es transaccional: el ``rollback()`` que el
      worker hace en cada RETRY lo desharía, y la conexión se quedaría sin tope
      justo después del primer fallo — que es cuando hace falta.
    · **El defecto es ``None``, o sea el comportamiento de siempre.** Ponerlo
      por defecto se lo daría también a los workers de notify/commands/incident/
      backfill, que comparten esta fábrica y **no tienen** la política de
      reintento de ``ingest/consumer.py``: en ellos el tope convertiría un lock
      ocupado en recepciones de SQS quemadas. Se activa donde ya hay red debajo.
    """
    dsn = dsn.replace("postgresql+psycopg://", "postgresql://", 1)
    kwargs: dict[str, object] = {}
    if lock_timeout_ms is not None:
        # int() explícito: es lo que impide que esto sea una inyección de opciones
        # el día que el valor deje de ser una constante del módulo de política.
        kwargs["options"] = f"-c lock_timeout={int(lock_timeout_ms)}"
    return psycopg.connect(dsn, autocommit=False, row_factory=dict_row, **kwargs)  # type: ignore[call-overload]


def with_retry[T](
    fn: Callable[[], T],
    *,
    attempts: int = 5,
    base_delay_s: float = 0.5,
    max_delay_s: float = 8.0,
) -> T:
    """Reintenta ``fn`` ante fallo operacional con backoff exponencial acotado."""
    delay = base_delay_s
    last: psycopg.OperationalError | None = None
    for i in range(attempts):
        try:
            return fn()
        except psycopg.OperationalError as exc:
            last = exc
            if i < attempts - 1:
                time.sleep(delay)
                delay = min(delay * 2, max_delay_s)
    assert last is not None
    raise last


def connect_with_retry(dsn: str, **retry_kwargs: float) -> psycopg.Connection:
    """Reconexión simple: ``connect`` envuelto en ``with_retry``."""
    return with_retry(lambda: connect(dsn), **retry_kwargs)  # type: ignore[arg-type]


def set_app_context(
    conn: psycopg.Connection,
    tenant_id: str | None,
    role: str | None,
    user_id: str | None,
) -> None:
    """Fija las variables de sesión RLS (locales a la transacción)."""
    conn.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id or "",))
    conn.execute("SELECT set_config('app.role', %s, true)", (role or "",))
    conn.execute("SELECT set_config('app.user_id', %s, true)", (user_id or "",))
