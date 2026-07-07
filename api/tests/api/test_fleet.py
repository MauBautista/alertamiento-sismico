"""Tests de la flota edge (T-1.22 · B1/G7).

Cubre la derivación de estado como VERDAD ÚNICA en dos planos: (1) unit puro de
``derive_fleet_state`` para los 3 estados y sus bordes; (2) el endpoint con filas
``device_health`` fixture que producen OPERATIVO/DEGRADADO/SIN ENLACE, más RLS y
autorización por rol (RBAC §2, columna Flota Edge).
"""

from __future__ import annotations

import os

import pytest
from fastapi import FastAPI
from sqlalchemy import text

import auth_utils as au
from takab_api.auth import deps
from takab_api.db.engine import get_engine
from takab_api.routers.fleet import router as fleet_router
from takab_api.schemas.fleet import (
    DEGRADADO,
    OPERATIVO,
    SIN_ENLACE,
    derive_fleet_state,
)

T_A = "81111111-1111-1111-1111-111111111111"  # private
T_B = "82222222-2222-2222-2222-222222222222"  # private (RLS)
T_GOV = "83333333-3333-3333-3333-333333333333"  # gov_shared
GOV_AGENCY = "89999999-9999-9999-9999-999999999999"  # tenant de la agencia gov
S_A = "8a000000-0000-0000-0000-0000000000a1"
S_B = "8b000000-0000-0000-0000-0000000000b1"
S_GOV = "8c000000-0000-0000-0000-0000000000c1"
GW_OP = "8d000000-0000-0000-0000-0000000000d1"
GW_DEG = "8d000000-0000-0000-0000-0000000000d2"
GW_OFF = "8d000000-0000-0000-0000-0000000000d3"
GW_NONE = "8d000000-0000-0000-0000-0000000000d4"
GW_B = "8d000000-0000-0000-0000-0000000000d5"
GW_GOV = "8d000000-0000-0000-0000-0000000000d6"

_GEOM = "ST_SetSRID(ST_MakePoint(-99.13,19.43),4326)::geography"
_TENANTS = (T_A, T_B, T_GOV, GOV_AGENCY)
_CLEANUP = (
    text("DELETE FROM device_health WHERE tenant_id = ANY(:t)"),
    text("DELETE FROM gateways WHERE tenant_id = ANY(:t)"),
    text("DELETE FROM sites WHERE tenant_id = ANY(:t)"),
    text("DELETE FROM tenants WHERE tenant_id = ANY(:t)"),
)

# Umbrales por defecto (schemas/settings) para los unit puros.
_THRESHOLDS = {
    "sin_enlace_s": 300.0,
    "battery_min_pct": 80.0,
    "cert_min_days": 30,
    "mqtt_rtt_max_ms": 1500.0,
    "seedlink_lag_max_s": 2.0,
    "ntp_offset_max_ms": 100.0,
}
_HEALTHY = {
    "power_status": "mains",
    "battery_pct": 100.0,
    "cert_days_remaining": 365,
    "mqtt_rtt_ms": 50.0,
    "seedlink_lag_s": 0.4,
    "ntp_offset_ms": 5.0,
}


# ---- unit puro: derive_fleet_state (verdad única, sin DB) --------------------


def _derive(**over: object) -> str:
    args: dict[str, object] = {"age_s": 1.0, **_HEALTHY, **_THRESHOLDS}
    args.update(over)
    return derive_fleet_state(**args)  # type: ignore[arg-type]


def test_derive_operativo() -> None:
    assert _derive() == OPERATIVO


def test_derive_sin_enlace_when_no_heartbeat() -> None:
    assert _derive(age_s=None) == SIN_ENLACE


def test_derive_sin_enlace_when_stale() -> None:
    assert _derive(age_s=301.0) == SIN_ENLACE  # justo por encima del umbral
    assert _derive(age_s=300.0) == OPERATIVO  # en el umbral aún hay enlace


@pytest.mark.parametrize(
    "over",
    [
        {"power_status": "battery"},
        {"battery_pct": 79.0},
        {"cert_days_remaining": 29},
        {"mqtt_rtt_ms": 1500.1},
        {"seedlink_lag_s": 2.1},
        {"ntp_offset_ms": 100.1},
        {"ntp_offset_ms": -100.1},  # el offset se compara en valor absoluto
    ],
)
def test_derive_degradado_per_metric(over: dict[str, object]) -> None:
    assert _derive(**over) == DEGRADADO


def test_derive_stale_beats_degraded() -> None:
    # Sin enlace domina aunque además haya métricas malas.
    assert _derive(age_s=None, power_status="battery") == SIN_ENLACE


# ---- endpoint: estados derivados + RLS + autz -------------------------------


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAKAB_API_AUTH_ISSUER", au.ISSUER)
    monkeypatch.setenv("TAKAB_API_AUTH_AUDIENCE", au.AUDIENCE)
    monkeypatch.setenv("TAKAB_API_AUTH_JWKS_JSON", au.jwks_json())
    dsn = os.environ.get("DATABASE_URL")
    if dsn:
        monkeypatch.setenv("TAKAB_API_DATABASE_URL", dsn)
    deps._reset_caches()
    get_engine.cache_clear()
    yield
    deps._reset_caches()


async def _cleanup() -> None:
    async with get_engine().begin() as conn:
        for stmt in _CLEANUP:
            await conn.execute(stmt, {"t": list(_TENANTS)})


async def _health(conn, tid, gw, *, age_min: float, **over: object) -> None:
    cols = {
        "power_status": "mains",
        "battery_pct": 100.0,
        "cert_days_remaining": 365,
        "mqtt_rtt_ms": 50.0,
        "seedlink_lag_s": 0.4,
        "ntp_offset_ms": 5.0,
    }
    cols.update(over)
    await conn.execute(
        text(
            "INSERT INTO device_health (ts, tenant_id, gateway_id, reason, power_status, "
            "battery_pct, cert_days_remaining, mqtt_rtt_ms, seedlink_lag_s, ntp_offset_ms) "
            "VALUES (now() - make_interval(mins => :age), :t, :gw, 'heartbeat', :ps, "
            ":bp, :cert, :rtt, :lag, :ntp)"
        ),
        {
            "age": age_min,
            "t": tid,
            "gw": gw,
            "ps": cols["power_status"],
            "bp": cols["battery_pct"],
            "cert": cols["cert_days_remaining"],
            "rtt": cols["mqtt_rtt_ms"],
            "lag": cols["seedlink_lag_s"],
            "ntp": cols["ntp_offset_ms"],
        },
    )


@pytest.fixture
async def seed() -> None:
    """Tenant A con 4 gateways (op/deg/off/none), tenant B y gov_shared para RLS."""
    await _cleanup()
    engine = get_engine()
    async with engine.begin() as conn:
        for tid, code, vis in (
            (T_A, "B1FLT_A", "private"),
            (T_B, "B1FLT_B", "private"),
            (T_GOV, "B1FLT_G", "gov_shared"),
        ):
            await conn.execute(
                text(
                    "INSERT INTO tenants (tenant_id, code, name, visibility) "
                    "VALUES (:id, :code, 'B1', :vis)"
                ),
                {"id": tid, "code": code, "vis": vis},
            )
        for sid, tid in ((S_A, T_A), (S_B, T_B), (S_GOV, T_GOV)):
            await conn.execute(
                text(
                    "INSERT INTO sites (site_id, tenant_id, code, name, geom) "
                    f"VALUES (:sid, :tid, :code, 'Sitio', {_GEOM})"
                ),
                {"sid": sid, "tid": tid, "code": sid[:6]},
            )
        for gw, tid, sid, serial in (
            (GW_OP, T_A, S_A, "GW-OP"),
            (GW_DEG, T_A, S_A, "GW-DEG"),
            (GW_OFF, T_A, S_A, "GW-OFF"),
            (GW_NONE, T_A, S_A, "GW-NONE"),
            (GW_B, T_B, S_B, "GW-B"),
            (GW_GOV, T_GOV, S_GOV, "GW-GOV"),
        ):
            await conn.execute(
                text(
                    "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial) "
                    "VALUES (:gw, :t, :s, :serial)"
                ),
                {"gw": gw, "t": tid, "s": sid, "serial": serial},
            )
        # heartbeats: op reciente sano; deg reciente con batería; off viejo; none sin fila.
        await _health(conn, T_A, GW_OP, age_min=0)
        await _health(conn, T_A, GW_DEG, age_min=0, power_status="battery")
        await _health(conn, T_A, GW_OFF, age_min=10)
        await _health(conn, T_B, GW_B, age_min=0)
        await _health(conn, T_GOV, GW_GOV, age_min=0)
    yield
    await _cleanup()
    await engine.dispose()
    get_engine.cache_clear()


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(fleet_router)
    return app


async def _get(token: str):
    async with au.client_for(_app()) as c:
        return await c.get("/fleet/gateways", headers=au.bearer(token))


async def test_states_derived_server_side(seed: None) -> None:
    resp = await _get(au.make_token("soc_operator", tenant=T_A))
    assert resp.status_code == 200
    by_serial = {g["serial"]: g["derived_state"] for g in resp.json()}
    assert by_serial == {
        "GW-OP": OPERATIVO,
        "GW-DEG": DEGRADADO,
        "GW-OFF": SIN_ENLACE,
        "GW-NONE": SIN_ENLACE,
    }


async def test_rls_tenant_a_does_not_see_b_gateway(seed: None) -> None:
    resp = await _get(au.make_token("soc_operator", tenant=T_A))
    serials = {g["serial"] for g in resp.json()}
    assert "GW-B" not in serials
    assert "GW-GOV" not in serials  # tenant privado no ve la flota gov_shared


async def test_gov_operator_sees_only_gov_shared(seed: None) -> None:
    # gov pertenece a su agencia; ve gateways de tenants gov_shared, no privados.
    resp = await _get(au.make_token("gov_operator", tenant=GOV_AGENCY))
    assert resp.status_code == 200
    serials = {g["serial"] for g in resp.json()}
    assert "GW-GOV" in serials  # ve la flota de tenants gov_shared
    assert "GW-OP" not in serials  # pero NO la de tenants privados (T_A)
    assert "GW-B" not in serials


@pytest.mark.parametrize("role", ["inspector", "building_admin"])
async def test_role_without_fleet_forbidden(seed: None, role: str) -> None:
    resp = await _get(au.make_token(role, tenant=T_A))
    assert resp.status_code == 403


async def test_unauthenticated_rejected() -> None:
    async with au.client_for(_app()) as c:
        resp = await c.get("/fleet/gateways")
    assert resp.status_code == 401
