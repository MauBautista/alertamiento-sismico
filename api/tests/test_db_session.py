"""Capa DB async (T-1.18 · A2): propagación de GUCs y fuga cero entre tenants.

El stack async coexiste con el conftest sync (psycopg): estos tests conectan
como el super ``takab`` del DSN y ``get_tenant_conn`` hace ``SET LOCAL ROLE
takab_app`` para que RLS aplique, igual que en producción (donde el DSN ya es
``takab_app``). Cada test crea/dispone su propio engine dentro de su event loop
para evitar reutilizar conexiones entre loops.
"""

from __future__ import annotations

import asyncio
import os

import pytest
from sqlalchemy import text

from takab_api.db.engine import get_engine
from takab_api.db.session import SessionCtx, get_tenant_conn

# UUIDs propios (distintos del seed del conftest) → aislamiento de este módulo.
T1 = "d1000000-0000-0000-0000-000000000001"
T2 = "d2000000-0000-0000-0000-000000000002"
S1 = "51000000-0000-0000-0000-000000000001"
S2 = "52000000-0000-0000-0000-000000000002"

_GEOM = "ST_SetSRID(ST_MakePoint(-99.13,19.43),4326)::geography"


@pytest.fixture(autouse=True)
async def _engine_lifecycle(monkeypatch):
    """Engine fresco por test en su propio loop; se dispone al terminar.

    Alinea ``TAKAB_API_DATABASE_URL`` (que lee ``Settings``) con la ``DATABASE_URL``
    que el conftest usa para migrar, de modo que el engine apunte a la misma DB.
    ``monkeypatch`` revierte el env al terminar → no contamina otros tests.
    """
    dsn = os.environ.get("DATABASE_URL")
    if dsn:
        monkeypatch.setenv("TAKAB_API_DATABASE_URL", dsn)
    get_engine.cache_clear()
    yield
    await get_engine().dispose()
    get_engine.cache_clear()


@pytest.fixture
async def seeded_db():
    """Siembra idempotente (super, bypass RLS) de 2 tenants privados con 1 sitio."""
    engine = get_engine()
    async with engine.begin() as conn:
        for tid, code in ((T1, "DBT1"), (T2, "DBT2")):
            await conn.execute(
                text(
                    "INSERT INTO tenants (tenant_id, code, name, visibility) "
                    "VALUES (:id, :code, 'DB async test', 'private') "
                    "ON CONFLICT (tenant_id) DO NOTHING"
                ),
                {"id": tid, "code": code},
            )
        for sid, tid, code in ((S1, T1, "S1"), (S2, T2, "S2")):
            await conn.execute(
                text(
                    "INSERT INTO sites (site_id, tenant_id, code, name, geom) "
                    f"VALUES (:sid, :tid, :code, 'Sitio', {_GEOM}) "
                    "ON CONFLICT (site_id) DO NOTHING"
                ),
                {"sid": sid, "tid": tid, "code": code},
            )


def _ctx(tenant: str) -> SessionCtx:
    return SessionCtx(tenant_id=tenant, role="soc_operator", user_id=f"user-{tenant}")


async def test_guc_set_inside_txn():
    """(a) Dentro de get_tenant_conn los GUCs valen lo seteado."""
    async with get_tenant_conn(_ctx(T1)) as conn:
        tenant = (await conn.execute(text("SELECT current_setting('app.tenant_id')"))).scalar_one()
        role = (await conn.execute(text("SELECT current_setting('app.role')"))).scalar_one()
        user = (await conn.execute(text("SELECT current_setting('app.user_id')"))).scalar_one()
    assert tenant == T1
    assert role == "soc_operator"
    assert user == f"user-{T1}"


async def test_no_cross_tenant_leak(seeded_db):
    """(b) Fuga cero: el tenant A no ve sitios del tenant B."""
    async with get_tenant_conn(_ctx(T1)) as conn:
        rows = (await conn.execute(text("SELECT tenant_id FROM sites"))).scalars().all()
    seen = {str(r) for r in rows}
    assert seen == {T1}
    assert T2 not in seen


async def test_concurrent_sessions_do_not_bleed(seeded_db):
    """(c) TEST ESTRELLA: get_tenant_conn(A) y (B) intercalados no se contaminan."""

    async def fetch(tenant: str) -> tuple[str, set[str], str]:
        async with get_tenant_conn(_ctx(tenant)) as conn:
            await asyncio.sleep(0.05)  # fuerza el intercalado del gather
            rows = (await conn.execute(text("SELECT tenant_id FROM sites"))).scalars().all()
            await asyncio.sleep(0.05)
            guc = (await conn.execute(text("SELECT current_setting('app.tenant_id')"))).scalar_one()
            return tenant, {str(r) for r in rows}, guc

    results = await asyncio.gather(fetch(T1), fetch(T2), fetch(T1), fetch(T2))
    for tenant, sites, guc in results:
        assert guc == tenant
        assert sites == {tenant}


async def test_guc_does_not_leak_across_txn(seeded_db):
    """(d) is_local: nueva txn sin setear GUC → RLS default-deny (0 sitios)."""
    async with get_tenant_conn(_ctx(T1)) as conn:
        assert (
            await conn.execute(text("SELECT current_setting('app.tenant_id')"))
        ).scalar_one() == T1

    engine = get_engine()
    async with engine.connect() as conn, conn.begin():
        await conn.execute(text('SET LOCAL ROLE "takab_app"'))
        rows = (await conn.execute(text("SELECT tenant_id FROM sites"))).scalars().all()
    assert rows == []


async def test_rollback_on_error():
    """Ante excepción dentro del bloque, la txn hace rollback (no commit)."""
    with pytest.raises(RuntimeError):
        async with get_tenant_conn(_ctx(T1)) as conn:
            await conn.execute(text("SELECT 1"))
            raise RuntimeError("boom")


async def test_role_allowlist_rejects_injection():
    """set_session_role fuera de la allowlist no abre conexión."""
    with pytest.raises(ValueError, match="rol no permitido"):
        async with get_tenant_conn(_ctx(T1), set_session_role="takab_app; DROP"):
            pass


def test_session_ctx_from_claims():
    """SessionCtx.from_claims mapea .sub → user_id sin acoplarse a auth."""

    class _Claims:
        tenant_id = T1
        role = "inspector"
        sub = "cognito-sub-123"

    ctx = SessionCtx.from_claims(_Claims())
    assert ctx == SessionCtx(tenant_id=T1, role="inspector", user_id="cognito-sub-123")
