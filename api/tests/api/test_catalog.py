"""GET /catalog/earthquakes (T-1.48): catálogo global de referencia SSN/USGS."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine

pytestmark = pytest.mark.usefixtures("base_data")


def _hdr(role: str = "soc_operator", *, tenant: str = au.DB_TENANT_PRIV):
    return au.bearer(au.make_token(role, tenant=tenant, user_id=str(uuid.uuid4())))


@pytest.fixture
async def catalog_rows(db_engine) -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO reference_earthquakes "
                "(catalog_key, origin_time, magnitude, place, epicenter, depth_km, "
                " source, source_ref) VALUES "
                "('T-1985', '1985-09-19T13:17:47Z', 8.0, 'Michoacan 1985', "
                " ST_SetSRID(ST_MakePoint(-102.533, 18.19), 4326)::geography, 27.9, "
                " 'USGS', 'ref85'), "
                "('T-2017', '2017-09-19T18:14:40Z', 7.1, 'Puebla-Morelos 19S', "
                " ST_SetSRID(ST_MakePoint(-98.72, 18.4), 4326)::geography, 57, 'SSN', 'ref17') "
                "ON CONFLICT (catalog_key) DO NOTHING"
            )
        )


async def test_list_ordered_desc_with_shape(client, catalog_rows) -> None:
    r = await client.get("/catalog/earthquakes", headers=_hdr())
    assert r.status_code == 200
    items = r.json()["items"]
    keys = [i["catalog_key"] for i in items if i["catalog_key"].startswith("T-")]
    assert keys == ["T-2017", "T-1985"]  # más reciente primero
    row = next(i for i in items if i["catalog_key"] == "T-2017")
    assert row["magnitude"] == 7.1
    assert row["source"] == "SSN"
    assert row["place"] == "Puebla-Morelos 19S"
    assert round(row["lat"], 2) == 18.40
    assert round(row["lon"], 2) == -98.72
    assert row["depth_km"] == 57.0
    assert row["source_ref"] == "ref17"


async def test_catalog_is_global_across_tenants(client, catalog_rows) -> None:
    a = await client.get("/catalog/earthquakes", headers=_hdr(tenant=au.DB_TENANT_PRIV))
    b = await client.get(
        "/catalog/earthquakes", headers=_hdr("building_admin", tenant=au.DB_TENANT_PRIV2)
    )
    assert a.status_code == b.status_code == 200
    assert a.json() == b.json()


async def test_catalog_requires_token(client, catalog_rows) -> None:
    r = await client.get("/catalog/earthquakes")
    assert r.status_code == 401


async def test_catalog_rejects_mobile_surface(client, catalog_rows) -> None:
    hdr = au.bearer(au.make_token("soc_operator", tenant=au.DB_TENANT_PRIV, surface="mobile"))
    r = await client.get("/catalog/earthquakes", headers=hdr)
    assert r.status_code == 403
