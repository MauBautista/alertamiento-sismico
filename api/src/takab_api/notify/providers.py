"""Providers de la cascada (T-1.21 · B6). Pluggables por canal.

Decisión ratificada (plan maestro): **SES real en sandbox** para email (con
``notify_email_from`` verificado) + **simulados** para WhatsApp/SMS en dev —
las rutas dedicadas (WhatsApp Business Cloud API, SMS Telcel/AT&T) se enchufan
aquí sin tocar el orquestador. El webhook es real (httpx) con firma HMAC.

TODO externo (no bloquea dev): DKIM/SPF del correo requieren dominio propio
verificado en SES producción (blueprint §5.6).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Protocol

import boto3
import httpx
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger("takab_api.notify")


class NotifyError(Exception):
    """Fallo de entrega de un canal (dispara la escalación de la cascada)."""


class NotifyProvider(Protocol):
    """Contrato mínimo de un canal de notificación."""

    def send(self, target: dict, message: dict) -> None:
        """Entrega ``message`` a ``target``; levanta ``NotifyError`` si falla."""
        ...


def _canonical_body(message: dict) -> bytes:
    """JSON canónico (claves ordenadas, sin espacios): base estable de la firma."""
    return json.dumps(message, separators=(",", ":"), sort_keys=True).encode()


class WebhookProvider:
    """POST JSON firmado: ``X-Takab-Signature`` = HMAC-SHA256 hex del body con
    el secret del tenant (re-resuelto del rule_set al despachar, nunca del job)."""

    def __init__(self, timeout_s: float, transport: httpx.BaseTransport | None = None) -> None:
        self._timeout_s = timeout_s
        self._transport = transport

    def send(self, target: dict, message: dict) -> None:
        url = target.get("url")
        if not url:
            raise NotifyError("webhook sin url configurada")
        body = _canonical_body(message)
        secret = str(target.get("secret") or "")
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        headers = {"Content-Type": "application/json", "X-Takab-Signature": signature}
        try:
            with httpx.Client(timeout=self._timeout_s, transport=self._transport) as client:
                response = client.post(url, content=body, headers=headers)
        except httpx.HTTPError as exc:
            raise NotifyError(f"webhook: {exc!r}") from exc
        if response.status_code >= 400:
            raise NotifyError(f"webhook: HTTP {response.status_code}")


class SesEmailProvider:
    """Correo vía AWS SES (sandbox en dev: remitente y destinos verificados)."""

    def __init__(self, sender: str, region: str) -> None:
        self._sender = sender
        self._region = region

    def send(self, target: dict, message: dict) -> None:
        recipients = list(target.get("to") or [])
        if not recipients:
            raise NotifyError("email sin destinatarios")
        subject = message.get("headline", "TAKAB Ailert · Notificación de incidente")
        body_text = json.dumps(message, indent=2, ensure_ascii=False, sort_keys=True)
        client = boto3.client("ses", region_name=self._region)
        try:
            client.send_email(
                Source=self._sender,
                Destination={"ToAddresses": recipients},
                Message={
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {"Text": {"Data": body_text, "Charset": "UTF-8"}},
                },
            )
        except (BotoCoreError, ClientError) as exc:
            raise NotifyError(f"ses: {exc}") from exc


class SimulatedProvider:
    """Canal simulado (WhatsApp/SMS en dev; email sin SES configurado):
    registra la entrega y triunfa. La ruta real se enchufa sin tocar nada más."""

    def __init__(self, channel: str) -> None:
        self.channel = channel
        self.sent: list[tuple[dict, dict]] = []

    def send(self, target: dict, message: dict) -> None:
        logger.info(
            "notify[%s] SIMULADO → %s: %s",
            self.channel,
            target.get("to", target.get("url", "?")),
            message.get("headline", ""),
        )
        self.sent.append((target, message))


def build_providers(settings) -> dict[str, NotifyProvider]:
    """Providers por canal según Settings (SES si hay remitente; si no, simulado)."""
    email: NotifyProvider
    if settings.notify_email_from:
        email = SesEmailProvider(sender=settings.notify_email_from, region=settings.aws_region)
    else:
        email = SimulatedProvider("email")
    return {
        "webhook": WebhookProvider(timeout_s=settings.notify_webhook_timeout_s),
        "whatsapp": SimulatedProvider("whatsapp"),
        "sms": SimulatedProvider("sms"),
        "email": email,
    }
