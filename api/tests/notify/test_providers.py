"""Providers de la cascada (T-1.21 · B6): webhook HMAC, SES (moto), simulados."""

from __future__ import annotations

import hashlib
import hmac
import json

import boto3
import httpx
import pytest
from moto import mock_aws

from takab_api.notify.providers import (
    NotifyError,
    SesEmailProvider,
    SimulatedProvider,
    WebhookProvider,
)

MESSAGE = {
    "incident_id": "11111111-0000-0000-0000-000000000001",
    "severity": "warning",
    "site_name": "Torre A",
    "headline": "TAKAB Ailert · Incidente warning · Torre A",
}

_REGION = "us-east-2"


# ------------------------------------------------------------------- webhook


def _provider_and_capture(handler) -> WebhookProvider:
    return WebhookProvider(timeout_s=2.0, transport=httpx.MockTransport(handler))


def test_webhook_signs_body_with_hmac_sha256() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content
        seen["sig"] = request.headers["X-Takab-Signature"]
        seen["ctype"] = request.headers["content-type"]
        return httpx.Response(200)

    provider = _provider_and_capture(handler)
    provider.send({"url": "https://soc.example.mx/hook", "secret": "s3cr3t"}, MESSAGE)

    expected = hmac.new(b"s3cr3t", seen["body"], hashlib.sha256).hexdigest()
    assert seen["sig"] == expected
    assert seen["ctype"] == "application/json"
    assert json.loads(seen["body"])["incident_id"] == MESSAGE["incident_id"]


def test_webhook_http_error_raises_notify_error() -> None:
    provider = _provider_and_capture(lambda _req: httpx.Response(500))
    with pytest.raises(NotifyError):
        provider.send({"url": "https://soc.example.mx/hook", "secret": "x"}, MESSAGE)


def test_webhook_network_failure_raises_notify_error() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout")

    provider = _provider_and_capture(handler)
    with pytest.raises(NotifyError):
        provider.send({"url": "https://soc.example.mx/hook", "secret": "x"}, MESSAGE)


def test_webhook_without_url_raises_notify_error() -> None:
    provider = _provider_and_capture(lambda _req: httpx.Response(200))
    with pytest.raises(NotifyError):
        provider.send({"secret": "x"}, MESSAGE)


# ----------------------------------------------------------------- SES email


def test_ses_sends_email_to_targets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", _REGION)
    with mock_aws():
        ses = boto3.client("ses", region_name=_REGION)
        ses.verify_email_identity(EmailAddress="alertas@takab.mx")

        provider = SesEmailProvider(sender="alertas@takab.mx", region=_REGION)
        provider.send({"to": ["ops@example.mx"]}, MESSAGE)

        assert ses.get_send_quota()["SentLast24Hours"] >= 1


def test_ses_unverified_sender_raises_notify_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", _REGION)
    with mock_aws():
        provider = SesEmailProvider(sender="nadie@takab.mx", region=_REGION)
        with pytest.raises(NotifyError):
            provider.send({"to": ["ops@example.mx"]}, MESSAGE)


def test_ses_without_recipients_raises_notify_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", _REGION)
    with mock_aws():
        provider = SesEmailProvider(sender="alertas@takab.mx", region=_REGION)
        with pytest.raises(NotifyError):
            provider.send({"to": []}, MESSAGE)


# ---------------------------------------------------------------- simulados


def test_simulated_provider_records_and_succeeds() -> None:
    provider = SimulatedProvider("whatsapp")
    provider.send({"to": "+5255"}, MESSAGE)
    assert provider.sent == [({"to": "+5255"}, MESSAGE)]
