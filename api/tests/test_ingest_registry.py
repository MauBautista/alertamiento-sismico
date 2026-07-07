"""Tests de Registry (T-1.17 G4) contra la DB de pruebas — fixtures SQL propias.

No toca ``conftest.py``: siembra su propia mini-flota (familia de UUIDs
``e9…``, idempotente) y la commitea, porque Registry abre SUS conexiones.
El gateway atiende sensores de DOS sitios (como los gateways sim de la
convención de flota dev).
"""

from __future__ import annotations

import os
from uuid import UUID

import pytest

from takab_api.db import pool
from takab_api.ingest.registry import Registry

DSN = os.environ.get("DATABASE_URL", "postgresql+psycopg://takab:takab_dev@localhost:5432/takab")

TENANT = "e9000000-0000-0000-0000-000000000001"
SITE_A = "e9100000-0000-0000-0000-000000000001"  # sitio propio del gateway
SITE_B = "e9100000-0000-0000-0000-000000000002"  # sitio de su segundo sensor
GW = "e9200000-0000-0000-0000-000000000001"
SENSOR_A = "e9300000-0000-0000-0000-000000000001"
SENSOR_B = "e9300000-0000-0000-0000-000000000002"
SENSOR_SIN_SERIAL = "e9300000-0000-0000-0000-000000000003"

THING = "gw-reg-0001"


@pytest.fixture(scope="module")
def fleet() -> None:
    """Mini-flota committeada (idempotente vía ON CONFLICT DO NOTHING)."""
    conn = pool.connect(DSN)
    try:
        conn.execute(
            "INSERT INTO tenants (tenant_id, code, name) "
            "VALUES (%s, 'tenant-reg', 'Tenant Registry') ON CONFLICT DO NOTHING",
            (TENANT,),
        )
        for site, code in ((SITE_A, "site-reg-a"), (SITE_B, "site-reg-b")):
            conn.execute(
                "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
                "(%s, %s, %s, 'Sitio Registry', "
                "ST_SetSRID(ST_MakePoint(-98.20, 19.04), 4326)::geography) "
                "ON CONFLICT DO NOTHING",
                (site, TENANT, code),
            )
        conn.execute(
            "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, iot_thing) "
            "VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (GW, TENANT, SITE_A, THING, THING),
        )
        for sensor, site, serial in (
            (SENSOR_A, SITE_A, "REG001"),
            (SENSOR_B, SITE_B, "REG002"),
            (SENSOR_SIN_SERIAL, SITE_A, None),  # sin serial ⇒ no es estación
        ):
            conn.execute(
                "INSERT INTO sensors (sensor_id, tenant_id, site_id, gateway_id, "
                "kind, model, serial) VALUES (%s, %s, %s, %s, 'structural', 'RS4D', %s) "
                "ON CONFLICT DO NOTHING",
                (sensor, TENANT, site, GW, serial),
            )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def factory_spy():
    """conn_factory real con contador de aperturas (mide cache hits/misses)."""
    counter = {"n": 0}

    def factory():
        counter["n"] += 1
        return pool.connect(DSN)

    return factory, counter


def test_resolve_happy(fleet, factory_spy) -> None:
    factory, _ = factory_spy
    registry = Registry(factory, ttl_s=30.0, ctx_factory=dict)

    ctx = registry.resolve(THING)

    assert ctx is not None
    assert ctx["tenant_id"] == UUID(TENANT)
    assert ctx["tenant_code"] == "tenant-reg"
    assert ctx["gateway_id"] == UUID(GW)
    assert ctx["gateway_serial"] == THING
    assert ctx["iot_thing"] == THING
    assert ctx["site_id"] == UUID(SITE_A)
    assert ctx["site_code"] == "site-reg-a"
    # estaciones publicables del gateway, aun de OTRO sitio, CON el sitio propio
    # de cada sensor (atribución multi-sitio); el sensor sin serial NO aparece
    # (no puede ser station de Feature1s)
    assert ctx["sensors"] == {
        "REG001": {
            "sensor_id": UUID(SENSOR_A),
            "site_id": UUID(SITE_A),
            "site_code": "site-reg-a",
        },
        "REG002": {
            "sensor_id": UUID(SENSOR_B),
            "site_id": UUID(SITE_B),
            "site_code": "site-reg-b",
        },
    }


def test_default_ctx_factory_builds_real_gateway_ctx(fleet) -> None:
    """Sin ctx_factory inyectado, resolve devuelve el GatewayCtx de handlers.py."""
    from takab_api.ingest.handlers import GatewayCtx

    registry = Registry(lambda: pool.connect(DSN), ttl_s=30.0)

    ctx = registry.resolve(THING)

    assert isinstance(ctx, GatewayCtx)
    assert ctx.gateway_id == UUID(GW)
    assert ctx.tenant_code == "tenant-reg"
    assert ctx.sensors["REG002"].sensor_id == UUID(SENSOR_B)
    assert ctx.sensors["REG002"].site_id == UUID(SITE_B)  # sitio del sensor, no del gateway
    # los sitios ATENDIDOS incluyen el del gateway y los de sus sensores
    assert ctx.served_sites == {"site-reg-a": UUID(SITE_A), "site-reg-b": UUID(SITE_B)}


def test_cache_ttl_second_resolve_does_not_query(fleet, factory_spy) -> None:
    factory, counter = factory_spy
    registry = Registry(factory, ttl_s=30.0, ctx_factory=dict)

    first = registry.resolve(THING)
    second = registry.resolve(THING)

    assert counter["n"] == 1  # el segundo resolve salió de la caché
    assert second is first


def test_ttl_zero_requeries(fleet, factory_spy) -> None:
    factory, counter = factory_spy
    registry = Registry(factory, ttl_s=0.0, ctx_factory=dict)

    registry.resolve(THING)
    registry.resolve(THING)

    assert counter["n"] == 2


def test_invalidate_forces_requery(fleet, factory_spy) -> None:
    factory, counter = factory_spy
    registry = Registry(factory, ttl_s=30.0, ctx_factory=dict)

    registry.resolve(THING)
    registry.invalidate(THING)
    registry.resolve(THING)
    registry.invalidate()  # sin argumento: limpia toda la caché
    registry.resolve(THING)

    assert counter["n"] == 3


def test_unknown_principal_returns_none_and_caches_miss(fleet, factory_spy) -> None:
    factory, counter = factory_spy
    registry = Registry(factory, ttl_s=30.0, ctx_factory=dict)

    assert registry.resolve("gw-desconocido") is None
    assert registry.resolve("gw-desconocido") is None  # miss cacheado

    assert counter["n"] == 1
