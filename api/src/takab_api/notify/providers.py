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

    #: [T-2.75] ¿Este canal entrega de verdad? Es parte del CONTRATO, no un
    #: detalle: el orquestador no puede afirmar "notificado" sin que alguien
    #: se haga responsable de la entrega.
    simulated: bool

    def send(self, target: dict, message: dict) -> None:
        """Entrega ``message`` a ``target``; levanta ``NotifyError`` si falla."""
        ...


def is_simulated(provider: object) -> bool:
    """¿El provider NO entrega nada? Se deriva del propio provider — jamás de
    una lista de canales (una lista se queda ciega ante el sexto canal).

    **El default ante lo desconocido es la peor causa**: quien no se declara
    real no ha demostrado que entregue, así que se le trata como simulado. Al
    revés —presumir entrega— es exactamente la mentira que cuesta vidas: un
    tablero que dice "notificado" cuando nadie recibió nada.
    """
    return bool(getattr(provider, "simulated", True))


def _canonical_body(message: dict) -> bytes:
    """JSON canónico (claves ordenadas, sin espacios): base estable de la firma."""
    return json.dumps(message, separators=(",", ":"), sort_keys=True).encode()


class WebhookProvider:
    """POST JSON firmado: ``X-Takab-Signature`` = HMAC-SHA256 hex del body con
    el secret del tenant (re-resuelto del rule_set al despachar, nunca del job)."""

    simulated = False

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

    simulated = False

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
    """Canal SIN proveedor real (WhatsApp/SMS hasta T-2.76/T-2.77; email sin SES).

    [T-2.75] No "triunfa": se declara simulado y el orquestador marca el job
    ``simulated`` — nunca ``sent``. ``hint`` dice QUÉ falta configurar, y viaja
    con el provider para que el aviso de arranque no tenga que enumerar canales.
    """

    simulated = True

    def __init__(self, channel: str, *, hint: str = "") -> None:
        self.channel = channel
        self.hint = hint
        self.sent: list[tuple[dict, dict]] = []

    def send(self, target: dict, message: dict) -> None:
        logger.info(
            "notify[%s] SIMULADO → %s: %s",
            self.channel,
            target.get("to", target.get("url", "?")),
            message.get("headline", ""),
        )
        self.sent.append((target, message))


# [T-1.62 · T-2.75] El grito de arranque. El 13/07 hubo correos "enviados" que
# nadie recibió porque el simulado marcaba 'sent' en silencio; desde entonces el
# email grita. Ahora grita CUALQUIER canal simulado, y no porque esté en una
# lista: porque se le pregunta al registro ya construido. El sexto canal que
# alguien enchufe sin proveedor real hereda el grito sin tocar esta función.
_SIMULATED_WARNING = (
    "canal %s SIMULADO — los jobs quedarán 'simulated' (NUNCA 'sent') y nadie "
    "recibirá nada por esta vía. En producción esto es un fallo.%s"
)


def warn_simulated_channels(providers: dict[str, NotifyProvider]) -> list[str]:
    """Grita una vez por canal simulado del registro; devuelve sus nombres."""
    simulated = [channel for channel, p in providers.items() if is_simulated(p)]
    for channel in simulated:
        hint = str(getattr(providers[channel], "hint", "") or "")
        logger.warning(_SIMULATED_WARNING, channel, f" Falta: {hint}." if hint else "")
    return simulated


def build_providers(settings) -> dict[str, NotifyProvider]:
    """Providers por canal según Settings (SES si hay remitente; si no, simulado)."""
    # Import tardío: push.py/twilio.py traen dependencias propias y este módulo
    # se importa desde tests puros del plan — sin ciclo y sin costo si no se usa.
    from takab_api.notify.push import build_push_provider
    from takab_api.notify.twilio import build_sms_provider

    email: NotifyProvider
    if settings.notify_email_from:
        email = SesEmailProvider(sender=settings.notify_email_from, region=settings.aws_region)
    else:
        email = SimulatedProvider("email", hint="TAKAB_API_NOTIFY_EMAIL_FROM")
    providers: dict[str, NotifyProvider] = {
        "webhook": WebhookProvider(timeout_s=settings.notify_webhook_timeout_s),
        "whatsapp": SimulatedProvider("whatsapp", hint="proveedor de WhatsApp Business (T-2.77)"),
        # [T-2.76] Twilio si hay credenciales; si no, simulado — la presunción
        # de no-entrega se hereda sola, sin que este registro sepa nada de SMS.
        "sms": build_sms_provider(settings),
        "email": email,
        # [T-2.04] El canal push usa deliver() (lote + resultado por dispositivo);
        # el orquestador lo despacha por una rama propia, no por send().
        "push": build_push_provider(settings),  # type: ignore[dict-item]
    }
    warn_simulated_channels(providers)
    return providers
