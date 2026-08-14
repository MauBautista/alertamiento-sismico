"""[T-2.77.b] Webhooks de estado de entrega — la ÚNICA superficie pública de la API.

Hasta hoy tres canales decían ``notify_sent`` queriendo decir «el proveedor lo
aceptó»: el correo («SES lo aceptó»), el SMS («Twilio lo encoló») y WhatsApp
(«Meta lo aceptó»). Ninguno afirmaba que un humano lo tuviera en la mano. Aquí
llega la otra mitad del hecho: el desenlace TARDÍO.

──────────────────────────────────────────────────────────────────────────────
ESTO SALE DEL SOBRE DE AUTENTICACIÓN DE TODA LA API, Y HAY QUE TRATARLO ASÍ
──────────────────────────────────────────────────────────────────────────────
No puede ir detrás de Cognito: quien llama es Twilio o Meta y no tienen un token
nuestro. **La firma es la única autenticación.** De ahí salen cinco decisiones,
todas con test:

1. **Sin firma válida no se toca la base, ni para BUSCAR el job.** La conexión se
   abre después de verificar, nunca antes. Un test lo mide saboteando
   ``delivery_conn``: si el router la tocara, revienta.
2. **Una firma mala y un identificador inexistente contestan LO MISMO** —404 con
   el mismo cuerpo—, así que desde fuera no se puede averiguar qué jobs hay.
   Adentro sí se distinguen: van al log con su motivo, que es donde lo lee quien
   opera y no quien llama.
3. **La comparación es en tiempo constante** (``hmac.compare_digest``, en
   ``notify/callbacks.py``). Un ``==`` sobre un HMAC filtra el prefijo correcto
   por temporización y con eso se fabrica una firma válida byte a byte.
4. **El secreto sale de la configuración** (regla de oro 6) y su ausencia es
   fail-closed **RUIDOSO**: 503. Que falte NUESTRO secreto es un error de
   despliegue, no información sobre los jobs, así que aquí sí se distingue —
   contestar 404 dejaría un canal muerto para siempre sin que nadie supiera por
   qué.
5. **El cuerpo está acotado** (``MAX_BODY_BYTES``): nadie puede hacernos leer
   megabytes en memoria para después comprobar que la firma no valía.

Y una que no se ve: **la URL con la que se valida a Twilio sale de la
CONFIGURACIÓN** (``notify_sms_status_callback_url``, la misma que viaja en el
``StatusCallback`` de cada envío), no de las cabeceras del request. Twilio firma
``url + parámetros``; si la URL se reconstruyera con ``Host`` /
``X-Forwarded-Proto``, quien llama controlaría parte del material firmado y
podría hacer casar una firma capturada en otro sitio.

──────────────────────────────────────────────────────────────────────────────
POR QUÉ ESCRIBE POR UNA FUNCIÓN Y NO CON UN UPDATE
──────────────────────────────────────────────────────────────────────────────
Este request no trae sesión, luego no hay ``app.tenant_id`` ni ``app.role``. La
API conecta como ``takab_app``, que sobre ``notification_jobs`` tiene SELECT y
nada más y cuya RLS es default-deny con FORCE: ni con un GRANT UPDATE podría
escribir. Y ``takab_app`` **no puede** volverse ``takab_ingest`` (el DSN lo dice
con todas las letras: "La API NUNCA usa takab_ingest").

Así que escribe por ``app_notify_delivery`` (0040), ``SECURITY DEFINER`` con
dueño ``takab_ingest``, ``REVOKE ... FROM PUBLIC`` y EXECUTE solo para
``takab_app`` — el mismo patrón de ``gov_ack_incident``. Lo que se abre no es
«escribir en notification_jobs»: es «mover el desenlace de UN job identificado
por un id de proveedor, y solo hacia adelante».

──────────────────────────────────────────────────────────────────────────────
REENVÍOS Y CALLBACKS FUERA DE ORDEN
──────────────────────────────────────────────────────────────────────────────
Los dos proveedores REINTENTAN y no garantizan el orden. La regla no es «gana el
último»: es que un estado solo pisa a los de rango inferior
(``callbacks.outranked_by``). Un reenvío del mismo callback no se pisa a sí mismo
⇒ es inerte. Un ``sent`` retrasado no borra un ``delivered``. Un ``failed`` tardío
sí pone en rojo un job que estaba verde —el caso que hoy no se ve y el que más
duele— pero no borra una entrega ya confirmada. Y lo que no reconocemos no toca
nada.
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from urllib.parse import parse_qsl

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import text

from takab_api.db.session import SessionCtx, get_tenant_conn
from takab_api.notify import callbacks as cb
from takab_api.routers._common import http_error
from takab_api.schemas.notify_webhooks import NotifyWebhookAck
from takab_api.settings import Settings

logger = logging.getLogger("takab_api.notify")

router = APIRouter()

#: Tope del cuerpo aceptado. Un ``StatusCallback`` de Twilio son ~1 KB y el lote
#: de estados más grande de Meta no llega a decenas; 64 KiB deja margen de sobra
#: y convierte "mándale 2 GB al endpoint sin autenticar" en un 413 barato.
MAX_BODY_BYTES = 64 * 1024

#: LA MISMA respuesta para "tu firma no vale" y para "no conozco ese
#: identificador". Es el punto entero: desde fuera no se puede averiguar qué
#: jobs existen. La diferencia se escribe en el log, no en el cuerpo.
_NO_RECONOCIDO = "callback no reconocido"

_ACK = NotifyWebhookAck()

# `string_to_array` y no un array enlazado: pasa por cualquier driver sin depender
# de cómo adapte listas, y una cadena vacía produce {""} — que no casa con ningún
# estado real, o sea el no-op correcto para un estado de rango mínimo.
_APPLY_SQL = text(
    """
SELECT o_job_id, o_applied, o_job_status, o_last_status, o_delivered_at
FROM app_notify_delivery(
  :channel, :message_id, :status, string_to_array(:outranks, ','),
  :delivered, :undelivered, CAST(:at AS timestamptz), :detail)
"""
)


@asynccontextmanager
async def delivery_conn():
    """Conexión de esta superficie: ``takab_app`` y SIN contexto de tenant.

    No es un descuido que vaya vacía: no hay sesión de la que sacarlo, y por eso
    lo único que esta conexión puede hacer sobre ``notification_jobs`` es
    ejecutar ``app_notify_delivery``. Con la RLS default-deny de la tabla, un
    SELECT directo desde aquí no devolvería ni una fila — que es exactamente la
    garantía que se quiere.

    Es una función del módulo, y no una llamada en línea, para que un test pueda
    sabotearla y comprobar que un cuerpo sin firma válida no llega hasta aquí.
    """
    async with get_tenant_conn(
        SessionCtx(tenant_id="", role="", user_id=""), set_session_role="takab_app"
    ) as conn:
        yield conn


async def _read_body(request: Request) -> bytes:
    """Cuerpo CRUDO y acotado.

    Crudo porque la firma de Meta se calcula sobre los bytes tal cual llegaron:
    re-serializar el JSON cambiaría espacios y orden y la firma dejaría de casar.
    Acotado porque esto no pide credenciales a nadie.
    """
    declarado = request.headers.get("content-length", "")
    if declarado.isdigit() and int(declarado) > MAX_BODY_BYTES:
        raise http_error(413, "cuerpo demasiado grande")
    trozos: list[bytes] = []
    total = 0
    async for trozo in request.stream():
        total += len(trozo)
        if total > MAX_BODY_BYTES:
            raise http_error(413, "cuerpo demasiado grande")
        trozos.append(trozo)
    return b"".join(trozos)


def _rechazo(proveedor: str, motivo: str) -> Exception:
    """404 idéntico para todos los rechazos; el motivo REAL va al log."""
    logger.warning("notify[callback %s] rechazado: %s", proveedor, motivo)
    return http_error(404, _NO_RECONOCIDO)


# =============================================================================
# TWILIO · X-Twilio-Signature
# =============================================================================


@router.post("/notify/webhooks/twilio", response_model=NotifyWebhookAck, status_code=202)
async def twilio_status_callback(request: Request) -> NotifyWebhookAck:
    """``StatusCallback`` de Twilio (formulario), firmado con el auth token."""
    settings = Settings()
    token = (settings.notify_sms_auth_token or "").strip()
    url = (settings.notify_sms_status_callback_url or "").strip()
    if not token or not url:
        # Fail-closed RUIDOSO: sin token no se puede verificar NADA, y sin la URL
        # configurada no se sabe sobre qué firmó Twilio. Aceptar por no poder
        # comprobar convertiría esto en "cualquiera marca entregado lo que no salió".
        logger.error(
            "notify[callback twilio]: falta el auth token o la URL de callback en la "
            "configuración; el endpoint responde 503 y NO hay confirmación de entrega"
        )
        raise http_error(503, "el callback de estado no está configurado en este despliegue")

    cuerpo = await _read_body(request)
    params = dict(parse_qsl(cuerpo.decode("utf-8", "replace"), keep_blank_values=True))
    firma = request.headers.get(cb.TWILIO_SIGNATURE_HEADER, "")
    if not cb.verify_twilio_signature(auth_token=token, url=url, params=params, signature=firma):
        raise _rechazo("twilio", "firma no válida")

    return await _apply("twilio", cb.parse_twilio_form(params))


# =============================================================================
# META · X-Hub-Signature-256 (+ el hub.verify_token del alta)
# =============================================================================


@router.get("/notify/webhooks/meta", response_class=PlainTextResponse)
async def meta_verify(request: Request) -> PlainTextResponse:
    """El apretón de manos con el que Meta da de alta la suscripción.

    Meta llama UNA vez con ``hub.verify_token`` y espera de vuelta el
    ``hub.challenge`` tal cual, en texto plano. El token se compara en tiempo
    constante como cualquier otro secreto: es corto y adivinable byte a byte con
    un ``==``.
    """
    esperado = (Settings().notify_whatsapp_verify_token or "").strip()
    if not esperado:
        logger.error(
            "notify[callback meta]: falta el verify token en la configuración; la "
            "suscripción del webhook no se puede dar de alta"
        )
        raise http_error(503, "el callback de estado no está configurado en este despliegue")

    q = request.query_params
    if q.get("hub.mode") != "subscribe":
        raise _rechazo("meta", "hub.mode inesperado")
    if not cb.verify_meta_token(expected=esperado, received=q.get("hub.verify_token", "")):
        raise _rechazo("meta", "hub.verify_token no válido")
    return PlainTextResponse(q.get("hub.challenge", ""))


@router.post("/notify/webhooks/meta", response_model=NotifyWebhookAck, status_code=202)
async def meta_status_callback(request: Request) -> NotifyWebhookAck:
    """Webhook de estado de Meta, firmado con el app secret sobre el cuerpo crudo."""
    secreto = (Settings().notify_whatsapp_app_secret or "").strip()
    if not secreto:
        logger.error(
            "notify[callback meta]: falta el app secret en la configuración; el endpoint "
            "responde 503 y NO hay confirmación de entrega"
        )
        raise http_error(503, "el callback de estado no está configurado en este despliegue")

    cuerpo = await _read_body(request)
    firma = request.headers.get(cb.META_SIGNATURE_HEADER, "")
    if not cb.verify_meta_signature(app_secret=secreto, body=cuerpo, header=firma):
        raise _rechazo("meta", "firma no válida")

    try:
        payload = json.loads(cuerpo)
    except ValueError:
        # Firmado pero ilegible: no hay hechos que contar. No se reintenta nada.
        payload = None
    return await _apply("meta", cb.parse_meta_payload(payload))


# =============================================================================
# LA ESCRITURA
# =============================================================================


async def _apply(proveedor: str, eventos: list[cb.DeliveryEvent]) -> NotifyWebhookAck:
    """Aplica los hechos del callback. La base se toca AQUÍ y no antes.

    Un cuerpo firmado sin hechos que contar —Meta manda los mensajes entrantes
    por este mismo webhook— se acusa y ya: no es un error y no hay nada que
    reintentar. Lo que sí se rechaza es un cuerpo cuyos identificadores no
    conocemos, y se rechaza con el MISMO 404 que una firma mala.
    """
    if not eventos:
        logger.info(
            "notify[callback %s]: cuerpo sin estados de entrega; nada que aplicar", proveedor
        )
        return _ACK

    atendidos = 0
    async with delivery_conn() as conn:
        for evento in eventos:
            if cb.rank(evento.status) is None:
                # Estado que Twilio o Meta inventaron después de esto: no tiene
                # rango, así que no puede pisar nada. Se acusa —el proveedor no
                # nos debe un reintento— y se GRITA, porque significa que el
                # vocabulario de `callbacks.py` se quedó corto.
                logger.warning(
                    "notify[callback %s]: estado desconocido %r (mensaje %s); no se aplica",
                    proveedor,
                    evento.status,
                    evento.message_id,
                )
                atendidos += 1
                continue
            if await _aplicar_uno(conn, evento):
                atendidos += 1

    if atendidos == 0:
        raise _rechazo(proveedor, "ningún identificador de este cuerpo casa con un job")
    return _ACK


async def _aplicar_uno(conn, evento: cb.DeliveryEvent) -> bool:
    """Un hecho contra su job. Devuelve si el identificador existía."""
    fila = (
        await conn.execute(
            _APPLY_SQL,
            {
                "channel": evento.channel,
                "message_id": evento.message_id,
                "status": evento.status,
                "outranks": ",".join(cb.outranked_by(evento.status)),
                "delivered": cb.is_delivered(evento.channel, evento.status),
                "undelivered": cb.is_undelivered(evento.channel, evento.status),
                "at": (evento.at or datetime.now(tz=UTC)).isoformat(),
                "detail": evento.detail,
            },
        )
    ).first()
    if fila is None:
        return False

    logger.info(
        "notify[callback %s] job %s estado %s (%s) · entrega %s",
        evento.channel,
        fila.o_job_id,
        evento.status,
        "aplicado" if fila.o_applied else "sin efecto (reenvío o fuera de orden)",
        "CONFIRMADA" if fila.o_delivered_at else "no confirmada",
    )
    return True
