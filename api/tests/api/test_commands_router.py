"""Command service HTTP (T-1.23 · B9): emitir/listar comandos firmados.

Patrón del conftest de B2 (client/app, tenants A/B/G). El publisher IoT se
sustituye por un fake vía dependency override; la clave HMAC va por env.
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
def _hmac_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAKAB_API_COMMAND_HMAC_KEY", KEY)


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


async def test_without_hmac_key_is_503_fail_closed(client, gateway, monkeypatch) -> None:
    monkeypatch.delenv("TAKAB_API_COMMAND_HMAC_KEY", raising=False)
    tok = au.make_token("tenant_admin", tenant=au.DB_TENANT_PRIV)
    r = await client.post(
        f"/sites/{au.DB_SITE_PRIV}/commands", json=_body(), headers=au.bearer(tok)
    )
    assert r.status_code == 503


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
