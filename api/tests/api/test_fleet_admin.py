"""CRUD de flota (T-1.32): autz ``manage_fleet``, tenancy en ESCRITURA, 409 y auditoría.

El eje de estos tests es que la escritura nunca cruce tenants. Las políticas
``sites_admin``/``gateways_admin``/``sensors_admin`` llevan
``WITH CHECK (app_is_takab_internal())`` **sin filtro de tenant**: la DB no detendría a
un rol interno que insertara en un tenant ajeno. Y las claves foráneas de PostgreSQL no
comparan ``tenant_id``, así que un ``site_id`` ajeno en el cuerpo colgaría hardware de
un cliente en el edificio de otro. Ambas puertas se cierran en la API y aquí se prueban.
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi import FastAPI
from sqlalchemy import text

import auth_utils as au
from takab_api.auth import deps
from takab_api.db.engine import get_engine
from takab_api.routers.fleet import router as fleet_router
from takab_api.routers.sensors import router as sensors_router
from takab_api.routers.sites import router as sites_router

# Prefijo 6: no colisiona con los seeds sync (1/2/3/9/a/b/c), async (7) ni B1 (8).
T_A = "61111111-1111-1111-1111-111111111111"
T_B = "62222222-2222-2222-2222-222222222222"
S_A = "6a000000-0000-0000-0000-0000000000a1"
S_B = "6b000000-0000-0000-0000-0000000000b1"
G_B = "6d000000-0000-0000-0000-0000000000d1"
Z_B = "6e000000-0000-0000-0000-0000000000e1"

_GEOM = "ST_SetSRID(ST_MakePoint(-99.13,19.43),4326)::geography"
_TENANTS = (T_A, T_B)
_CLEANUP = (
    text("DELETE FROM sensors WHERE tenant_id = ANY(:t)"),
    text("DELETE FROM gateways WHERE tenant_id = ANY(:t)"),
    text("DELETE FROM zones WHERE tenant_id = ANY(:t)"),
    text("DELETE FROM sites WHERE tenant_id = ANY(:t)"),
    text("TRUNCATE audit_log"),  # append-only: DELETE lo veta un trigger
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
    """Dos tenants privados; un sitio cada uno; gabinete y zona en B (para el cruce)."""
    await _cleanup()
    engine = get_engine()
    async with engine.begin() as conn:
        for tid, code in ((T_A, "FLEET_A"), (T_B, "FLEET_B")):
            await conn.execute(
                text(
                    "INSERT INTO tenants (tenant_id, code, name, visibility) "
                    "VALUES (:id, :code, 'T-1.32', 'private')"
                ),
                {"id": tid, "code": code},
            )
        for sid, tid, code in ((S_A, T_A, "SA"), (S_B, T_B, "SB")):
            await conn.execute(
                text(
                    "INSERT INTO sites (site_id, tenant_id, code, name, geom) "
                    f"VALUES (:sid, :tid, :code, 'Sitio', {_GEOM})"
                ),
                {"sid": sid, "tid": tid, "code": code},
            )
        await conn.execute(
            text(
                "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial) "
                "VALUES (:g, :t, :s, 'SN-B-0001')"
            ),
            {"g": G_B, "t": T_B, "s": S_B},
        )
        await conn.execute(
            text(
                "INSERT INTO zones (zone_id, tenant_id, site_id, name) "
                "VALUES (:z, :t, :s, 'Planta baja')"
            ),
            {"z": Z_B, "t": T_B, "s": S_B},
        )
    yield
    await _cleanup()
    await engine.dispose()
    get_engine.cache_clear()


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(sites_router)
    app.include_router(fleet_router)
    app.include_router(sensors_router)
    return app


def _tok(role: str, tenant: str = T_A) -> dict[str, str]:
    return au.bearer(au.make_token(role, tenant=tenant, site_scope="*"))


def _site_body(**over) -> dict:
    return {"code": "NUEVO", "name": "Torre Norte", "lat": 19.43, "lon": -99.13} | over


async def _post(path: str, body: dict, token: dict[str, str]):
    async with au.client_for(_app()) as c:
        return await c.post(path, json=body, headers=token)


async def _put(path: str, body: dict, token: dict[str, str]):
    async with au.client_for(_app()) as c:
        return await c.put(path, json=body, headers=token)


async def _delete(path: str, token: dict[str, str]):
    async with au.client_for(_app()) as c:
        return await c.delete(path, headers=token)


async def _get(path: str, token: dict[str, str]):
    async with au.client_for(_app()) as c:
        return await c.get(path, headers=token)


async def _audit_verbs() -> list[str]:
    async with get_engine().connect() as conn:
        rows = (await conn.execute(text("SELECT verb FROM audit_log ORDER BY audit_id"))).all()
    return [r.verb for r in rows]


# ---- sitios ------------------------------------------------------------------


async def test_create_site_lands_in_callers_tenant_and_audits(seed: None) -> None:
    resp = await _post("/sites", _site_body(), _tok("tenant_admin"))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["tenant_id"] == T_A
    assert body["lat"] == pytest.approx(19.43)
    assert body["status"] == "active"
    assert body["row_version"]  # testigo de concurrencia presente
    assert await _audit_verbs() == ["site_create"]


async def test_tenant_admin_cannot_plant_a_site_in_another_tenant(seed: None) -> None:
    """El cuerpo pide el tenant B; el token es de A. La API ignora el cuerpo y lo rechaza."""
    resp = await _post("/sites", _site_body(tenant_id=T_B), _tok("tenant_admin", tenant=T_A))
    assert resp.status_code == 403, resp.text
    assert await _audit_verbs() == []


async def test_superadmin_must_name_the_tenant_explicitly(seed: None) -> None:
    """``sites_admin`` no filtra por tenant en su WITH CHECK: el default silencioso
    (el tenant de los claims del superadmin) crearía el sitio en el tenant equivocado."""
    missing = await _post("/sites", _site_body(), _tok("takab_superadmin"))
    assert missing.status_code == 400, missing.text

    ghost = await _post("/sites", _site_body(tenant_id=str(uuid4())), _tok("takab_superadmin"))
    assert ghost.status_code == 404

    ok = await _post("/sites", _site_body(tenant_id=T_B), _tok("takab_superadmin"))
    assert ok.status_code == 201
    assert ok.json()["tenant_id"] == T_B


async def test_takab_support_cannot_manage_fleet(seed: None) -> None:
    """[DECISION 2026-07-09] Soporte lee la flota; no mueve la geometría de un sitio."""
    write = await _post("/sites", _site_body(tenant_id=T_A), _tok("takab_support"))
    assert write.status_code == 403
    read = await _get("/sites", _tok("takab_support"))
    assert read.status_code == 200


async def test_soc_operator_cannot_write_but_can_read(seed: None) -> None:
    assert (await _post("/sites", _site_body(), _tok("soc_operator"))).status_code == 403
    assert (await _get("/sites", _tok("soc_operator"))).status_code == 200


async def test_duplicate_code_within_tenant_is_409(seed: None) -> None:
    first = await _post("/sites", _site_body(code="DUP"), _tok("tenant_admin"))
    assert first.status_code == 201
    again = await _post("/sites", _site_body(code="DUP"), _tok("tenant_admin"))
    assert again.status_code == 409, again.text


async def test_same_code_in_another_tenant_is_allowed(seed: None) -> None:
    """``sites.code`` es único POR TENANT (UNIQUE (tenant_id, code)), no global."""
    a = await _post("/sites", _site_body(code="TORRE1"), _tok("tenant_admin", tenant=T_A))
    b = await _post("/sites", _site_body(code="TORRE1"), _tok("tenant_admin", tenant=T_B))
    assert (a.status_code, b.status_code) == (201, 201)


async def test_stale_row_version_is_409_and_does_not_move_the_site(seed: None) -> None:
    created = (await _post("/sites", _site_body(), _tok("tenant_admin"))).json()
    stale = created["row_version"]

    first = await _put(
        f"/sites/{created['site_id']}",
        _site_body(name="Primero", base_row_version=stale),
        _tok("tenant_admin"),
    )
    assert first.status_code == 200, first.text
    assert first.json()["row_version"] != stale

    second = await _put(
        f"/sites/{created['site_id']}",
        _site_body(name="Segundo", lat=1.0, lon=1.0, base_row_version=stale),
        _tok("tenant_admin"),
    )
    assert second.status_code == 409, second.text

    still = (await _get(f"/sites/{created['site_id']}", _tok("tenant_admin"))).json()
    assert still["name"] == "Primero"
    assert still["lat"] == pytest.approx(19.43), "el segundo escritor no movió la estación"


async def test_update_foreign_site_is_404(seed: None) -> None:
    resp = await _put(f"/sites/{S_B}", _site_body(), _tok("tenant_admin", tenant=T_A))
    assert resp.status_code == 404


async def test_retire_is_soft_idempotent_and_hides_from_the_catalog(seed: None) -> None:
    created = (await _post("/sites", _site_body(), _tok("tenant_admin"))).json()
    sid = created["site_id"]

    first = await _delete(f"/sites/{sid}", _tok("tenant_admin"))
    assert first.status_code == 200
    assert first.json()["status"] == "retired"
    assert (await _delete(f"/sites/{sid}", _tok("tenant_admin"))).status_code == 200  # idempotente

    listing = (await _get("/sites", _tok("tenant_admin"))).json()
    assert sid not in {s["site_id"] for s in listing}

    with_retired = (await _get("/sites?include_retired=true", _tok("tenant_admin"))).json()
    assert sid in {s["site_id"] for s in with_retired}, "la fila sigue ahí: retiro lógico"

    # Y el detalle sigue resolviendo: la evidencia del sitio no queda huérfana.
    assert (await _get(f"/sites/{sid}", _tok("tenant_admin"))).status_code == 200


# ---- gabinetes ---------------------------------------------------------------


async def test_gateway_inherits_tenant_from_its_site_and_starts_provisioned(seed: None) -> None:
    resp = await _post(
        "/fleet/gateways", {"site_id": S_A, "serial": "SN-A-0001"}, _tok("tenant_admin")
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["tenant_id"] == T_A
    assert body["status"] == "provisioned", "sin heartbeat no se puede afirmar 'online'"
    assert body["iot_thing"] is None, "la API no crea things en AWS"


async def test_gateway_cannot_hang_from_another_tenants_site(seed: None) -> None:
    """Las FK no comparan tenant: sin la comprobación de la API, el gabinete de A
    quedaría colgado del edificio de B y su telemetría cruzaría de tenant."""
    resp = await _post(
        "/fleet/gateways", {"site_id": S_B, "serial": "SN-X-0001"}, _tok("tenant_admin", tenant=T_A)
    )
    assert resp.status_code == 404, resp.text  # RLS oculta el sitio de B


async def test_duplicate_gateway_serial_is_409_across_tenants(seed: None) -> None:
    """``gateways.serial`` es único GLOBAL (no por tenant): el choque es un 409, no un 500."""
    resp = await _post(
        "/fleet/gateways", {"site_id": S_A, "serial": "SN-B-0001"}, _tok("tenant_admin")
    )
    assert resp.status_code == 409, resp.text


async def test_gateway_retire_and_restore_never_claims_online(seed: None) -> None:
    gid = (
        await _post("/fleet/gateways", {"site_id": S_A, "serial": "SN-A-9"}, _tok("tenant_admin"))
    ).json()["gateway_id"]

    retired = await _delete(f"/fleet/gateways/{gid}", _tok("tenant_admin"))
    assert retired.json()["status"] == "retired"

    restored = await _post(f"/fleet/gateways/{gid}/restore", {}, _tok("tenant_admin"))
    assert restored.status_code == 200
    assert restored.json()["status"] == "provisioned"


# ---- sensores ----------------------------------------------------------------


def _sensor_body(**over) -> dict:
    return {"site_id": S_A, "kind": "structural", "model": "RS4D"} | over


async def test_create_sensor_defaults_to_rs4d_channels(seed: None) -> None:
    resp = await _post("/sensors", _sensor_body(), _tok("tenant_admin"))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["channels"] == ["EHZ", "ENZ", "ENN", "ENE"]
    assert body["sample_rate"] == 100
    assert body["lat"] is None, "sin coordenadas propias hereda la del sitio"


async def test_sensor_cannot_reference_another_tenants_gateway(seed: None) -> None:
    """El sitio es de A y el gabinete de B: la FK lo aceptaría, la API no."""
    resp = await _post("/sensors", _sensor_body(gateway_id=G_B), _tok("tenant_admin", tenant=T_A))
    assert resp.status_code == 404, resp.text  # RLS oculta el gateway de B


async def test_sensor_cannot_reference_another_tenants_zone(seed: None) -> None:
    resp = await _post("/sensors", _sensor_body(zone_id=Z_B), _tok("tenant_admin", tenant=T_A))
    assert resp.status_code == 404, resp.text


async def test_superadmin_sees_the_cross_tenant_reference_and_gets_403(seed: None) -> None:
    """El interno SÍ ve ambas filas (``*_admin`` bypassa RLS): el 403 lo pone la API."""
    site_a = (await _post("/sites", _site_body(tenant_id=T_A), _tok("takab_superadmin"))).json()
    resp = await _post(
        "/sensors",
        _sensor_body(site_id=site_a["site_id"], gateway_id=G_B),
        _tok("takab_superadmin"),
    )
    assert resp.status_code == 403, resp.text


async def test_sensor_half_coordinate_is_rejected(seed: None) -> None:
    resp = await _post("/sensors", _sensor_body(lat=19.4), _tok("tenant_admin"))
    assert resp.status_code == 422, "media coordenada no es una ubicación"


async def test_sensor_invalid_kind_is_rejected(seed: None) -> None:
    resp = await _post("/sensors", _sensor_body(kind="telepathic"), _tok("tenant_admin"))
    assert resp.status_code == 422


async def test_sensor_retire_keeps_the_row(seed: None) -> None:
    sid = (await _post("/sensors", _sensor_body(), _tok("tenant_admin"))).json()["sensor_id"]
    resp = await _delete(f"/sensors/{sid}", _tok("tenant_admin"))
    assert resp.status_code == 200
    assert resp.json()["status"] == "retired"

    listing = (await _get(f"/sensors?site_id={S_A}", _tok("tenant_admin"))).json()
    assert sid in {s["sensor_id"] for s in listing}
