"""Grant service del backfill (T-1.25): identidad + key canónica + presign."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest

from takab_api.backfill.grants import canonical_key, handle_backfill_request
from takab_api.commands.publisher import PublishError
from takab_api.contracts.meta import Meta
from takab_api.ingest.handlers import GatewayCtx
from takab_api.settings import Settings

THING = "gw-grant-test"
TENANT = "d0000000-0000-0000-0000-0000000000aa"
SHA = "a" * 64


class _FakePublisher:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.published: list[tuple[str, dict]] = []

    def publish(self, topic: str, payload: bytes) -> None:
        if self.fail:
            raise PublishError("iot caído (simulado)")
        self.published.append((topic, json.loads(payload)))


def _ctx() -> GatewayCtx:
    return GatewayCtx(
        gateway_id=uuid.uuid4(),
        gateway_serial=THING,
        iot_thing=THING,
        tenant_id=uuid.UUID(TENANT),
        tenant_code="dev",
        site_id=uuid.uuid4(),
        site_code="site",
        sensors={},
    )


def _meta(thing: str = THING, principal: str | None = None) -> Meta:
    return Meta(
        principal=principal if principal is not None else thing,
        topic=f"takab/backfill/request/{thing}",
        ts_iot=datetime(2026, 7, 7, 12, 0, 0, tzinfo=UTC),
    )


def _payload(mode: str = "backfill", **over: object) -> dict:
    base: dict = {
        "kind": "backfill_request",
        "request_id": uuid.uuid4().hex,
        "mode": mode,
        "ts_from": "2026-07-07T06:00:00+00:00",
        "ts_to": "2026-07-07T12:00:00+00:00",
        "lines": 21600,
        "event_id": "",
        "sha256": "",
    }
    base.update(over)
    return base


def _settings() -> Settings:
    return Settings(
        transfer_bucket="takab-dev-transfer",
        evidence_bucket="takab-dev-evidence",
        backfill_presign_ttl_s=900.0,
    )


@pytest.fixture(autouse=True)
def _aws_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-2")


def test_backfill_grant_has_canonical_key_and_presigned_url() -> None:
    publisher = _FakePublisher()
    ok, reason = handle_backfill_request(_payload(), _meta(), _ctx(), publisher, _settings())
    assert ok, reason
    topic, grant = publisher.published[0]
    assert topic == f"takab/backfill/grant/{THING}"
    assert grant["kind"] == "backfill_grant"
    assert grant["mode"] == "backfill"
    assert grant["key"] == f"backfill/{THING}/20260707T060000Z_20260707T120000Z.ndjson.gz"
    assert "takab-dev-transfer" in grant["url"]
    assert grant["key"].replace("/", "%2F") in grant["url"] or grant["key"] in grant["url"]
    assert grant["expires_at"]


def test_evidence_grant_key_carries_tenant_from_registry() -> None:
    """La key es autoridad de la NUBE: tenant del registry, no del payload."""
    publisher = _FakePublisher()
    event = uuid.uuid4().hex
    ok, _ = handle_backfill_request(
        _payload(mode="evidence", event_id=event, sha256=SHA),
        _meta(),
        _ctx(),
        publisher,
        _settings(),
    )
    assert ok
    grant = publisher.published[0][1]
    assert grant["key"] == f"evidence/{TENANT}/{event}/{SHA}.mseed"
    assert "takab-dev-evidence" in grant["url"]


def test_principal_topic_mismatch_rejected() -> None:
    publisher = _FakePublisher()
    ok, reason = handle_backfill_request(
        _payload(), _meta(principal="gw-otro"), _ctx(), publisher, _settings()
    )
    assert not ok and "mismatch" in reason
    assert publisher.published == []


def test_evidence_without_valid_sha_rejected() -> None:
    publisher = _FakePublisher()
    ok, _ = handle_backfill_request(
        _payload(mode="evidence", event_id="e1", sha256="corto"),
        _meta(),
        _ctx(),
        publisher,
        _settings(),
    )
    assert not ok
    assert publisher.published == []


def test_missing_bucket_is_fail_closed() -> None:
    publisher = _FakePublisher()
    ok, reason = handle_backfill_request(
        _payload(), _meta(), _ctx(), publisher, Settings(transfer_bucket="")
    )
    assert not ok and "bucket" in reason
    assert publisher.published == []


def test_publish_failure_reports_error() -> None:
    ok, reason = handle_backfill_request(
        _payload(), _meta(), _ctx(), _FakePublisher(fail=True), _settings()
    )
    assert not ok and "publish" in reason


def test_canonical_key_unknown_mode_none() -> None:
    assert canonical_key({"mode": "nuke"}, _ctx(), THING) is None
