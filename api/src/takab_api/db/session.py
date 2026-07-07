"""Sesión de tenant async: rol + GUCs RLS por transacción (T-1.18).

Espeja ``api/tests/conftest.py::use`` para el stack async: ``SET LOCAL ROLE
takab_app`` (allowlist → sin inyección de identificador) + tres
``set_config('app.*', :v, true)`` PARAMETRIZADOS. Todo vive en la transacción:
los GUCs son locales (``is_local=true``) y el rol es ``SET LOCAL``, así que al
hacer commit/rollback la conexión vuelve limpia al pool y una request posterior
que la reutilice NO hereda el contexto de tenant (fuga cero).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.db.engine import get_engine

# Allowlist de roles de conexión (espejo de conftest.DB_ROLES): el nombre de rol
# es un identificador y no puede ir como bind param, así que se restringe aquí.
DB_ROLES = frozenset({"takab_app", "takab_ingest", "takab_migrator"})

_SET_TENANT = text("SELECT set_config('app.tenant_id', :v, true)")
_SET_ROLE = text("SELECT set_config('app.role', :v, true)")
_SET_USER = text("SELECT set_config('app.user_id', :v, true)")


@dataclass(frozen=True, slots=True)
class SessionCtx:
    """Contexto mínimo por request para RLS (desacoplado de ``auth.claims``)."""

    tenant_id: str
    role: str
    user_id: str

    @classmethod
    def from_claims(cls, claims: object) -> SessionCtx:
        """Puente desde un objeto de claims con ``.tenant_id``/``.role``/``.sub``."""
        return cls(
            tenant_id=getattr(claims, "tenant_id", "") or "",
            role=getattr(claims, "role", "") or "",
            user_id=getattr(claims, "sub", "") or "",
        )


@asynccontextmanager
async def get_tenant_conn(
    ctx: SessionCtx,
    *,
    set_session_role: str | None = "takab_app",
) -> AsyncIterator[AsyncConnection]:
    """Conexión async dentro de una txn con rol de conexión + GUCs RLS fijados.

    Commit al salir sin excepción; rollback ante cualquier error. Uso::

        async with get_tenant_conn(ctx) as conn:
            await conn.execute(...)

    ``set_session_role`` debe estar en ``DB_ROLES`` (o ``None`` para no cambiar
    de rol: producción ya conecta como ``takab_app``).
    """
    if set_session_role is not None and set_session_role not in DB_ROLES:
        raise ValueError(f"rol no permitido: {set_session_role!r}")
    engine = get_engine()
    async with engine.connect() as conn, conn.begin():
        if set_session_role is not None:
            await conn.execute(text(f'SET LOCAL ROLE "{set_session_role}"'))
        await conn.execute(_SET_TENANT, {"v": ctx.tenant_id})
        await conn.execute(_SET_ROLE, {"v": ctx.role})
        await conn.execute(_SET_USER, {"v": ctx.user_id})
        yield conn


@asynccontextmanager
async def get_healthcheck_conn() -> AsyncIterator[AsyncConnection]:
    """Conexión sin rol ni GUCs para liveness/readiness (``SELECT 1``)."""
    engine = get_engine()
    async with engine.connect() as conn:
        yield conn
