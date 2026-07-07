"""Flujo E2E de auth: token real (RS256 + StaticJWKS) → HTTP → RLS por tenant.

Ejercita la pila completa (get_claims → get_session → GUCs en la txn) sobre la
app montada, sin Cognito real. Cubre aislamiento cross-tenant, rechazo de firma
ajena, la vía de gobierno (SECURITY DEFINER) y el corte por rol en ruta web.
"""

from __future__ import annotations

from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine

_SOC_USER = "50c00000-0000-0000-0000-000000000001"
_GOV_USER = "60700000-0000-0000-0000-000000000001"


async def _incident_state(iid: str) -> str:
    engine = get_engine()
    async with engine.connect() as conn:
        return (
            await conn.execute(
                text("SELECT state FROM incidents WHERE incident_id = :i"), {"i": iid}
            )
        ).scalar_one()


async def _audit_count(iid: str) -> int:
    engine = get_engine()
    async with engine.connect() as conn:
        return (
            await conn.execute(
                text("SELECT count(*) FROM audit_log WHERE verb = 'ack' AND object = :o"),
                {"o": f"incident:{iid}"},
            )
        ).scalar_one()


async def test_soc_operator_only_sees_own_tenant(client, make_incident) -> None:
    """soc_operator del tenant A: /me refleja su identidad y solo acusa lo suyo."""
    own = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    foreign = await make_incident(au.DB_TENANT_PRIV2, au.DB_SITE_PRIV2)
    token = au.make_token(
        "soc_operator", tenant=au.DB_TENANT_PRIV, site_scope="*", user_id=_SOC_USER
    )

    me = await client.get("/me", headers=au.bearer(token))
    assert me.status_code == 200, me.text
    body = me.json()
    assert body["tenant_id"] == au.DB_TENANT_PRIV
    assert body["role"] == "soc_operator"
    assert "/console" in body["allowed_routes"]

    # Su propio incidente: acuse ok end-to-end (RLS lo deja pasar).
    mine = await client.post(f"/incidents/{own}/ack", headers=au.bearer(token))
    assert mine.status_code == 200, mine.text
    assert mine.json()["state"] == "acked"
    assert await _incident_state(own) == "acked"

    # Incidente de otro tenant: RLS lo oculta → 404, sin efecto lateral.
    other = await client.post(f"/incidents/{foreign}/ack", headers=au.bearer(token))
    assert other.status_code == 404
    assert await _incident_state(foreign) == "open", "el incidente ajeno no se toca"


async def test_foreign_key_signature_is_401(client, make_incident) -> None:
    """Token firmado con una llave que NO está en el JWKS → 401 (firma inválida)."""
    forged = au.badsig_token("soc_operator", tenant=au.DB_TENANT_PRIV, user_id=_SOC_USER)
    resp = await client.get("/me", headers=au.bearer(forged))
    assert resp.status_code == 401
    assert resp.headers.get("WWW-Authenticate") == "Bearer"


async def test_gov_operator_ack_gov_shared_e2e(client, make_incident) -> None:
    """gov_operator acusa un incidente gov_shared: 200 + exactamente una traza de audit."""
    iid = await make_incident(au.DB_TENANT_GOV, au.DB_SITE_GOV)
    token = au.make_token(
        "gov_operator", tenant=au.DB_TENANT_AGENCY, site_scope="*", user_id=_GOV_USER
    )

    resp = await client.post(f"/incidents/{iid}/ack", headers=au.bearer(token))
    assert resp.status_code == 200, resp.text
    assert resp.json()["state"] == "acked"
    assert await _incident_state(iid) == "acked"
    assert await _audit_count(iid) == 1


async def test_occupant_mobile_forbidden_on_web_route(client, make_incident) -> None:
    """occupant (móvil, sin acuse) → 403 en una ruta web protegida; no altera nada."""
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    token = au.make_token("occupant", tenant=au.DB_TENANT_PRIV, surface="mobile", site_scope="")

    resp = await client.post(f"/incidents/{iid}/ack", headers=au.bearer(token))
    assert resp.status_code == 403
    assert await _incident_state(iid) == "open"
