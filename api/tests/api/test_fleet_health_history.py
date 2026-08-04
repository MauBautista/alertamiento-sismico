"""T-2.38 · Historia de salud de la flota: tendencia y reincidencia.

La Flota Edge decía si un gabinete está bien AHORA y nada más. Un gabinete que se cae
cinco veces al día se veía idéntico a uno que nunca falló, y esa es justo la
diferencia entre un corte puntual y un problema de instalación.

Las caídas NO son un campo: se derivan del silencio entre latidos, con el mismo umbral
que ``derive_fleet_state``. Dos definiciones distintas de "sin enlace" en dos pantallas
serían la contradicción que la regla de oro 7 evita.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from sqlalchemy import text

import auth_utils as au
from takab_api.auth import deps
from takab_api.db.engine import get_engine
from takab_api.routers.fleet import router as fleet_router

# Prefijo 3: libre.
T_A = "31111111-1111-1111-1111-111111111111"
T_B = "32222222-2222-2222-2222-222222222222"
S_A = "3a000000-0000-0000-0000-0000000000a1"
S_B = "3b000000-0000-0000-0000-0000000000b1"
GW_STEADY = "3d000000-0000-0000-0000-0000000000d1"
GW_FLAPPY = "3d000000-0000-0000-0000-0000000000d2"
GW_B = "3d000000-0000-0000-0000-0000000000d3"

_GEOM = "ST_SetSRID(ST_MakePoint(-99.13,19.43),4326)::geography"
_TENANTS = (T_A, T_B)
_CLEANUP = (
    text("DELETE FROM device_health WHERE tenant_id = ANY(:t)"),
    text("DELETE FROM gateways WHERE tenant_id = ANY(:t)"),
    text("DELETE FROM sites WHERE tenant_id = ANY(:t)"),
    text("DELETE FROM tenants WHERE tenant_id = ANY(:t)"),
)


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


@pytest.fixture
async def seed() -> None:
    """Un gabinete con latidos continuos y otro con DOS huecos largos.

    Los latidos van cada 60 s durante 3 h. `GW_FLAPPY` calla dos veces 20 min — muy
    por encima de los 5 min de `sin_enlace_min`.
    """
    await _cleanup()
    engine = get_engine()
    now = datetime.now(UTC)
    async with engine.begin() as conn:
        for tid, code in ((T_A, "HH_A"), (T_B, "HH_B")):
            await conn.execute(
                text(
                    "INSERT INTO tenants (tenant_id, code, name, visibility) "
                    "VALUES (:id, :code, 'T-2.38', 'private')"
                ),
                {"id": tid, "code": code},
            )
        for sid, tid, code in ((S_A, T_A, "HHA"), (S_B, T_B, "HHB")):
            await conn.execute(
                text(
                    "INSERT INTO sites (site_id, tenant_id, code, name, geom) "
                    f"VALUES (:sid, :tid, :code, 'Sitio', {_GEOM})"
                ),
                {"sid": sid, "tid": tid, "code": code},
            )
        for gid, tid, sid, serial in (
            (GW_STEADY, T_A, S_A, "SN-HH-1"),
            (GW_FLAPPY, T_A, S_A, "SN-HH-2"),
            (GW_B, T_B, S_B, "SN-HH-B"),
        ):
            await conn.execute(
                text(
                    "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial) "
                    "VALUES (:g, :t, :s, :sn)"
                ),
                {"g": gid, "t": tid, "s": sid, "sn": serial},
            )

        # 180 minutos de latidos; los minutos 40-60 y 100-120 los calla el "flappy".
        rows = []
        for minute in range(180):
            ts = now - timedelta(minutes=180 - minute)
            rows.append((ts, T_A, GW_STEADY, 42.0))
            if not (40 <= minute < 60 or 100 <= minute < 120):
                rows.append((ts, T_A, GW_FLAPPY, 900.0))
            rows.append((ts, T_B, GW_B, 30.0))
        for ts, tid, gid, rtt in rows:
            await conn.execute(
                text(
                    "INSERT INTO device_health "
                    "(ts, tenant_id, gateway_id, reason, mqtt_rtt_ms, seedlink_lag_s) "
                    "VALUES (:ts, :t, :g, 'heartbeat', :rtt, 0.4)"
                ),
                {"ts": ts, "t": tid, "g": gid, "rtt": rtt},
            )
    yield
    await _cleanup()
    await engine.dispose()
    get_engine.cache_clear()


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(fleet_router)
    return app


async def _get(path: str, role: str = "tenant_admin", tenant: str = T_A):
    async with au.client_for(_app()) as c:
        return await c.get(
            path, headers=au.bearer(au.make_token(role, tenant=tenant, site_scope="*"))
        )


async def _by_gateway(path: str = "/fleet/health-history") -> dict[str, dict]:
    resp = await _get(path)
    assert resp.status_code == 200, resp.text
    return {row["gateway_id"]: row for row in resp.json()}


async def test_un_gabinete_estable_no_reporta_caidas(seed: None) -> None:
    rows = await _by_gateway()
    assert rows[GW_STEADY]["outages"] == 0
    assert rows[GW_STEADY]["downtime_s"] == 0.0
    assert rows[GW_STEADY]["last_outage_end"] is None


async def test_dos_silencios_largos_cuentan_dos_caidas(seed: None) -> None:
    """Lo que distingue un corte puntual de una instalación mala."""
    flappy = (await _by_gateway())[GW_FLAPPY]
    assert flappy["outages"] == 2
    # Cada hueco es de 20 min + el minuto del propio latido perdido.
    assert 1200 <= flappy["downtime_s"] <= 2600
    assert flappy["last_outage_end"] is not None


async def test_la_serie_llega_agregada_por_bucket(seed: None) -> None:
    steady = (await _by_gateway("/fleet/health-history?hours=3&bucket_min=60"))[GW_STEADY]
    assert len(steady["buckets"]) >= 3
    assert all(b["heartbeats"] > 0 for b in steady["buckets"])
    # p95 del RTT, no promedio: la cola larga es lo que importa en un enlace.
    assert steady["buckets"][0]["mqtt_rtt_p95_ms"] == pytest.approx(42.0, abs=0.5)


async def test_una_metrica_sin_dato_es_null_no_cero(seed: None) -> None:
    """Regla de oro 7: "no reportó" y "reportó 0" no son lo mismo."""
    steady = (await _by_gateway())[GW_STEADY]
    # Nunca se sembró batería ni NTP: deben venir nulos, no ceros.
    assert all(b["battery_min_pct"] is None for b in steady["buckets"])
    assert all(b["ntp_offset_abs_max_ms"] is None for b in steady["buckets"])


async def test_la_completitud_de_latidos_nunca_supera_uno(seed: None) -> None:
    for row in (await _by_gateway()).values():
        assert row["heartbeat_completeness"] is not None
        assert 0.0 <= row["heartbeat_completeness"] <= 1.0


async def test_el_gabinete_con_huecos_tiene_menos_completitud(seed: None) -> None:
    rows = await _by_gateway()
    assert rows[GW_FLAPPY]["heartbeat_completeness"] < rows[GW_STEADY]["heartbeat_completeness"]


async def test_la_rls_acota_al_tenant(seed: None) -> None:
    assert GW_B not in await _by_gateway()
    otro = await _by_gateway_for_b()
    assert set(otro) == {GW_B}


async def _by_gateway_for_b() -> dict[str, dict]:
    resp = await _get("/fleet/health-history", tenant=T_B)
    assert resp.status_code == 200, resp.text
    return {row["gateway_id"]: row for row in resp.json()}


async def test_la_ventana_se_acota_para_que_no_sea_un_almacen_de_series(seed: None) -> None:
    """`hours` desbordado se recorta en vez de reventar o barrer meses de tabla."""
    assert (await _get("/fleet/health-history?hours=100000")).status_code == 200
    assert (await _get("/fleet/health-history?hours=0&bucket_min=0")).status_code == 200


async def test_exige_acceso_a_la_flota(seed: None) -> None:
    assert (await _get("/fleet/health-history", role="inspector")).status_code == 403
