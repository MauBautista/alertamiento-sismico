"""GET /audit (T-1.57): lectura keyset del audit trail bajo RLS.

La ESCRITURA no se prueba aquí (el único escritor es ``takab_api.audit``,
contract-test single-writer); las filas se siembran como superusuario, igual
que el resto de fixtures de B2. La RLS ``audit_read`` existe desde el schema
consolidado: tenant propio o rol interno; ``tenant_id NULL`` (plataforma) solo
internos.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine
from takab_api.main import create_app
from takab_api.routers.audit import router as audit_router

T0 = datetime(2026, 7, 12, 10, 0, 0, tzinfo=UTC)
_USER = str(uuid.uuid4())


def _token(role: str = "tenant_admin", tenant: str = au.DB_TENANT_PRIV) -> dict[str, str]:
    return au.bearer(au.make_token(role, tenant=tenant, site_scope="*", user_id=_USER))


@pytest.fixture
def app() -> FastAPI:
    application = create_app()
    application.include_router(audit_router)
    return application


@pytest.fixture
def make_audit(base_data) -> Callable[..., Awaitable[None]]:
    """Siembra una fila de audit_log commiteada (superusuario, solo tests)."""

    async def _make(
        tenant_id: str | None,
        *,
        actor: str = "user:test",
        verb: str = "ack",
        obj: str = "incident:xyz",
        ts: datetime | None = None,
    ) -> None:
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO audit_log (ts, tenant_id, actor, verb, object, meta) "
                    "VALUES (:ts, CAST(:t AS uuid), :a, :v, :o, '{}'::jsonb)"
                ),
                {"ts": ts or datetime.now(UTC), "t": tenant_id, "a": actor, "v": verb, "o": obj},
            )

    return _make


async def _seed_mixed(make_audit) -> None:
    """3 filas del tenant A, 1 del B y 1 de PLATAFORMA (tenant NULL)."""
    for i, verb in enumerate(("ack", "export", "profile_update")):
        await make_audit(
            au.DB_TENANT_PRIV,
            actor="user:ana" if i < 2 else "user:beto",
            verb=verb,
            obj=f"incident:a{i}",
            ts=T0 + timedelta(minutes=i),
        )
    await make_audit(au.DB_TENANT_PRIV2, verb="ack", obj="incident:b0", ts=T0)
    await make_audit(None, actor="system:ingest", verb="ingest_reject", obj="feature_1s@t", ts=T0)


async def test_tenant_admin_ve_solo_su_tenant_y_nunca_plataforma(client, make_audit) -> None:
    await _seed_mixed(make_audit)
    resp = await client.get("/audit", headers=_token())
    assert resp.status_code == 200
    rows = resp.json()["items"]
    assert len(rows) == 3
    assert {r["tenant_id"] for r in rows} == {au.DB_TENANT_PRIV}  # ni B ni NULL


async def test_interno_ve_todo_incluidas_filas_de_plataforma(client, make_audit) -> None:
    await _seed_mixed(make_audit)
    resp = await client.get("/audit", headers=_token("takab_superadmin"))
    assert resp.status_code == 200
    rows = resp.json()["items"]
    assert len(rows) == 5
    assert any(r["tenant_id"] is None for r in rows)  # la fila de plataforma


@pytest.mark.parametrize("role", ["soc_operator", "inspector", "building_admin"])
async def test_rol_sin_read_audit_403(client, make_audit, role: str) -> None:
    await _seed_mixed(make_audit)
    resp = await client.get("/audit", headers=_token(role))
    assert resp.status_code == 403


async def test_sin_token_401(client, base_data) -> None:
    resp = await client.get("/audit")
    assert resp.status_code == 401


async def test_keyset_estable_ante_inserciones(client, make_audit) -> None:
    """Paginar con inserciones intercaladas: cero duplicados y cero huecos."""
    for i in range(5):
        await make_audit(au.DB_TENANT_PRIV, obj=f"incident:k{i}", ts=T0 + timedelta(seconds=i))
    first = await client.get("/audit", params={"limit": 2}, headers=_token())
    page1 = first.json()
    assert len(page1["items"]) == 2 and page1["next_cursor"]
    # Fila NUEVA más reciente: no debe colarse en las páginas siguientes.
    await make_audit(au.DB_TENANT_PRIV, obj="incident:new", ts=T0 + timedelta(minutes=5))
    second = await client.get(
        "/audit", params={"limit": 2, "cursor": page1["next_cursor"]}, headers=_token()
    )
    page2 = second.json()
    third = await client.get(
        "/audit", params={"limit": 2, "cursor": page2["next_cursor"]}, headers=_token()
    )
    seen = [r["audit_id"] for r in page1["items"] + page2["items"] + third.json()["items"]]
    assert len(seen) == len(set(seen)) == 5  # las 5 originales, sin duplicar
    objs = {r["object"] for r in page1["items"] + page2["items"] + third.json()["items"]}
    assert objs == {f"incident:k{i}" for i in range(5)}


async def test_filtros_actor_verb_prefijo_y_fechas(client, make_audit) -> None:
    await _seed_mixed(make_audit)
    by_actor = await client.get("/audit", params={"actor": "user:ana"}, headers=_token())
    assert {r["actor"] for r in by_actor.json()["items"]} == {"user:ana"}
    assert len(by_actor.json()["items"]) == 2

    by_verb = await client.get("/audit", params={"verb": "export"}, headers=_token())
    assert [r["verb"] for r in by_verb.json()["items"]] == ["export"]

    by_obj = await client.get("/audit", params={"object": "incident:a"}, headers=_token())
    assert len(by_obj.json()["items"]) == 3

    ranged = await client.get(
        "/audit",
        params={
            "from": (T0 + timedelta(minutes=1)).isoformat(),
            "to": (T0 + timedelta(minutes=2)).isoformat(),
        },
        headers=_token(),
    )
    assert [r["object"] for r in ranged.json()["items"]] == ["incident:a1"]  # [from, to)


async def test_cursor_corrupto_400_y_rango_invalido_422(client, make_audit) -> None:
    await _seed_mixed(make_audit)
    bad_cursor = await client.get("/audit", params={"cursor": "no-es-b64"}, headers=_token())
    assert bad_cursor.status_code == 400
    bad_range = await client.get(
        "/audit",
        params={"from": T0.isoformat(), "to": T0.isoformat()},
        headers=_token(),
    )
    assert bad_range.status_code == 422
