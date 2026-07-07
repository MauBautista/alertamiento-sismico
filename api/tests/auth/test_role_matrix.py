"""Matriz 10 roles × {/me, ack} → status, copiada a mano de RBAC §2.

Si el código diverge de esta tabla (p. ej. otro rol gana acuse), el test FALLA.
``/me`` es identidad genérica → 200 con token válido para todo rol.
``ack`` (Consola C4I ∈ {Total, "Lectura + ack"}) solo lo tienen superadmin,
tenant_admin, soc_operator y gov_operator; el resto → 403.
"""

from __future__ import annotations

import pytest

import auth_utils as au

# Copia MANUAL de RBAC §2 (no se deriva de matrix.py a propósito).
EXPECTED = {
    "takab_superadmin": {"me": 200, "ack": 200},
    "takab_support": {"me": 200, "ack": 403},
    "tenant_admin": {"me": 200, "ack": 200},
    "soc_operator": {"me": 200, "ack": 200},
    "gov_operator": {"me": 200, "ack": 200},
    "inspector": {"me": 200, "ack": 403},
    "building_admin": {"me": 200, "ack": 403},
    "brigadista": {"me": 200, "ack": 403},
    "security_guard": {"me": 200, "ack": 403},
    "occupant": {"me": 200, "ack": 403},
}


@pytest.mark.parametrize("role", sorted(EXPECTED))
async def test_me_status_per_role(client, role: str) -> None:
    token = au.make_token(role, tenant=au.TENANT_A, site_scope="*")
    resp = await client.get("/me", headers=au.bearer(token))
    assert resp.status_code == EXPECTED[role]["me"]


@pytest.mark.parametrize("role", sorted(EXPECTED))
async def test_ack_status_per_role(client, make_incident, role: str) -> None:
    if role == "gov_operator":
        tenant = au.DB_TENANT_AGENCY
        iid = await make_incident(au.DB_TENANT_GOV, au.DB_SITE_GOV)
    else:
        tenant = au.DB_TENANT_PRIV
        iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    token = au.make_token(role, tenant=tenant, site_scope="*", user_id="ackuser")
    resp = await client.post(f"/incidents/{iid}/ack", headers=au.bearer(token))
    assert resp.status_code == EXPECTED[role]["ack"], resp.text


async def test_ack_without_token_is_401(client) -> None:
    resp = await client.post(f"/incidents/{au.TENANT_A}/ack")
    assert resp.status_code == 401
