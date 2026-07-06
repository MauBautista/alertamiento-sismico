"""Entorno Alembic para TAKAB.

La URL se toma de la variable de entorno ``DATABASE_URL`` (sin secretos en git,
regla de oro 6). Por defecto apunta al Postgres local del ``docker-compose.yml``.
No usamos autogenerate: la migración inicial aplica ``db/schema.sql`` verbatim.
"""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config

DEFAULT_URL = "postgresql+psycopg://takab:takab_dev@localhost:5432/takab"
config.set_main_option("sqlalchemy.url", os.environ.get("DATABASE_URL", DEFAULT_URL))

# Sin metadata declarativa: el DDL es la fuente de verdad (db/schema.sql).
target_metadata = None


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
