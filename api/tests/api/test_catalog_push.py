"""Push del catálogo SSN firmado (T-2.24): POST /gateways/{id}/catalog.

Patrón de test_commands_router: publisher fake por dependency override, claves
HMAC per-gateway inline por env. El sobre publicado debe verificar con el
SecurityManager del edge — eso lo anclan los vectores compartidos; aquí se
prueba la superficie HTTP: auth interno-only, versión monótona, fail-closed
sin clave, y el estado/auditoría persistidos.
"""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi import FastAPI
from sqlalchemy import text

import auth_utils as au
from takab_api.commands.publisher import PublishError
from takab_api.commands.signing import canonical_payload, sign_catalog
from takab_api.db.engine import get_engine
from takab_api.main import create_app
from takab_api.routers.commands import get_publisher
from takab_api.routers.commands import router as commands_router

pytestmark = pytest.mark.asyncio

KEY = "clave-catalogo-test"
GW_CAT = "7c900000-0000-0000-0000-0000000000c9"
THING = "gw-catalog-test"

SNAPSHOT = {
    "fuente": "Servicio Sismológico Nacional (SSN) · Instituto de Geofísica, UNAM",
    "capturado": "2026-07-31T06:00:00-06:00",
    "replicas_nota": "sin réplicas",
    "eventos": [
        {
            "m": 4.2,
            "fecha": "2026-07-30",
            "hora": "22:11:02",
            "lat": 16.7,
            "lon": -98.1,
            "prof": 12.0,
            "loc": "costa de Guerrero",
        }
    ],
    "referencias": [{"n": "CDMX", "lat": 19.4326, "lon": -99.1332}],
}


class _FakePublisher:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.published: list[tuple[str, dict]] = []

    def publish(self, topic: str, payload: bytes) -> None:
        if self.fail:
            raise PublishError("iot caído (simulado)")
        self.published.append((topic, json.loads(payload)))


@pytest.fixture
def publisher() -> _FakePublisher:
    return _FakePublisher()


@pytest.fixture
def app(publisher: _FakePublisher) -> FastAPI:
    application = create_app()
    application.include_router(commands_router)
    application.dependency_overrides[get_publisher] = lambda: publisher
    return application


@pytest.fixture(autouse=True)
def _hmac_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TAKAB_API_COMMAND_HMAC_SECRET_PREFIX", raising=False)
    monkeypatch.setenv("TAKAB_API_COMMAND_HMAC_KEYS_JSON", json.dumps({THING: KEY}))


@pytest.fixture
async def gateway(base_data) -> str:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, iot_thing) "
                "VALUES (:g, :t, :s, 'SER-CAT-A9', :thing) ON CONFLICT DO NOTHING"
            ),
            {"g": GW_CAT, "t": au.DB_TENANT_PRIV, "s": au.DB_SITE_PRIV, "thing": THING},
        )
        # El endpoint COMMITEA (versión monótona para siempre, como exige el
        # edge): se parte de estado limpio para que los asserts absolutos valgan.
        await conn.execute(
            text("DELETE FROM gateway_catalog_state WHERE gateway_id = :g"), {"g": GW_CAT}
        )
    return GW_CAT


async def test_push_signs_publishes_persists_and_audits(
    client, gateway, publisher: _FakePublisher
) -> None:
    tok = au.make_token("takab_superadmin")
    r = await client.post(
        f"/gateways/{GW_CAT}/catalog", json={"catalog": SNAPSHOT}, headers=au.bearer(tok)
    )
    assert r.status_code == 202, r.text
    out = r.json()
    assert out["version"] == 1
    assert out["topic"] == f"takab/catalog/{THING}"

    assert len(publisher.published) == 1
    topic, envelope = publisher.published[0]
    assert topic == f"takab/catalog/{THING}"
    assert envelope["kind"] == "catalog_update"
    assert envelope["version"] == 1
    assert envelope["payload"]["capturado"] == SNAPSHOT["capturado"]
    # La firma reproduce EXACTAMENTE lo que el edge verificará (framing anclado
    # por los vectores compartidos).
    expected = sign_catalog(KEY.encode(), canonical_payload(SNAPSHOT), 1)
    assert envelope["sig"] == expected

    engine = get_engine()
    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text("SELECT version, sig FROM gateway_catalog_state WHERE gateway_id = :g"),
                {"g": GW_CAT},
            )
        ).first()
        assert row is not None and row.version == 1 and row.sig == expected
        verb = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM audit_log "
                    "WHERE verb = 'catalog_published' AND object = :o"
                ),
                {"o": f"gateway:{GW_CAT}"},
            )
        ).scalar_one()
        assert verb >= 1


async def test_push_version_is_monotonic_per_gateway(
    client, gateway, publisher: _FakePublisher
) -> None:
    tok = au.make_token("takab_superadmin")
    for expected_version in (1, 2):
        r = await client.post(
            f"/gateways/{GW_CAT}/catalog", json={"catalog": SNAPSHOT}, headers=au.bearer(tok)
        )
        assert r.status_code == 202
        assert r.json()["version"] == expected_version
    assert [e["version"] for _, e in publisher.published] == [1, 2]


async def test_push_is_internal_only(client, gateway) -> None:
    for role in ("tenant_admin", "soc_operator", "b_admin"):
        tok = au.make_token(role, tenant=au.DB_TENANT_PRIV)
        r = await client.post(
            f"/gateways/{GW_CAT}/catalog", json={"catalog": SNAPSHOT}, headers=au.bearer(tok)
        )
        assert r.status_code == 403, f"{role}: {r.status_code}"


async def test_push_rejects_malformed_catalog(client, gateway) -> None:
    tok = au.make_token("takab_superadmin")
    r = await client.post(
        f"/gateways/{GW_CAT}/catalog",
        json={"catalog": {"eventos": "no-es-lista"}},
        headers=au.bearer(tok),
    )
    assert r.status_code == 400


async def test_push_unknown_gateway_is_404(client, base_data) -> None:
    tok = au.make_token("takab_superadmin")
    r = await client.post(
        f"/gateways/{uuid.uuid4()}/catalog", json={"catalog": SNAPSHOT}, headers=au.bearer(tok)
    )
    assert r.status_code == 404


async def test_push_without_resolvable_key_is_503(
    client, gateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail-closed por gateway (T-1.38): sin SU clave no se firma con nada."""
    monkeypatch.setenv("TAKAB_API_COMMAND_HMAC_KEYS_JSON", json.dumps({"otro-thing": "x"}))
    tok = au.make_token("takab_superadmin")
    r = await client.post(
        f"/gateways/{GW_CAT}/catalog", json={"catalog": SNAPSHOT}, headers=au.bearer(tok)
    )
    assert r.status_code == 503


async def test_publish_failure_does_not_burn_version(
    client, gateway, publisher: _FakePublisher
) -> None:
    publisher.fail = True
    tok = au.make_token("takab_superadmin")
    r = await client.post(
        f"/gateways/{GW_CAT}/catalog", json={"catalog": SNAPSHOT}, headers=au.bearer(tok)
    )
    assert r.status_code == 502
    publisher.fail = False
    r = await client.post(
        f"/gateways/{GW_CAT}/catalog", json={"catalog": SNAPSHOT}, headers=au.bearer(tok)
    )
    assert r.status_code == 202
    assert r.json()["version"] == 1  # la fallida no quemó la v1
