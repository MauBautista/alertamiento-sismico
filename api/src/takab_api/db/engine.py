"""Engine SQLAlchemy async sobre psycopg3 — plano de datos de la API (T-1.18).

La API NUNCA conecta como dueño de tablas: en producción el DSN autentica como
``takab_app`` (rol sin BYPASSRLS y que no es dueño) para que
``FORCE ROW LEVEL SECURITY`` la cubra. En dev/tests el DSN es el super ``takab``
y el helper de sesión hace ``SET LOCAL ROLE takab_app`` (espejo del conftest
sync) ANTES de fijar los GUCs, para ejercitar RLS igual que en producción.
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from takab_api.settings import Settings


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """Engine async cacheado por proceso.

    DSN desde ``settings.database_url`` (``postgresql+psycopg://…`` → psycopg3
    async). Pool pequeño con ``pre_ping`` para reciclar conexiones caídas.
    """
    settings = Settings()
    return create_async_engine(
        settings.database_url,
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,
    )
