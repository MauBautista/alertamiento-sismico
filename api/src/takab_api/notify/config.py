"""Destinos de notificación por tenant desde ``rule_sets.config.notifications``.

Mismo canal de configuración que quorum/dictamen (la pantalla Matriz
Multi-Tenant gestiona la cascada por tenant — blueprint §7.4). Cada canal se
valida por separado; uno inválido se omite con warning (degradación grácil).

Forma esperada::

    {"notifications": {
       "webhook":  {"url": "https://...", "secret": "..."},
       "whatsapp": {"to": "+52...", "opt_in": {"at": "2026-08-01T12:00:00Z"}},
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
            # [T-2.77] El opt-in viaja con el destino porque WhatsApp condiciona
            # CUALQUIER contacto a un consentimiento previo. No es un secreto (no
            # se poda como el `secret` del webhook): es justo lo contrario, la
            # constancia de que se puede escribir a ese número. Si se cayera por
            # el camino, el provider se negaría a enviar SIEMPRE y el canal
            # estaría muerto sin que nadie supiera por qué.
            #
            # [COSTURA T-2.79 · el interruptor de este canal]
            # Este `opt_in` es el PARCHE de T-2.77: un instante suelto que
            # cualquiera puede teclear en el `rule_set`, sin decir quién lo dio,
            # sobre qué texto ni quién lo registró. T-2.79 ya construyó el motor
            # que sí lo sabe, y su lector es
            # ``takab_api.privacy.store.whatsapp_opt_in_at(conn, tenant_id=…,
            # msisdn=…)`` — devuelve el instante del opt-in VIGENTE (y ``None``
            # si se retiró, que es algo que una fecha en el `rule_set` no puede
            # decir jamás). Está implementado y probado
            # (``tests/api/test_privacy.py::
            # test_optin_de_whatsapp_de_un_tercero_y_la_costura_que_lo_lee``).
            #
            # **Por qué el cambio no se hace AQUÍ:** esta función es PURA sobre
            # el `rule_set` y no tiene conexión a la base — enchufarla obliga a
            # mover la construcción del destino al orquestador, que es superficie
            # de T-2.77 y tiene su propia ficha (`T-2.77.b`). Hacerlo de refilón
            # rompería los tests de T-2.77 sin que esta tarea lo cubriera.
            #
            # **La forma exacta del cambio**, para que no haya que redescubrirla:
            # quien mueva esto pasa el `tenant_id` y una conexión hasta aquí (o
            # resuelve el destino en el orquestador), sustituye estas dos líneas
            # por la llamada a `whatsapp_opt_in_at`, y deja de leer `opt_in` del
            # `rule_set`. El provider NO cambia: sigue exigiendo `opt_in.at` en
            # el destino y sigue negándose a enviar sin él.
            if channel == "whatsapp" and isinstance(dest.get("opt_in"), dict):
                out[channel]["opt_in"] = dict(dest["opt_in"])
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
