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
import time
from collections.abc import Callable, Mapping
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


def channel_reality(providers: Mapping[str, NotifyProvider]) -> dict[str, bool]:
    """``{canal: ¿simulado?}`` DERIVADO del registro ya construido (T-2.75.a).

    Ni una lista de canales: se recorre el registro y se le pregunta a cada
    provider, con el mismo ``is_simulated`` que usa el guard del orquestador. El
    sexto canal que alguien enchufe en ``build_providers`` aparece aquí solo, y
    aparece con la presunción correcta (simulado) si no se declara.

    Existe porque esta verdad **moría en el log**: el worker la grita al
    arrancar y la consola no tenía a quién preguntársela, así que rotulaba
    «SIMULADO en el MVP» a fuego — y ese rótulo se volvería mentira, al revés,
    el día que el canal ascendiera a real.
    """
    return {channel: is_simulated(provider) for channel, provider in providers.items()}


class DuplicateStore(Protocol):
    """[T-2.77.c] Dónde vive el recuerdo de "esto pudo salir ya"."""

    def seen(self, key: tuple[str, str]) -> bool: ...

    def remember(self, key: tuple[str, str], ttl_s: float) -> None: ...


class SharedNotifyState(Protocol):
    """[T-2.77.c] El estado del subsistema que sobrevive al proceso.

    Lo implementa ``notify.state.PgNotifyState`` sobre la conexión de la pasada.
    Es la unión de las DOS memorias que la ficha encontró en RAM: la guarda de
    duplicados (``DuplicateStore``) y la cuarentena de plantillas.
    """

    def seen(self, key: tuple[str, str]) -> bool: ...

    def remember(self, key: tuple[str, str], ttl_s: float) -> None: ...

    def quarantined(self, channel: str) -> Mapping[str, str]: ...

    def quarantine(self, channel: str, name: str, reason: str) -> None: ...


def bind_state(providers: Mapping[str, object], state: SharedNotifyState | None) -> list[str]:
    """Entrega el estado COMPARTIDO a los providers que lo acepten.

    **Derivado, no enumerado**, igual que ``warn_simulated_channels``: se le
    pregunta a cada provider si sabe recibirlo. El canal que alguien enchufe
    mañana con memoria propia hereda el estado compartido sin tocar esta función,
    y el que no tenga nada que recordar —el correo, el webhook— no se entera de
    que existe. Devuelve los canales atados (para poder afirmarlo en un test).
    """
    atados: list[str] = []
    for channel, provider in providers.items():
        bind = getattr(provider, "bind_state", None)
        if callable(bind):
            bind(state)
            atados.append(channel)
    return atados


def provider_message_id(provider: object) -> str:
    """[T-2.77.b] Identificador que el PROVEEDOR le dio al último mensaje.

    Es con lo que el webhook de estado casará el desenlace tardío, y hasta hoy
    moría en el recibo en memoria del worker. Sale del recibo por una propiedad
    con el MISMO nombre en los dos providers (``TwilioReceipt.message_id``,
    y su gemela del canal de plantilla), no de una rama por canal: el
    orquestador no puede saber que uno se llama SID y el otro no.

    Un provider sin recibo —SES, el webhook firmado— devuelve cadena vacía, y el
    orquestador no escribe nada. No hay nada que casar donde no hay callback.
    """
    receipt = getattr(provider, "last_receipt", None)
    return str(getattr(receipt, "message_id", "") or "")


def _canonical_body(message: dict) -> bytes:
    """JSON canónico (claves ordenadas, sin espacios): base estable de la firma."""
    return json.dumps(message, separators=(",", ":"), sort_keys=True).encode()


class DuplicateGuard:
    """Memoria corta de "esto pudo salir ya" (T-2.76 · T-2.77).

    Ni Twilio ni la Cloud API de Meta ofrecen clave de idempotencia en su
    endpoint de envío, así que la pone el dominio: ``(destino, incidente)``. Un
    fallo AMBIGUO —5xx, timeout, respuesta ilegible— pudo haber creado el
    mensaje, así que se recuerda la clave y el siguiente intento **no sale**:
    escala al canal siguiente en vez de arriesgar un aviso duplicado durante un
    sismo. Un rechazo EXPLÍCITO (4xx) demuestra que no se creó nada, y ese sí se
    puede reintentar — por eso recordar es una decisión de quien llama.

    **Lo que cuesta esa elección, dicho en voz alta:** si el mensaje NO se había
    creado, la guarda convierte un reintento que habría funcionado en un fallo.
    Se acepta porque (a) el orquestador escala al canal siguiente en el acto, y
    (b) el fallo queda ESCRITO (``notify_failed``, rojo en la consola). El caso
    simétrico —duplicar— no lo ve nadie hasta que el teléfono suena dos veces en
    mitad de una evacuación.

    El TTL lo pone el llamante con la ventana de vida real del mensaje en el
    proveedor (``ValidityPeriod`` en Twilio, ``message_send_ttl_seconds`` en
    Meta): pasado ese instante el proveedor ya descartó lo encolado, luego no
    queda nada vivo que duplicar. Así la memoria tampoco crece sin fin en un
    worker residente.

    [T-2.77.c] **Y esa memoria dejó de ser la de un proceso.** Con más de una
    instancia del worker la guarda no existía entre instancias, así que el
    duplicado seguía siendo posible; y el supuesto de "un solo worker" ya estaba
    contradicho por el orquestador de al lado, que usa ``pg_advisory_xact_lock``
    justamente porque asume varias. Cuando alguien le ata un ``store``
    (``notify.state.PgNotifyState``, vía ``bind_state``), recordar y preguntar
    van a la BASE y el recuerdo es de todos. Sin ``store`` —la API, un test
    puro— se comporta exactamente como antes: la mecánica de CUÁNDO recordar no
    cambia una línea, solo DÓNDE.
    """

    def __init__(
        self, clock: Callable[[], float] | None = None, store: DuplicateStore | None = None
    ) -> None:
        self._clock = clock or time.monotonic
        self._issued: dict[tuple[str, str], float] = {}
        self._store = store

    def bind(self, store: DuplicateStore | None) -> None:
        """Ata (o suelta) el almacén COMPARTIDO de la guarda."""
        self._store = store

    @property
    def pending(self) -> int:
        """Claves vivas EN MEMORIA (para comprobar que no se acumulan)."""
        return len(self._issued)

    def seen(self, key: tuple[str, str]) -> bool:
        if self._store is not None:
            return self._store.seen(key)
        now = self._clock()
        self._issued = {k: exp for k, exp in self._issued.items() if exp > now}
        return key in self._issued

    def remember(self, key: tuple[str, str], ttl_s: float) -> None:
        """Marca que esa clave puede tener un mensaje VIVO durante ``ttl_s``."""
        if self._store is not None:
            self._store.remember(key, ttl_s)
            return
        self._issued[key] = self._clock() + ttl_s


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


#: [T-2.104 · T-2.157] Cómo se NOMBRA cada origen. No se compone con el valor
#: crudo del `trigger` ni se rotula todo igual: un incidente que no viene de la
#: alerta oficial NO puede presentarse como suyo, y ése es exactamente el defecto
#: que llegó a un teléfono en T-2.104 —titular a fuego para las cuatro fuentes—.
#: Un `trigger` desconocido cae a su propio texto en vez de a SASMEX: si algún día
#: aparece una fuente nueva, el correo dirá que no la reconoce, no la atribuirá.
_ORIGENES = {
    "sasmex": "Alerta oficial SASMEX recibida en el inmueble",
    "rules": "Detección instrumental del sensor del inmueble",
    "quorum": "Confirmación por varios inmuebles de la red",
    "manual": "Activación manual desde el inmueble",
}


def cuerpo_email(message: dict) -> str:
    """[T-2.157] El cuerpo que lee una PERSONA.

    Antes era ``json.dumps(message, indent=2, sort_keys=True)``: catorce claves
    en orden alfabético, con la nota del solicitante entre dos UUID. Funcionaba y
    no comunicaba, que es la misma familia de defecto que `T-2.104`.

    El orden no es estético, es operativo: **qué pasa, dónde, qué se te pide y la
    nota** arriba; los identificadores al pie, porque no son información para el
    destinatario sino para quien atienda el reporte después.
    """
    lineas: list[str] = []
    sitio = message.get("site_name") or message.get("site_code") or "inmueble sin nombre"
    kind = message.get("kind")

    # 1. QUÉ pasa. Primero y en una línea: es lo que se lee de pie y con prisa.
    if kind == "damage_people_at_risk":
        lineas += ["PERSONAS EN RIESGO", ""]
        lineas.append(f"Se reportaron personas en riesgo en {sitio}.")
    elif kind == "dictamen_request":
        lineas.append(f"Se solicita un dictamen de habitabilidad para {sitio}.")
    else:
        severidad = message.get("severity") or "sin clasificar"
        lineas.append(f"Incidente {severidad} en {sitio}.")

    # 2. DE DÓNDE viene la alerta, nombrada por lo que es.
    origen = _ORIGENES.get(str(message.get("trigger") or ""))
    if origen:
        lineas += ["", f"Origen: {origen}."]

    # 3. La NOTA, si la hay: es lo único que escribió una persona, y va arriba.
    nota = (message.get("note") or "").strip()
    if nota:
        lineas += ["", "Nota de quien lo solicita:", f"  {nota}"]

    quien = message.get("requested_by") or message.get("reported_by")
    if quien:
        verbo = "Reportado por" if kind == "damage_people_at_risk" else "Solicitado por"
        lineas.append(f"{verbo}: {quien}")

    # 4. El enlace. Si no viene, NO se inventa (regla de oro 7).
    enlace = message.get("link")
    if enlace:
        lineas += ["", f"Atender en la consola: {enlace}"]

    # 5. Al pie, lo que sirve para soporte y no para decidir.
    pie = [
        ("Inmueble", message.get("site_code")),
        ("Apertura", message.get("opened_at")),
        ("Incidente", message.get("incident_id")),
        ("Evento", message.get("event_id")),
    ]
    detalle = [f"{k}: {v}" for k, v in pie if v]
    if detalle:
        lineas += ["", "-- ", "Datos para soporte:"] + [f"  {d}" for d in detalle]

    lineas += [
        "",
        "Este aviso lo genera TAKAB Ailert para el personal que su organización",
        "registró en la consola. Para dejar de recibirlo, solicite su baja al",
        "administrador de su organización.",
    ]
    return "\n".join(lineas)


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
        body_text = cuerpo_email(message)
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
    # Import tardío: push.py/twilio.py/whatsapp.py traen dependencias propias y
    # este módulo se importa desde tests puros del plan — sin ciclo (whatsapp.py
    # importa de aquí) y sin costo si no se usa.
    from takab_api.notify.push import build_push_provider
    from takab_api.notify.twilio import build_sms_provider
    from takab_api.notify.whatsapp import build_whatsapp_provider

    email: NotifyProvider
    if settings.notify_email_from:
        email = SesEmailProvider(sender=settings.notify_email_from, region=settings.aws_region)
    else:
        email = SimulatedProvider("email", hint="TAKAB_API_NOTIFY_EMAIL_FROM")
    providers: dict[str, NotifyProvider] = {
        "webhook": WebhookProvider(timeout_s=settings.notify_webhook_timeout_s),
        # [T-2.77] WhatsApp Cloud si hay credenciales Y una plantilla APROBADA;
        # si falta cualquiera de las dos, el canal se declara simulado él solo.
        "whatsapp": build_whatsapp_provider(settings),
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
