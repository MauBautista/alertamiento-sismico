"""Destinos de notificación por tenant desde ``rule_sets.config.notifications``.

Mismo canal de configuración que quorum/dictamen (la pantalla Matriz
Multi-Tenant gestiona la cascada por tenant — blueprint §7.4). Cada canal se
valida por separado; uno inválido se omite con warning (degradación grácil).

Forma esperada::

    {"notifications": {
       "webhook":  {"url": "https://...", "secret": "..."},
       "whatsapp": {"to": "+52..."},
       "sms":      {"to": "+52..."},
       "email":    {"to": ["ops@...", ...]}   # o string único
    }}
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def resolve_destinations(config: dict | None) -> dict[str, dict]:
    """Destinos válidos por canal (canal inválido/ausente → omitido + log)."""
    raw = config.get("notifications") if isinstance(config, dict) else None
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict] = {}

    webhook = raw.get("webhook")
    if isinstance(webhook, dict) and isinstance(webhook.get("url"), str) and webhook["url"]:
        out["webhook"] = {k: webhook[k] for k in ("url", "secret") if k in webhook}
    elif webhook is not None:
        logger.warning("notifications.webhook inválido (falta url) → omitido")

    for channel in ("whatsapp", "sms"):
        dest = raw.get(channel)
        if isinstance(dest, dict) and isinstance(dest.get("to"), str) and dest["to"]:
            out[channel] = {"to": dest["to"]}
        elif dest is not None:
            logger.warning("notifications.%s inválido (falta to) → omitido", channel)

    email = raw.get("email")
    if email is not None:
        to = email.get("to") if isinstance(email, dict) else None
        if isinstance(to, str) and to:
            to = [to]
        if isinstance(to, list) and to and all(isinstance(x, str) and x for x in to):
            out["email"] = {"to": list(to)}
        else:
            logger.warning("notifications.email inválido (sin destinatarios) → omitido")

    return out


def resolve_inspector_emails(config: dict | None) -> list[str]:
    """Correos del INSPECTOR (``notifications.inspector_emails``, T-1.61).

    Lista SEPARADA de ``notifications.email`` a propósito: aquel es el ops del
    tenant (cascada de incidentes); este es la audiencia profesional de las
    solicitudes de dictamen. Sin lista válida ⇒ [] (el orquestador loguea y
    omite — degradación grácil, jamás inventa destinatarios).
    """
    raw = config.get("notifications") if isinstance(config, dict) else None
    if not isinstance(raw, dict):
        return []
    emails = raw.get("inspector_emails")
    if isinstance(emails, str) and emails:
        return [emails]
    if isinstance(emails, list) and all(isinstance(x, str) and x for x in emails):
        return list(emails)
    if emails is not None:
        logger.warning("notifications.inspector_emails inválido → omitido")
    return []
