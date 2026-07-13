"""Command service HTTP (T-1.23 · B9): emitir/listar comandos firmados.

Patrón del conftest de B2 (client/app, tenants A/B/G). El publisher IoT se
sustituye por un fake vía dependency override; las claves HMAC van por env
como mapa inline PER-GATEWAY (T-1.38): cada iot_thing firma con LA SUYA.
"""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi import FastAPI
from sqlalchemy import text

import auth_utils as au
from takab_api.commands.publisher import PublishError
from takab_api.commands.signing import canonical_payload, sign_command
from takab_api.db.engine import get_engine
from takab_api.main import create_app
from takab_api.routers.commands import get_publisher
from takab_api.routers.commands import router as commands_router

pytestmark = pytest.mark.asyncio

KEY = "clave-router-test"
GW_PRIV = "7c300000-0000-0000-0000-0000000000c3"
THING = "gw-cmd-test-a"

# Segundo gabinete comandable del MISMO tenant, con clave DISTINTA (T-1.38).
KEY_B = "clave-router-test-b"
SITE_B3 = "7c300000-0000-0000-0000-00000000015b"
GW_B3 = "7c300000-0000-0000-0000-0000000001c4"
THING_B = "gw-cmd-test-b"


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
    """Mapa inline per-gateway (T-1.38): claves deterministas sin AWS."""
    monkeypatch.delenv("TAKAB_API_COMMAND_HMAC_SECRET_PREFIX", raising=False)
    monkeypatch.setenv("TAKAB_API_COMMAND_HMAC_KEYS_JSON", json.dumps({THING: KEY, THING_B: KEY_B}))


@pytest.fixture
async def gateway(base_data) -> str:
    """Gateway comandable (iot_thing) del sitio del tenant A."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, iot_thing) "
                "VALUES (:g, :t, :s, 'SER-CMD-A', :thing) ON CONFLICT DO NOTHING"
            ),
            {"g": GW_PRIV, "t": au.DB_TENANT_PRIV, "s": au.DB_SITE_PRIV, "thing": THING},
        )
    return GW_PRIV


@pytest.fixture
async def gateway_b(base_data) -> str:
    """Segundo gabinete comandable (tenant A, sitio propio) con clave DISTINTA.

    Sitio nuevo a propósito: DB_SITE_PRIV2 debe seguir SIN gateway para que
    test_site_without_gateway_is_409 no dependa del orden de ejecución.
    """
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
                "(:s, :t, 'S-CMD-B3', 'Sitio cmd B3', "
                "ST_SetSRID(ST_MakePoint(-98.20, 19.04), 4326)::geography) "
                "ON CONFLICT DO NOTHING"
            ),
            {"s": SITE_B3, "t": au.DB_TENANT_PRIV},
        )
        await conn.execute(
            text(
                "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, iot_thing) "
                "VALUES (:g, :t, :s, 'SER-CMD-B3', :thing) ON CONFLICT DO NOTHING"
            ),
            {"g": GW_B3, "t": au.DB_TENANT_PRIV, "s": SITE_B3, "thing": THING_B},
        )
    return SITE_B3


def _body(channel: str = "siren", action: str = "activate") -> dict:
    return {"channel": channel, "action": action, "event_id": "EVT-CMD-1"}


async def test_issue_command_signs_publishes_and_persists(
    client, gateway, publisher: _FakePublisher
) -> None:
    tok = au.make_token("tenant_admin", tenant=au.DB_TENANT_PRIV)
    r = await client.post(
        f"/sites/{au.DB_SITE_PRIV}/commands", json=_body(), headers=au.bearer(tok)
    )
    assert r.status_code == 201, r.text
    row = r.json()
    assert row["status"] == "pending"
    assert row["channel"] == "siren"

    assert len(publisher.published) == 1
    topic, envelope = publisher.published[0]
    assert topic == f"takab/cmd/{THING}"
    assert envelope["kind"] == "command"
    assert envelope["command_id"] == row["command_id"]
    assert envelope["nonce"] == row["nonce"]
    expected = sign_command(
        KEY.encode(), canonical_payload(envelope["payload"]), envelope["nonce"], envelope["ts"]
    )
    assert envelope["sig"] == expected

    engine = get_engine()
    async with engine.begin() as conn:
        verbs = (
            (
                await conn.execute(
                    text("SELECT verb FROM audit_log WHERE tenant_id = :t"),
                    {"t": au.DB_TENANT_PRIV},
                )
            )
            .scalars()
            .all()
        )
    assert "command_issued" in verbs


async def test_rate_limit_user_site_429(client, gateway, publisher, monkeypatch) -> None:
    monkeypatch.setenv("TAKAB_API_COMMAND_RATE_USER_SITE_PER_MIN", "2")
    tok = au.make_token("tenant_admin", tenant=au.DB_TENANT_PRIV)
    for _ in range(2):
        r = await client.post(
            f"/sites/{au.DB_SITE_PRIV}/commands", json=_body(), headers=au.bearer(tok)
        )
        assert r.status_code == 201
    r = await client.post(
        f"/sites/{au.DB_SITE_PRIV}/commands", json=_body(), headers=au.bearer(tok)
    )
    assert r.status_code == 429
    assert len(publisher.published) == 2  # el tercero jamás se publicó


async def test_role_without_actuator_action_forbidden(client, gateway) -> None:
    tok = au.make_token("soc_operator", tenant=au.DB_TENANT_PRIV)  # sin siren_test
    r = await client.post(
        f"/sites/{au.DB_SITE_PRIV}/commands", json=_body(), headers=au.bearer(tok)
    )
    assert r.status_code == 403


async def test_cross_tenant_site_is_404(client, gateway) -> None:
    tok = au.make_token("tenant_admin", tenant=au.DB_TENANT_PRIV2)
    r = await client.post(
        f"/sites/{au.DB_SITE_PRIV}/commands", json=_body(), headers=au.bearer(tok)
    )
    assert r.status_code == 404


async def test_site_scope_outside_is_403(client, gateway) -> None:
    other_site = str(uuid.uuid4())
    tok = au.make_token("tenant_admin", tenant=au.DB_TENANT_PRIV, site_scope=other_site)
    r = await client.post(
        f"/sites/{au.DB_SITE_PRIV}/commands", json=_body(), headers=au.bearer(tok)
    )
    assert r.status_code == 403


async def test_site_without_gateway_is_409(client, base_data) -> None:
    """El sitio B2SB (tenant B) no tiene gateway comandable."""
    tok = au.make_token("tenant_admin", tenant=au.DB_TENANT_PRIV2)
    r = await client.post(
        f"/sites/{au.DB_SITE_PRIV2}/commands", json=_body(), headers=au.bearer(tok)
    )
    assert r.status_code == 409


async def test_without_any_key_config_is_503_fail_closed(client, gateway, monkeypatch) -> None:
    """Sin mapa inline NI prefijo de Secrets Manager: nada resoluble ⇒ 503."""
    monkeypatch.delenv("TAKAB_API_COMMAND_HMAC_KEYS_JSON", raising=False)
    monkeypatch.delenv("TAKAB_API_COMMAND_HMAC_SECRET_PREFIX", raising=False)
    tok = au.make_token("tenant_admin", tenant=au.DB_TENANT_PRIV)
    r = await client.post(
        f"/sites/{au.DB_SITE_PRIV}/commands", json=_body(), headers=au.bearer(tok)
    )
    assert r.status_code == 503


async def test_gateway_without_key_is_503_and_nothing_leaks(
    client, gateway, publisher: _FakePublisher, monkeypatch
) -> None:
    """Fail-closed POR GATEWAY: su thing no está en el mapa ⇒ 503, sin publish ni fila."""
    monkeypatch.setenv("TAKAB_API_COMMAND_HMAC_KEYS_JSON", json.dumps({"otro-thing": "x"}))
    tok = au.make_token("tenant_admin", tenant=au.DB_TENANT_PRIV)
    r = await client.post(
        f"/sites/{au.DB_SITE_PRIV}/commands", json=_body(), headers=au.bearer(tok)
    )
    assert r.status_code == 503
    assert publisher.published == []
    engine = get_engine()
    async with engine.begin() as conn:
        count = (
            await conn.execute(
                text("SELECT count(*) FROM commands WHERE site_id = :s"),
                {"s": au.DB_SITE_PRIV},
            )
        ).scalar_one()
    assert count == 0  # el 503 ocurre ANTES del insert: sin pending fantasma


async def test_each_gateway_signs_with_its_own_key(
    client, gateway, gateway_b, publisher: _FakePublisher
) -> None:
    """Dos gabinetes del mismo tenant: cada envelope verifica SOLO con su clave."""
    tok = au.make_token("tenant_admin", tenant=au.DB_TENANT_PRIV)
    r1 = await client.post(
        f"/sites/{au.DB_SITE_PRIV}/commands", json=_body(), headers=au.bearer(tok)
    )
    r2 = await client.post(f"/sites/{SITE_B3}/commands", json=_body(), headers=au.bearer(tok))
    assert r1.status_code == 201, r1.text
    assert r2.status_code == 201, r2.text

    by_topic = dict(publisher.published)
    env_a = by_topic[f"takab/cmd/{THING}"]
    env_b = by_topic[f"takab/cmd/{THING_B}"]
    assert env_a["sig"] == sign_command(
        KEY.encode(), canonical_payload(env_a["payload"]), env_a["nonce"], env_a["ts"]
    )
    assert env_b["sig"] == sign_command(
        KEY_B.encode(), canonical_payload(env_b["payload"]), env_b["nonce"], env_b["ts"]
    )
    # La clave de A NO verifica el comando de B: la firma liga al gateway (T-1.38).
    assert env_b["sig"] != sign_command(
        KEY.encode(), canonical_payload(env_b["payload"]), env_b["nonce"], env_b["ts"]
    )


async def test_invalid_channel_is_400(client, gateway) -> None:
    tok = au.make_token("tenant_admin", tenant=au.DB_TENANT_PRIV)
    r = await client.post(
        f"/sites/{au.DB_SITE_PRIV}/commands",
        json={"channel": "nuke", "action": "activate"},
        headers=au.bearer(tok),
    )
    assert r.status_code == 400


async def test_publish_failure_is_502_and_no_pending_row(
    client, gateway, publisher: _FakePublisher
) -> None:
    publisher.fail = True
    tok = au.make_token("tenant_admin", tenant=au.DB_TENANT_PRIV)
    r = await client.post(
        f"/sites/{au.DB_SITE_PRIV}/commands", json=_body(), headers=au.bearer(tok)
    )
    assert r.status_code == 502
    engine = get_engine()
    async with engine.begin() as conn:
        count = (
            await conn.execute(
                text("SELECT count(*) FROM commands WHERE site_id = :s"),
                {"s": au.DB_SITE_PRIV},
            )
        ).scalar_one()
    assert count == 0  # rollback: sin pending fantasma


async def test_list_commands_shows_recent(client, gateway, publisher) -> None:
    tok = au.make_token("tenant_admin", tenant=au.DB_TENANT_PRIV)
    r = await client.post(
        f"/sites/{au.DB_SITE_PRIV}/commands", json=_body(), headers=au.bearer(tok)
    )
    assert r.status_code == 201
    r = await client.get(f"/sites/{au.DB_SITE_PRIV}/commands", headers=au.bearer(tok))
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1 and items[0]["status"] == "pending"


# --- self_test (T-1.59): canal system + guardia por-acción ------------------------


async def test_self_test_issues_on_system_channel(client, gateway, publisher) -> None:
    tok = au.make_token("tenant_admin", tenant=au.DB_TENANT_PRIV)
    r = await client.post(
        f"/sites/{au.DB_SITE_PRIV}/commands",
        json={"channel": "system", "action": "self_test", "event_id": None},
        headers=au.bearer(tok),
    )
    assert r.status_code == 201, r.text
    row = r.json()
    assert (row["channel"], row["action"], row["status"]) == ("system", "self_test", "pending")
    # El envelope firmado salió al topic del gateway, como cualquier comando.
    assert len(publisher.published) == 1
    envelope = publisher.published[0][1]
    assert envelope["payload"] == {"channel": "system", "action": "self_test", "event_id": None}


@pytest.mark.parametrize(
    ("channel", "action"),
    [("siren", "self_test"), ("system", "activate"), ("system", "deactivate")],
)
async def test_self_test_channel_action_cross_is_400(client, gateway, channel, action) -> None:
    tok = au.make_token("tenant_admin", tenant=au.DB_TENANT_PRIV)
    r = await client.post(
        f"/sites/{au.DB_SITE_PRIV}/commands",
        json={"channel": channel, "action": action, "event_id": None},
        headers=au.bearer(tok),
    )
    assert r.status_code == 400


async def test_soc_operator_cannot_self_test(client, gateway) -> None:
    """soc_operator opera incidentes, no mantenimiento del gabinete (matriz)."""
    tok = au.make_token("soc_operator", tenant=au.DB_TENANT_PRIV)
    r = await client.post(
        f"/sites/{au.DB_SITE_PRIV}/commands",
        json={"channel": "system", "action": "self_test", "event_id": None},
        headers=au.bearer(tok),
    )
    assert r.status_code == 403


async def test_building_admin_can_self_test_but_not_actuate(client, gateway, publisher) -> None:
    tok = au.make_token("building_admin", tenant=au.DB_TENANT_PRIV)
    st = await client.post(
        f"/sites/{au.DB_SITE_PRIV}/commands",
        json={"channel": "system", "action": "self_test", "event_id": None},
        headers=au.bearer(tok),
    )
    assert st.status_code == 201
