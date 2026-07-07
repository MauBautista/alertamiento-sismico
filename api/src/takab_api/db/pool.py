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


def connect(dsn: str) -> psycopg.Connection:
    """Conexión transaccional con filas dict. Acepta DSN estilo SQLAlchemy."""
    dsn = dsn.replace("postgresql+psycopg://", "postgresql://", 1)
    return psycopg.connect(dsn, autocommit=False, row_factory=dict_row)


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
