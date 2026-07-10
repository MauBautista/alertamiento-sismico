"""POST /incidents/{id}/epicenter (T-1.48): reubicación manual auditada.

La física de la función SECURITY DEFINER se prueba en test_migration_0011;
aquí va el contrato HTTP: roles por matriz, 404 invisible cross-tenant,
acción en el timeline y auditoría.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine

pytestmark = pytest.mark.usefixtures("base_data")


def _hdr(role: str = "soc_operator", *, tenant: str = au.DB_TENANT_PRIV):
    return au.bearer(au.make_token(role, tenant=tenant, user_id=str(uuid.uuid4())))


async def test_relocate_without_event_creates_manual(client, make_incident) -> None:
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    r = await client.post(
        f"/incidents/{iid}/epicenter",
        headers=_hdr(),
        json={"lon": -98.21, "lat": 19.05, "note": "reporte SSN"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["created_event"] is True
    assert body["event_id"].startswith("EVT-MAN-")
    assert body["epicenter"] == {"lon": -98.21, "lat": 19.05}
    assert body["previous"] is None

    # Re-POST: mismo evento determinista, ya linkeado.
    r2 = await client.post(
        f"/incidents/{iid}/epicenter", headers=_hdr(), json={"lon": -98.30, "lat": 19.10}
    )
    assert r2.status_code == 200
    assert r2.json()["event_id"] == body["event_id"]
    assert r2.json()["created_event"] is False
    assert r2.json()["previous"] == {"lon": -98.21, "lat": 19.05}


async def test_relocate_with_linked_event_updates(client, make_incident, make_event) -> None:
    eid = await make_event()
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, event_id=eid)
    r = await client.post(
        f"/incidents/{iid}/epicenter",
        headers=_hdr("tenant_admin"),
        json={"lon": -98.5, "lat": 18.9},
    )
    assert r.status_code == 200
    assert r.json()["event_id"] == eid
    assert r.json()["created_event"] is False


async def test_relocate_lands_in_timeline_and_audit(client, make_incident) -> None:
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    await client.post(
        f"/incidents/{iid}/epicenter", headers=_hdr(), json={"lon": -98.2, "lat": 19.0}
    )
    acts = await client.get(f"/incidents/{iid}/actions", headers=_hdr())
    kinds = [a["kind"] for a in acts.json()]
    assert "epicenter_relocate" in kinds
    engine = get_engine()
    async with engine.connect() as conn:
        n = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM audit_log WHERE verb = 'epicenter_relocate' "
                    "AND object = :obj"
                ),
                {"obj": f"incident:{iid}"},
            )
        ).scalar_one()
    assert n == 1


@pytest.mark.parametrize("role", ["inspector", "gov_operator", "building_admin", "takab_support"])
async def test_relocate_forbidden_roles(client, make_incident, role: str) -> None:
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    r = await client.post(
        f"/incidents/{iid}/epicenter", headers=_hdr(role), json={"lon": -98.2, "lat": 19.0}
    )
    assert r.status_code == 403


async def test_relocate_cross_tenant_is_404(client, make_incident) -> None:
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    r = await client.post(
        f"/incidents/{iid}/epicenter",
        headers=_hdr(tenant=au.DB_TENANT_PRIV2),
        json={"lon": -98.2, "lat": 19.0},
    )
    assert r.status_code == 404


async def test_relocate_bounds_rejected_by_schema(client, make_incident) -> None:
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    r = await client.post(
        f"/incidents/{iid}/epicenter", headers=_hdr(), json={"lon": 200.0, "lat": 19.0}
    )
    assert r.status_code == 422
