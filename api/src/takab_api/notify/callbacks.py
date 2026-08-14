"""Desenlace TARDÍO de una notificación: firma, parseo y orden (T-2.77.b).

Hasta hoy tres canales decían ``notify_sent`` queriendo decir «el proveedor lo
aceptó»: el correo («SES lo aceptó»), el SMS («Twilio lo encoló») y WhatsApp
(«Meta lo aceptó»). Ninguno podía afirmar que un humano lo tuviera en la mano.
Era honesto —está escrito en los tres sitios— pero era **una tarea sin hacer**.

Este módulo es la mitad PURA de esa tarea: verificar la firma del callback,
convertir el cuerpo del proveedor en hechos, y saber ORDENAR esos hechos. La
mitad sucia —el endpoint público y la escritura— vive en
``routers/notify_webhooks.py``.

──────────────────────────────────────────────────────────────────────────────
LA FIRMA ES LA ÚNICA AUTENTICACIÓN
──────────────────────────────────────────────────────────────────────────────
El endpoint no puede estar detrás de Cognito: quien llama es Twilio o Meta, y no
tienen un token nuestro. Sale, por tanto, del sobre de autenticación de toda la
API. Consecuencias que este módulo asume por escrito:

1. **Comparación en tiempo constante, siempre** (``hmac.compare_digest``). Un
   ``==`` sobre un HMAC filtra el prefijo correcto por temporización, y con eso
   se fabrica una firma válida byte a byte. Lo ancla un test que lee esta fuente.
2. **Fail-closed sin secreto.** Sin secreto configurado no se valida nada: se
   devuelve ``False``. Aceptar por no poder comprobar convertiría esto en
   «cualquiera marca entregado lo que no salió».
3. **La URL de Twilio sale de la CONFIGURACIÓN, no de las cabeceras.** Twilio
   firma ``url + parámetros ordenados``
   (https://www.twilio.com/docs/usage/security#validating-signatures). Si la URL
   se reconstruyera con ``Host``/``X-Forwarded-Proto``, quien llama controlaría
   parte del material firmado y podría hacer casar una firma capturada en otro
   sitio. La URL que se usa aquí es la MISMA que viaja en ``StatusCallback``
   (``settings.notify_sms_status_callback_url``), que es exactamente lo que
   Twilio firmó.

``verify_*`` devuelve un booleano y **no** levanta: quien decide qué contestar
—y qué NO contar— es el router, en un solo sitio.

──────────────────────────────────────────────────────────────────────────────
EL ORDEN DE LOS ESTADOS · reenvíos y callbacks fuera de orden
──────────────────────────────────────────────────────────────────────────────
Los dos proveedores REINTENTAN sus callbacks y **no garantizan el orden**: un
``delivered`` puede llegar antes que el ``sent`` que lo precedió. Así que el
desenlace no se escribe «el último que llegue gana»: se escribe por RANGO, y un
estado solo pisa a los que están por debajo. De ahí salen las tres propiedades
que la ficha pide:

* un **reenvío** del mismo callback no cambia nada (un estado no se pisa a sí
  mismo, así que la segunda vez no aplica);
* un ``sent`` retrasado **no** hace retroceder un ``delivered``;
* un ``failed`` tardío **sí** pisa a ``sent`` (el job acaba en rojo, que es el
  caso que hoy no se ve y el que más duele), pero **no** pisa a una entrega ya
  confirmada: una entrega es un hecho ocurrido y no la borra un callback
  posterior.

Y lo que no se reconoce no se toca: un estado que Twilio o Meta inventen mañana
no tiene rango, no pisa a nadie y no cuenta como entrega. El default ante lo
desconocido es la peor causa, igual que en el resto del subsistema.

**Qué significa cada palabra lo dicen los providers, no este módulo**:
``is_delivered`` delega en ``twilio.is_delivery_confirmed`` /
``whatsapp.is_delivery_confirmed``, que ya existían con esa regla exacta. Una
segunda copia aquí sería la fuente de la próxima divergencia.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from takab_api.notify import twilio as _twilio
from takab_api.notify import whatsapp as _whatsapp

logger = logging.getLogger("takab_api.notify")

#: Cabeceras de firma de cada proveedor.
TWILIO_SIGNATURE_HEADER = "X-Twilio-Signature"
META_SIGNATURE_HEADER = "X-Hub-Signature-256"

#: Canal de cada proveedor dentro de nuestra cascada.
CHANNEL_TWILIO = "sms"
CHANNEL_META = "whatsapp"

#: Prefijo obligatorio de la firma de Meta (docs/graph-api/webhooks/getting-started
#: — "the SHA256 signature ... prefixed with sha256=").
_META_PREFIX = "sha256="


# =============================================================================
# FIRMAS
# =============================================================================


def twilio_signature(*, auth_token: str, url: str, params: Mapping[str, str]) -> str:
    """La firma que Twilio habría puesto: base64(HMAC-SHA1(url + k+v ordenados)).

    SHA-1 no es una elección nuestra: es el algoritmo que Twilio usa para
    ``X-Twilio-Signature`` y el único con el que su firma casa. Se usa como MAC
    con clave secreta (no como resumen de integridad), que es el uso donde
    SHA-1 sigue siendo aceptable; y encima de él va la comparación en tiempo
    constante de abajo.
    """
    material = url + "".join(k + str(params[k]) for k in sorted(params))
    mac = hmac.new(auth_token.encode(), material.encode("utf-8"), hashlib.sha1)
    return base64.b64encode(mac.digest()).decode()


def verify_twilio_signature(
    *, auth_token: str, url: str, params: Mapping[str, str], signature: str
) -> bool:
    """¿Ese ``X-Twilio-Signature`` corresponde a estos parámetros y a esta URL?

    Fail-closed sin token y comparación en tiempo constante sobre los BYTES
    decodificados (dos base64 distintos pueden decodificar a lo mismo; comparar
    el texto dejaría pasar variantes de relleno).
    """
    if not auth_token or not signature:
        return False
    try:
        recibida = base64.b64decode(signature.strip(), validate=True)
    except (binascii.Error, ValueError):
        return False
    esperada = base64.b64decode(twilio_signature(auth_token=auth_token, url=url, params=params))
    return hmac.compare_digest(recibida, esperada)


def verify_meta_signature(*, app_secret: str, body: bytes, header: str) -> bool:
    """¿Ese ``X-Hub-Signature-256`` corresponde al cuerpo CRUDO recibido?

    Sobre los bytes tal cual llegaron, nunca sobre el JSON re-serializado: un
    re-serializado cambia espacios y orden y la firma dejaría de casar (o, peor,
    obligaría a normalizar y abriría un hueco).
    """
    if not app_secret or not header:
        return False
    marca = header.strip()
    if not marca.startswith(_META_PREFIX):
        return False
    try:
        recibida = bytes.fromhex(marca[len(_META_PREFIX) :])
    except ValueError:
        return False
    esperada = hmac.new(app_secret.encode(), body, hashlib.sha256).digest()
    return hmac.compare_digest(recibida, esperada)


def verify_meta_token(*, expected: str, received: str) -> bool:
    """El ``hub.verify_token`` del alta del webhook de Meta.

    Es un secreto compartido que Meta devuelve UNA vez, al suscribir el
    endpoint. Mismo trato que una firma: fail-closed y tiempo constante — es
    corto y adivinable byte a byte si se compara con ``==``.
    """
    if not expected or not received:
        return False
    return hmac.compare_digest(expected.encode(), received.encode())


# =============================================================================
# LOS HECHOS
# =============================================================================


@dataclass(frozen=True)
class DeliveryEvent:
    """Un desenlace tardío contado por el proveedor. Todavía sin casar con nada."""

    channel: str
    message_id: str
    status: str
    at: datetime | None = None
    detail: str = ""


def parse_twilio_form(form: Mapping[str, str]) -> list[DeliveryEvent]:
    """Un ``StatusCallback`` de Twilio ⇒ 0 o 1 hechos.

    Se aceptan los dos juegos de nombres (``MessageSid``/``MessageStatus`` y los
    antiguos ``SmsSid``/``SmsStatus``) porque Twilio manda unos u otros según la
    antigüedad del recurso; sin SID o sin estado no hay hecho que contar.
    """
    sid = str(form.get("MessageSid") or form.get("SmsSid") or "").strip()
    status = str(form.get("MessageStatus") or form.get("SmsStatus") or "").strip().lower()
    if not sid or not status:
        return []
    code = str(form.get("ErrorCode") or "").strip()
    detail = f"twilio: {status}" + (f" [{code}]" if code else "")
    return [DeliveryEvent(channel=CHANNEL_TWILIO, message_id=sid, status=status, detail=detail)]


def parse_meta_payload(payload: object) -> list[DeliveryEvent]:
    """Un webhook de Meta ⇒ los hechos de estado que traiga (puede traer varios).

    **Defensivo a propósito**: es una superficie pública y por el MISMO webhook
    llegan cosas que no son desenlaces nuestros (mensajes entrantes, cambios de
    la cuenta). Un cuerpo firmado pero deforme se ignora entero en vez de
    reventar el proceso: aquí un 500 sería un denegado de servicio de un campo.
    """
    eventos: list[DeliveryEvent] = []
    if not isinstance(payload, dict):
        return eventos
    for entry in _as_list(payload.get("entry")):
        for change in _as_list(_get(entry, "changes")):
            value = _get(change, "value")
            for status in _as_list(_get(value, "statuses")):
                evento = _meta_status(status)
                if evento is not None:
                    eventos.append(evento)
    return eventos


def _meta_status(raw: object) -> DeliveryEvent | None:
    if not isinstance(raw, dict):
        return None
    wa_id = str(raw.get("id") or "").strip()
    status = str(raw.get("status") or "").strip().lower()
    if not wa_id or not status:
        return None
    errores = [
        str(e.get("code"))
        for e in _as_list(raw.get("errors"))
        if isinstance(e, dict) and e.get("code")
    ]
    detail = f"meta: {status}" + (f" [{', '.join(errores)}]" if errores else "")
    return DeliveryEvent(
        channel=CHANNEL_META,
        message_id=wa_id,
        status=status,
        at=_unix(raw.get("timestamp")),
        detail=detail,
    )


def _as_list(value: object) -> list:
    return value if isinstance(value, list) else []


def _get(container: object, key: str) -> object:
    return container.get(key) if isinstance(container, dict) else None


def _unix(raw: object) -> datetime | None:
    """El ``timestamp`` de Meta (segundos unix, a veces como cadena)."""
    try:
        return datetime.fromtimestamp(int(str(raw)), tz=UTC)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


# =============================================================================
# EL ORDEN
# =============================================================================

#: Rango de cada estado conocido. No es una escala de "bondad": es el ORDEN en
#: que los hechos pueden ocurrir, y sirve para una sola cosa — decidir si un
#: callback que llega ahora cuenta más que el que ya está escrito.
#:
#: · Los de VUELO (encolado/aceptado/retenido/enviado) suben poco a poco.
#: · La ENTREGA (30) y la LECTURA (40) están por encima de todo lo demás, y por
#:   eso ningún fallo tardío las pisa: una entrega es un hecho ocurrido.
#: · El FALLO (25) está por encima del vuelo y por debajo de la entrega: pisa a
#:   ``sent`` —que es el caso de la ficha, el job que se queda verde para
#:   siempre— y no puede borrar un ``delivered``.
STATUS_RANK: dict[str, int] = {
    "scheduled": 5,
    "queued": 10,
    "accepted": 10,
    "sending": 15,
    "held_for_quality_assessment": 15,
    "sent": 20,
    "canceled": 25,
    "failed": 25,
    "undelivered": 25,
    "delivered": 30,
    "read": 40,
}

#: El vocabulario completo, para quien tenga que recorrerlo (tests incluidos).
KNOWN_STATUSES: tuple[str, ...] = tuple(STATUS_RANK)


def rank(status: str) -> int | None:
    """Rango del estado, o ``None`` si no lo conocemos."""
    return STATUS_RANK.get(status)


def outranked_by(status: str) -> tuple[str, ...]:
    """Los estados que ``status`` puede PISAR.

    Se devuelve la lista explícita —y no un número— porque el que decide es la
    base: ``app_notify_delivery`` compara contra ``last_status`` con un
    ``= ANY(...)``. Así el vocabulario vive en UN sitio (aquí) y la función SQL
    se queda siendo mecanismo puro, sin una segunda copia de la escala que
    pueda derivar de ésta.

    Y por construcción, lo que NO está en la lista no se pisa: ni el propio
    estado (de ahí que un reenvío sea inerte) ni un estado desconocido que
    hubiera quedado escrito.
    """
    mio = rank(status)
    if mio is None:
        return ()
    return tuple(s for s, r in STATUS_RANK.items() if r < mio)


def is_delivered(channel: str, status: str) -> bool:
    """¿Ese estado significa que el mensaje llegó al teléfono?

    La regla NO se reinventa aquí: la ponen los providers, que ya la traían
    (``T-2.76``/``T-2.77``). ``accepted``, ``queued``, ``sent`` y
    ``held_for_quality_assessment`` **no** son entregas.
    """
    if channel == CHANNEL_META:
        return _whatsapp.is_delivery_confirmed(status)
    return _twilio.is_delivery_confirmed(status)


def is_undelivered(channel: str, status: str) -> bool:
    """¿Ese estado declara que el mensaje NO llegará?

    Mismo criterio: los conjuntos terminales de fallo son los de cada provider.
    """
    if channel == CHANNEL_META:
        return status in _whatsapp.DELIVERY_FAILED_STATUSES
    return status in _twilio.TERMINAL_FAILURE_STATUSES
