"""Providers de la cascada (T-1.21 · B6): webhook HMAC, SES (moto), simulados."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging

import boto3
import httpx
import pytest
from moto import mock_aws

from takab_api.notify.providers import (
    _SIMULATED_WARNING,
    NotifyError,
    SesEmailProvider,
    SimulatedProvider,
    WebhookProvider,
    build_providers,
    is_simulated,
    warn_simulated_channels,
)
from takab_api.settings import Settings

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


# --- T-2.75 · quién entrega de verdad, y quién grita al arrancar -----------------


def test_los_providers_reales_se_declaran_reales() -> None:
    """Solo quien entrega puede decir que entrega."""
    assert is_simulated(WebhookProvider(timeout_s=1.0)) is False
    assert is_simulated(SesEmailProvider(sender="a@b.mx", region=_REGION)) is False
    assert is_simulated(SimulatedProvider("sms")) is True


def test_provider_que_no_se_declara_cuenta_como_simulado() -> None:
    """El default ante lo desconocido es la PEOR causa: quien no se declara real
    no ha demostrado que entregue. Al revés —presumir entrega— es la mentira."""

    class _Indeclarado:
        def send(self, target: dict, message: dict) -> None: ...

    assert is_simulated(_Indeclarado()) is True


def test_arranque_grita_por_cada_canal_simulado_del_registro(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Criterio 2: el patrón del email (grito en ``build_providers``) aplicado a
    TODOS. Sin remitente ni platform applications, los cuatro simulados gritan
    y los reales callan."""
    caplog.set_level(logging.WARNING, logger="takab_api.notify")
    providers = build_providers(Settings())

    gritados = {r.args[0] for r in caplog.records if r.msg is _SIMULATED_WARNING}
    assert gritados == {"whatsapp", "sms", "email", "push"}
    assert "webhook" not in gritados  # el único con proveedor real por defecto
    assert all("SIMULADO" in r.getMessage() for r in caplog.records if r.args)
    assert is_simulated(providers["webhook"]) is False


def test_el_grito_se_deriva_del_registro_no_de_una_lista(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """La prueba de que no hay enumeración: un canal que NO existe hoy —el sexto,
    el que alguien enchufe mañana— grita sin que nadie lo dé de alta aquí."""
    caplog.set_level(logging.WARNING, logger="takab_api.notify")
    registro = {
        "webhook": WebhookProvider(timeout_s=1.0),
        "telegram": SimulatedProvider("telegram", hint="proveedor de Telegram"),
    }
    assert warn_simulated_channels(registro) == ["telegram"]  # type: ignore[arg-type]
    mensaje = next(r.getMessage() for r in caplog.records if r.args and r.args[0] == "telegram")
    assert "SIMULADO" in mensaje
    assert "proveedor de Telegram" in mensaje  # el hint viaja con el provider


def test_el_grito_no_promete_sent() -> None:
    """El texto del aviso también aprendió: prometía "se marcarán 'sent'", que
    era justo la mentira. Ahora dice lo que de verdad va a pasar."""
    assert "'sent'" not in _SIMULATED_WARNING.replace("NUNCA 'sent'", "")
    assert "'simulated'" in _SIMULATED_WARNING
