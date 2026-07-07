"""Acceso a base de datos (psycopg3 síncrono para workers de ingesta)."""

from takab_api.db.pool import connect, connect_with_retry, set_app_context, with_retry

__all__ = ["connect", "connect_with_retry", "set_app_context", "with_retry"]
