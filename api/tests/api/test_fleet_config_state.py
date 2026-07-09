"""``GET /fleet/gateways/{id}/config-state`` — observabilidad del sync firmado (T-1.30).

``POST /rule-sets/{id}/publish`` solo registra la INTENCIÓN (202 ``pending_sync``);
quien firma y publica de verdad es el worker de T-1.23, que hace UPSERT en
``gateway_config_state``. Sin este endpoint la consola no podía distinguir
"pendiente" de "ya llegó al gabinete" y habría tenido que mentir.

``in_sync`` se calcula con el MISMO predicado del worker (``commands/sync.py``:
``st.payload IS DISTINCT FROM rs.config->'edge'``), invertido → verdad única.
La firma HMAC cruda JAMÁS sale del servidor: solo su huella sha256.
"""

from __future__ import annotations

import hashlib
import json
import os

import pytest
from fastapi import FastAPI
from sqlalchemy import text

import auth_utils as au
from takab_api.auth import deps
from takab_api.db.engine import get_engine
from takab_api.routers.fleet import router as fleet_router

pytestmark = pytest.mark.asyncio

T_A = "91111111-1111-1111-1111-111111111111"
T_B = "92222222-2222-2222-2222-222222222222"
S_A = "9a000000-0000-0000-0000-0000000000a1"
# Sitio con rule_set propio SIN bloque 'edge' (el de sitio gana al de tenant).
S_A_NOEDGE = "9a000000-0000-0000-0000-0000000000a2"
S_B = "9b000000-0000-0000-0000-0000000000b1"

GW_SYNCED = "9d000000-0000-0000-0000-0000000000d1"  # publicado y al día
GW_STALE = "9d000000-0000-0000-0000-0000000000d2"  # publicado, rule_set cambió
GW_NEVER = "9d000000-0000-0000-0000-0000000000d3"  # nunca publicado
GW_NOEDGE = "9d000000-0000-0000-0000-0000000000d4"  # rule_set sin bloque 'edge'
GW_RETIRED = "9d000000-0000-0000-0000-0000000000d5"  # no comandable
GW_B = "9d000000-0000-0000-0000-0000000000d6"  # otro tenant (RLS)

_GEOM = "ST_SetSRID(ST_MakePoint(-99.13,19.43),4326)::geography"
_TENANTS = (T_A, T_B)

EDGE_CFG = {"thresholds": {"pga_trip_g": 0.08}, "sample_rate": 100}
EDGE_CFG_NEW = {"thresholds": {"pga_trip_g": 0.05}, "sample_rate": 100}
RAW_SIG = "deadbeefcafe1234567890abcdef"

_CLEANUP = (
    text("DELETE FROM gateway_config_state WHERE tenant_id = ANY(:t)"),
    text("DELETE FROM rule_sets WHERE tenant_id = ANY(:t)"),
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
    await _cleanup()
    engine = get_engine()
    async with engine.begin() as conn:
        for tid, code in ((T_A, "CFGST_A"), (T_B, "CFGST_B")):
            await conn.execute(
                text("INSERT INTO tenants (tenant_id, code, name) VALUES (:id, :code, 'CFG')"),
                {"id": tid, "code": code},
            )
        # `code` es UNIQUE por tenant: los dos sitios de T_A comparten prefijo, así
        # que se etiquetan a mano en vez de recortar el uuid.
        for sid, tid, code in ((S_A, T_A, "SA"), (S_A_NOEDGE, T_A, "SA-NOEDGE"), (S_B, T_B, "SB")):
            await conn.execute(
                text(
                    "INSERT INTO sites (site_id, tenant_id, code, name, geom) "
                    f"VALUES (:sid, :tid, :code, 'Sitio', {_GEOM})"
                ),
                {"sid": sid, "tid": tid, "code": code},
            )
        # status ∈ (provisioned, online, degraded, offline, retired) — db/schema.sql.
        for gw, tid, sid, serial, status, thing in (
            (GW_SYNCED, T_A, S_A, "GW-SYNCED", "online", "thing-1"),
            (GW_STALE, T_A, S_A, "GW-STALE", "online", "thing-2"),
            (GW_NEVER, T_A, S_A, "GW-NEVER", "online", "thing-3"),
            (GW_NOEDGE, T_A, S_A_NOEDGE, "GW-NOEDGE", "online", "thing-4"),
            (GW_RETIRED, T_A, S_A, "GW-RETIRED", "retired", None),
            (GW_B, T_B, S_B, "GW-B", "online", "thing-b"),
        ):
            await conn.execute(
                text(
                    "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, "
                    "status, iot_thing) VALUES (:gw, :t, :s, :serial, :st, :thing)"
                ),
                {"gw": gw, "t": tid, "s": sid, "serial": serial, "st": status, "thing": thing},
            )

        # NB: `:param::jsonb` NO liga en SQLAlchemy (su regex de bindparams lleva
        # un lookahead (?!:) para no morder los casts `::`). Usar CAST(... AS jsonb).
        _RS = text(
            "INSERT INTO rule_sets (tenant_id, scope_type, scope_id, version, "
            "is_active, config) VALUES (:t, :scope, :sid, 1, true, CAST(:cfg AS jsonb))"
        )
        # rule_set activo a nivel TENANT con bloque 'edge' → aplica a todos los de T_A…
        await conn.execute(
            _RS,
            {"t": T_A, "scope": "tenant", "sid": T_A, "cfg": json.dumps({"edge": EDGE_CFG})},
        )
        # …salvo GW_NOEDGE, que vive en un sitio cuyo rule_set (más específico, gana
        # sobre el de tenant) no trae 'edge'.
        await conn.execute(
            _RS,
            {
                "t": T_A,
                "scope": "site",
                "sid": S_A_NOEDGE,
                "cfg": json.dumps({"relays": {"siren": "NO"}}),
            },
        )
        await conn.execute(
            _RS,
            {"t": T_B, "scope": "tenant", "sid": T_B, "cfg": json.dumps({"edge": EDGE_CFG})},
        )

        # Estado publicado: SYNCED coincide con el rule_set; STALE quedó atrás.
        for gw, tid, ver, payload in (
            (GW_SYNCED, T_A, 7, EDGE_CFG),
            (GW_STALE, T_A, 3, EDGE_CFG_NEW),
            (GW_B, T_B, 1, EDGE_CFG),
        ):
            await conn.execute(
                text(
                    "INSERT INTO gateway_config_state (gateway_id, tenant_id, version, "
                    "payload, sig) VALUES (:gw, :t, :v, CAST(:p AS jsonb), :sig)"
                ),
                {"gw": gw, "t": tid, "v": ver, "p": json.dumps(payload), "sig": RAW_SIG},
            )
    yield
    await _cleanup()
    await engine.dispose()
    get_engine.cache_clear()


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(fleet_router)
    return app


async def _get(gateway_id: str, token: str):
    async with au.client_for(_app()) as c:
        return await c.get(f"/fleet/gateways/{gateway_id}/config-state", headers=au.bearer(token))


# ---- estado del sync --------------------------------------------------------


async def test_synced_gateway_reports_in_sync(seed: None) -> None:
    """Payload publicado == config.edge del rule_set activo ⇒ SINCRONIZADO."""
    resp = await _get(GW_SYNCED, au.make_token("soc_operator", tenant=T_A))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["in_sync"] is True
    assert body["version"] == 7
    assert body["has_edge_config"] is True
    assert body["is_syncable"] is True
    assert body["published_at"] is not None


async def test_stale_gateway_is_not_in_sync(seed: None) -> None:
    """El rule_set cambió y el gabinete sigue con el payload viejo ⇒ PENDIENTE."""
    body = (await _get(GW_STALE, au.make_token("soc_operator", tenant=T_A))).json()
    assert body["in_sync"] is False
    assert body["version"] == 3  # la versión vieja se muestra tal cual


async def test_never_published_is_200_not_404(seed: None) -> None:
    """Sin fila en gateway_config_state la consola pinta PENDIENTE, no un error."""
    resp = await _get(GW_NEVER, au.make_token("soc_operator", tenant=T_A))
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] is None
    assert body["published_at"] is None
    assert body["sig_fingerprint"] is None
    assert body["in_sync"] is False
    assert body["has_edge_config"] is True


async def test_gateway_without_edge_config_never_syncs(seed: None) -> None:
    """El rule_set de sitio (preferente) no trae 'edge': el worker jamás lo publica.
    Mostrar PENDIENTE eternamente sería mentir; has_edge_config lo explica."""
    body = (await _get(GW_NOEDGE, au.make_token("soc_operator", tenant=T_A))).json()
    assert body["has_edge_config"] is False
    assert body["in_sync"] is False


async def test_gateway_without_any_active_rule_set_is_200_not_500(seed: None) -> None:
    """Sin rule_set activo el LEFT JOIN deja ``rs.config`` NULL y ``NULL ? 'edge'``
    es NULL (jsonb_exists es STRICT), no false: sin COALESCE el bool no-opcional de
    Pydantic reventaba con un 500 en el endpoint que promete 200 + PENDIENTE.

    Es un estado alcanzable: ``rule_sets.is_active`` nace en false y nada garantiza
    que un gateway recién aprovisionado tenga un rule_set activo.
    """
    async with get_engine().begin() as conn:
        await conn.execute(
            text("UPDATE rule_sets SET is_active = false WHERE tenant_id = :t"), {"t": T_A}
        )

    # Con estado publicado (in_sync sería TRUE AND NULL AND … = NULL sin COALESCE).
    resp = await _get(GW_SYNCED, au.make_token("soc_operator", tenant=T_A))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["has_edge_config"] is False
    assert body["in_sync"] is False
    assert body["version"] == 7  # el gabinete sigue con su config vieja

    # Y sin estado publicado tampoco explota.
    never = await _get(GW_NEVER, au.make_token("soc_operator", tenant=T_A))
    assert never.status_code == 200
    assert never.json()["has_edge_config"] is False
    assert never.json()["in_sync"] is False


async def test_retired_gateway_is_not_syncable(seed: None) -> None:
    """El worker excluye status='retired' e iot_thing NULL; la UI no debe prometer sync."""
    body = (await _get(GW_RETIRED, au.make_token("soc_operator", tenant=T_A))).json()
    assert body["is_syncable"] is False


# ---- seguridad --------------------------------------------------------------


async def test_raw_hmac_signature_never_leaves_the_server(seed: None) -> None:
    """La firma cruda junto al payload es material de ataque offline contra la
    clave HMAC. Solo sale su huella sha256 truncada."""
    resp = await _get(GW_SYNCED, au.make_token("soc_operator", tenant=T_A))
    raw = resp.text
    assert RAW_SIG not in raw
    body = resp.json()
    assert "sig" not in body
    assert "payload" not in body
    assert body["sig_fingerprint"] == hashlib.sha256(RAW_SIG.encode()).hexdigest()[:12]


async def test_rls_blocks_other_tenant_gateway(seed: None) -> None:
    """Tenant A no ve el config-state de un gateway de B: 404, no 403 (no revela
    que exista)."""
    resp = await _get(GW_B, au.make_token("soc_operator", tenant=T_A))
    assert resp.status_code == 404


async def test_unknown_gateway_is_404(seed: None) -> None:
    resp = await _get(
        "9f000000-0000-0000-0000-0000000000ff", au.make_token("soc_operator", tenant=T_A)
    )
    assert resp.status_code == 404


@pytest.mark.parametrize("role", ["inspector", "building_admin"])
async def test_role_without_fleet_forbidden(seed: None, role: str) -> None:
    resp = await _get(GW_SYNCED, au.make_token(role, tenant=T_A))
    assert resp.status_code == 403


async def test_unauthenticated_rejected(seed: None) -> None:
    async with au.client_for(_app()) as c:
        resp = await c.get(f"/fleet/gateways/{GW_SYNCED}/config-state")
    assert resp.status_code == 401
