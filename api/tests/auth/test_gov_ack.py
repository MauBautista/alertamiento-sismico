"""POST /incidents/{id}/ack para gov_operator: vía SECURITY DEFINER, no fila directa.

gov_operator solo acusa incidentes de tenants gov_shared (open→acked + audit_log).
Sobre un tenant private → invisible (404). Doble-acuse → 409. Un rol sin acuse → 403.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

import auth_utils as au
from takab_api.db.engine import get_engine
from takab_api.db.session import SessionCtx, get_tenant_conn
from takab_api.routers.incidents_ack import _gov_ack

_USER = "abcabcab-0000-0000-0000-000000000001"


async def _incident_state(iid: str) -> str:
    engine = get_engine()
    async with engine.connect() as conn:
        return (
            await conn.execute(
                text("SELECT state FROM incidents WHERE incident_id = :i"), {"i": iid}
            )
        ).scalar_one()


async def test_gov_ack_gov_shared_success(client, make_incident) -> None:
    iid = await make_incident(au.DB_TENANT_GOV, au.DB_SITE_GOV)
    token = au.make_token("gov_operator", tenant=au.DB_TENANT_AGENCY, site_scope="*", user_id=_USER)

    resp = await client.post(f"/incidents/{iid}/ack", headers=au.bearer(token))
    assert resp.status_code == 200, resp.text
    assert resp.json()["state"] == "acked"

    assert await _incident_state(iid) == "acked"
    engine = get_engine()
    async with engine.connect() as conn:
        n = (
            await conn.execute(
                text("SELECT count(*) FROM audit_log WHERE verb = 'ack' AND object = :o"),
                {"o": f"incident:{iid}"},
            )
        ).scalar_one()
    assert n == 1, "gov_ack deja exactamente una traza en audit_log"


async def test_gov_ack_private_incident_is_404(client, make_incident) -> None:
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)  # tenant private
    token = au.make_token("gov_operator", tenant=au.DB_TENANT_AGENCY, site_scope="*", user_id=_USER)

    resp = await client.post(f"/incidents/{iid}/ack", headers=au.bearer(token))
    assert resp.status_code == 404
    assert await _incident_state(iid) == "open", "el incidente private no se toca"


async def test_gov_double_ack_is_409(client, make_incident) -> None:
    iid = await make_incident(au.DB_TENANT_GOV, au.DB_SITE_GOV)
    token = au.make_token("gov_operator", tenant=au.DB_TENANT_AGENCY, site_scope="*", user_id=_USER)

    first = await client.post(f"/incidents/{iid}/ack", headers=au.bearer(token))
    assert first.status_code == 200
    second = await client.post(f"/incidents/{iid}/ack", headers=au.bearer(token))
    assert second.status_code == 409


async def test_non_ack_role_forbidden(client, make_incident) -> None:
    iid = await make_incident(au.DB_TENANT_GOV, au.DB_SITE_GOV)
    token = au.make_token("inspector", tenant=au.DB_TENANT_AGENCY, site_scope="*", user_id=_USER)

    resp = await client.post(f"/incidents/{iid}/ack", headers=au.bearer(token))
    assert resp.status_code == 403
    assert await _incident_state(iid) == "open"


async def test_gov_ack_concurrent_double_ack_serializes(make_incident) -> None:
    """Dos gov acks concurrentes (dos txn abiertas a la vez) sobre el mismo incidente
    gov_shared: el candado de fila serializa → exactamente uno acusa y el otro cae en
    'transicion invalida' (=> 409 en la API), con una sola traza en audit_log (G6)."""
    iid = await make_incident(au.DB_TENANT_GOV, au.DB_SITE_GOV)
    ctx = SessionCtx(tenant_id=au.DB_TENANT_AGENCY, role="gov_operator", user_id=_USER)
    barrier = asyncio.Barrier(2)  # dispara ambos gov_ack con las dos txn ya abiertas

    async def _ack() -> str:
        async with get_tenant_conn(ctx) as conn:
            await barrier.wait()
            await conn.execute(text("SELECT gov_ack_incident(:i)"), {"i": iid})
        return "ok"

    results = await asyncio.gather(
        asyncio.create_task(_ack()), asyncio.create_task(_ack()), return_exceptions=True
    )
    oks = [r for r in results if r == "ok"]
    errs = [r for r in results if isinstance(r, BaseException)]
    assert len(oks) == 1 and len(errs) == 1, results
    assert "transicion" in str(getattr(errs[0], "orig", errs[0]))
    assert await _incident_state(iid) == "acked"

    engine = get_engine()
    async with engine.connect() as conn:
        n = (
            await conn.execute(
                text("SELECT count(*) FROM audit_log WHERE verb = 'ack' AND object = :o"),
                {"o": f"incident:{iid}"},
            )
        ).scalar_one()
    assert n == 1, "una sola traza pese al doble-acuse concurrente"


# --- Clasificación de errores de _gov_ack (sin DB): finding [baja] enmascaramiento ---


class _RaisingConn:
    """Conn de prueba cuyo ``execute`` siempre lanza el ``DBAPIError`` dado."""

    def __init__(self, err: DBAPIError) -> None:
        self._err = err

    async def execute(self, *_a: object, **_k: object) -> None:
        raise self._err


def _dbapi_error(message: str) -> DBAPIError:
    return DBAPIError("SELECT gov_ack_incident(:id)", {}, Exception(message))


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("gov_ack_incident: transicion invalida acked -> acked", 409),
        ("gov_ack_incident: incidente 00000000-... inexistente", 404),
        ("gov_ack_incident: tenant no es gov_shared", 404),
    ],
)
async def test_gov_ack_known_raises_map_to_4xx(message: str, expected: int) -> None:
    with pytest.raises(HTTPException) as excinfo:
        await _gov_ack(_RaisingConn(_dbapi_error(message)), uuid4())
    assert excinfo.value.status_code == expected


async def test_gov_ack_unknown_db_error_is_not_masked_as_404() -> None:
    """Un fallo real (timeout/deadlock) se relanza como 5xx, no se disfraza de 404."""
    err = _dbapi_error("canceling statement due to statement timeout")
    with pytest.raises(DBAPIError):
        await _gov_ack(_RaisingConn(err), uuid4())
