"""Propagación de GUCs por request y fuga cero entre tenants (regla de oro 5).

Una ruta de prueba lee ``current_setting('app.*')`` dentro de la sesión y hace una
consulta real a ``incidents``: el tenant A ve su incidente y NUNCA el del tenant B.
También se verifica la traza del acuse directo y que un acuse cruzado da 404.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

import auth_utils as au
from takab_api.auth.deps import get_session
from takab_api.db.engine import get_engine
from takab_api.main import create_app


def _probe_app() -> FastAPI:
    app = create_app()

    @app.get("/_probe")
    async def probe(conn: AsyncConnection = Depends(get_session)) -> dict[str, object]:
        tenant = (await conn.execute(text("SELECT current_setting('app.tenant_id')"))).scalar_one()
        role = (await conn.execute(text("SELECT current_setting('app.role')"))).scalar_one()
        user = (await conn.execute(text("SELECT current_setting('app.user_id')"))).scalar_one()
        ids = (
            (await conn.execute(text("SELECT incident_id FROM incidents ORDER BY incident_id")))
            .scalars()
            .all()
        )
        return {
            "tenant_id": tenant,
            "role": role,
            "user_id": user,
            "incidents": [str(i) for i in ids],
        }

    return app


async def test_gucs_propagate_and_no_cross_tenant_read(make_incident) -> None:
    ia = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    ib = await make_incident(au.DB_TENANT_PRIV2, au.DB_SITE_PRIV2)
    app = _probe_app()
    async with au.client_for(app) as client:
        tok_a = au.make_token(
            "soc_operator", tenant=au.DB_TENANT_PRIV, site_scope="*", user_id="ua"
        )
        body_a = (await client.get("/_probe", headers=au.bearer(tok_a))).json()
        assert body_a["tenant_id"] == au.DB_TENANT_PRIV
        assert body_a["role"] == "soc_operator"
        assert body_a["user_id"] == "ua"
        assert ia in body_a["incidents"]
        assert ib not in body_a["incidents"], "tenant A no puede ver incidentes de B"

        tok_b = au.make_token(
            "soc_operator", tenant=au.DB_TENANT_PRIV2, site_scope="*", user_id="ub"
        )
        body_b = (await client.get("/_probe", headers=au.bearer(tok_b))).json()
        assert body_b["tenant_id"] == au.DB_TENANT_PRIV2
        assert ib in body_b["incidents"]
        assert ia not in body_b["incidents"], "tenant B no puede ver incidentes de A"


async def test_tenant_ack_writes_action_and_audit(client, make_incident) -> None:
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    user = "dddddddd-0000-0000-0000-000000000001"
    token = au.make_token("tenant_admin", tenant=au.DB_TENANT_PRIV, site_scope="*", user_id=user)

    resp = await client.post(f"/incidents/{iid}/ack", headers=au.bearer(token))
    assert resp.status_code == 200, resp.text

    engine = get_engine()
    async with engine.connect() as conn:
        state = (
            await conn.execute(
                text("SELECT state FROM incidents WHERE incident_id = :i"), {"i": iid}
            )
        ).scalar_one()
        actions = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM incident_actions "
                    "WHERE incident_id = :i AND kind = 'ack' AND actor = :a"
                ),
                {"i": iid, "a": f"user:{user}"},
            )
        ).scalar_one()
        audit = (
            await conn.execute(
                text("SELECT count(*) FROM audit_log WHERE verb = 'ack' AND object = :o"),
                {"o": f"incident:{iid}"},
            )
        ).scalar_one()
    assert state == "acked"
    assert actions == 1
    assert audit == 1


async def test_cross_tenant_ack_is_404(client, make_incident) -> None:
    ib = await make_incident(au.DB_TENANT_PRIV2, au.DB_SITE_PRIV2)
    token = au.make_token("soc_operator", tenant=au.DB_TENANT_PRIV, site_scope="*", user_id="ua")

    resp = await client.post(f"/incidents/{ib}/ack", headers=au.bearer(token))
    assert resp.status_code == 404, "un usuario de A no puede acusar (ni ver) un incidente de B"


async def test_double_tenant_ack_is_409(client, make_incident) -> None:
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    token = au.make_token("soc_operator", tenant=au.DB_TENANT_PRIV, site_scope="*", user_id="ua")

    first = await client.post(f"/incidents/{iid}/ack", headers=au.bearer(token))
    assert first.status_code == 200
    second = await client.post(f"/incidents/{iid}/ack", headers=au.bearer(token))
    assert second.status_code == 409
