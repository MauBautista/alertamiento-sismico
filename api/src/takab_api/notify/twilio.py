"""Canal SMS real por **Twilio** (T-2.76). Decisión ratificada 2026-08-07.

Se enchufa donde estaba ``SimulatedProvider("sms")``: mismo contrato
``NotifyProvider`` (``simulated`` + ``send()``), **cero líneas del orquestador**.

──────────────────────────────────────────────────────────────────────────────
LÍMITES DECLARADOS (criterio 2: *declarados, no descubiertos en la factura*)
──────────────────────────────────────────────────────────────────────────────
Todo lo de abajo se verificó contra la documentación de Twilio el **2026-08-07**
y está fijado en ``TWILIO_LIMITS`` con un test que se pone rojo si cambia. La
fuente va con cada número porque una razón escrita que no resiste comprobación
cuesta lo mismo que el código malo.

**Coste.** ``USD 0.1819`` por *segmento* hacia México por long code
(https://www.twilio.com/en-us/sms/pricing/mx). El número mexicano son
``USD 6.50/mes`` (local limpio) o ``USD 15/mes`` (prefijo móvil). Se cobra por
SEGMENTO, no por mensaje: ver "el acento que triplica la factura" más abajo.

**Tope de gasto.** El presupuesto de la cuenta AWS/proveedor son ``USD 50/mes``,
que a este precio son **274 segmentos al mes** y nada más. Este módulo **NO
corta** el canal al alcanzarlo: cortar el aviso de un sismo por presupuesto es
una decisión de producto, no de un provider, y se toma con el nombre de quien
la firma. Lo que sí hace es (a) **declarar** la cifra en el log de arranque, y
(b) hacer el gasto masivo **imposible por construcción**: ver "sin fan-out".

**Sin fan-out.** ``notifications.sms.to`` es **un solo número** por tenant
(``notify/config.py``): este canal es la cadena de guardia del SOC, no el
altavoz de los ocupantes — a los ocupantes los despierta el push (``push.py``),
que no cuesta por mensaje. Un incidente = **un** SMS. Un destino con lista o
comas se rechaza: así el gasto queda acotado por incidentes, no por censo de
edificio, y nadie puede convertir este canal en un difusor sin abrir una ficha.

**Límite de tasa.** El límite documentado peor —y el que se asume aquí— es
**1 segmento/segundo** por long code (https://www.twilio.com/docs/messaging/
guides/scaling-queueing-latency: "Long Codes (US): 1 MPS"; short code 100 MPS,
14 semanas de alta). Twilio **no publica** el MPS de long code en México y sí
documenta que la entrega doméstica por long code allí es "best-effort and may
be unreliable" (https://www.twilio.com/en-us/guidelines/mx/sms) ⇒ **el default
ante lo desconocido es la peor causa**: 1 MPS.

**El plazo, con ese límite.** El plan da al SMS la ventana
``notify_sms_deadline_s − notify_step_s × posición_en_la_cascada`` = **10 s**
con los valores de ``settings.py``. A 1 MPS eso son **10 segmentos**: el SLA de
30 s es alcanzable mientras no coincidan más de ~10 SMS en el mismo segundo
sobre el mismo número. Por encima, el plazo **está declarado inalcanzable**
(``sms_deadline_headroom()`` lo calcula y lo dice; no se promete en silencio).
Si un día hay más de 10 tenants con incidente simultáneo, las salidas son
comprar throughput (short code, 14 semanas) o repartir en varios números —
ficha aparte, no un parche aquí.

**Caducidad en cola.** Twilio guarda un mensaje encolado hasta **10 h
(36 000 s)** por defecto y luego lo tira con el error 30001
(https://www.twilio.com/docs/messaging/guides/account-based-throughput-overview).
Un aviso de sismo entregado 10 horas después es ruido puro, así que **cada
petición lleva ``ValidityPeriod``** (rango legal 1..36 000 s;
https://www.twilio.com/docs/messaging/api/message-resource), 300 s por defecto.

──────────────────────────────────────────────────────────────────────────────
PUBLICADO ≠ ENTREGADO
──────────────────────────────────────────────────────────────────────────────
El ``POST`` de creación devuelve ``queued`` o ``accepted``. En el vocabulario
del propio Twilio la única palabra que significa "llegó al teléfono" es
``delivered``, y esa **no viaja en esa respuesta**: llega después, por *status
callback* (https://www.twilio.com/docs/messaging/guides/
outbound-message-status-in-status-callbacks).

Consecuencia honesta, escrita aquí para que nadie la infiera al revés: cuando
este provider vuelve sin excepción, el orquestador marca el job ``sent`` y
escribe ``notify_sent``. **Eso significa "aceptado por Twilio", NO "entregado
al teléfono"** — exactamente lo mismo que ya significaba para SES (que acepta
un correo sin prometer bandeja) y para SNS. El log lo dice con todas las
letras en cada envío ("entrega NO confirmada") y ``last_receipt`` guarda el
estado crudo.

La entrega **confirmada** exige un endpoint público que reciba el callback y
valide ``X-Twilio-Signature``, más el mapeo ``MessageSid`` → job y una columna
donde escribir el desenlace tardío. Eso es superficie de API + infra y **no cabe
en esta ficha**: queda anotado como pendiente derivado dentro de `T-2.76` en
`takab-docs/TASKS.md`. Hasta entonces el estado que se marca **no se llama
"entregado"**. El parámetro ``StatusCallback`` ya viaja si hay URL configurada,
para que ese día no haya que tocar el provider.

──────────────────────────────────────────────────────────────────────────────
REINTENTOS
──────────────────────────────────────────────────────────────────────────────
Twilio ya reintenta contra la operadora y el orquestador ya reintenta con
backoff (``_BACKOFF_S``). Una tercera capa aquí dentro sería invisible y
multiplicaría duplicados, así que **este provider no reintenta nunca**.

Y Twilio **no ofrece clave de idempotencia** en el recurso Message, así que la
pone el dominio: ``(destino, incidente)``. Un fallo AMBIGUO —5xx, timeout,
respuesta ilegible— pudo haber creado el mensaje, así que se recuerda la clave
y el siguiente intento **no sale**: escala al correo en vez de arriesgar un SMS
duplicado durante un sismo. Un rechazo EXPLÍCITO (4xx) demuestra que no se creó
nada, y ese sí se puede reintentar. La memoria caduca con el ``ValidityPeriod``
—pasado ese instante Twilio ya descartó lo encolado, luego no hay nada vivo que
duplicar— y así no crece sin fin en un worker residente.

**Lo que cuesta esa elección, dicho en voz alta:** si el mensaje NO se había
creado, la guarda convierte un reintento que habría funcionado en un fallo. Se
acepta porque (a) el orquestador escala al canal siguiente en el acto, así que
el humano llega igual, y (b) cuando no hay nadie detrás, el fallo queda
ESCRITO —``notify_failed`` en rojo en la consola, con el motivo dentro— y no es
un silencio. El caso simétrico —duplicar— no lo ve nadie hasta que el teléfono
suena dos veces en mitad de una evacuación.

Credenciales por entorno / Secrets Manager (regla de oro 6). **Sin las tres
piezas el canal cae a ``SimulatedProvider`` y los jobs quedan ``simulated``,
jamás ``sent``** (T-2.75): quien no puede entregar no se declara real.
"""

from __future__ import annotations

import logging
import math
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from takab_api.notify.plan import CASCADE_ORDER
from takab_api.notify.providers import DuplicateGuard, NotifyError, SimulatedProvider

logger = logging.getLogger("takab_api.notify")

_API_ROOT = "https://api.twilio.com/2010-04-01"

# Rango legal de ValidityPeriod (docs/messaging/api/message-resource).
TWILIO_MIN_VALIDITY_S = 1
TWILIO_MAX_VALIDITY_S = 36_000


@dataclass(frozen=True)
class TwilioLimits:
    """Los números que la ficha exige DECLARAR, con su fuente."""

    cost_per_segment_usd: float
    number_rental_usd_month: float
    sender_mps: float
    queue_ttl_default_s: int
    account_budget_usd_month: float
    source: str


TWILIO_LIMITS = TwilioLimits(
    cost_per_segment_usd=0.1819,  # MX long code, verificado 2026-08-07
    number_rental_usd_month=6.50,  # "Clean Local Numbers"
    sender_mps=1.0,  # peor caso documentado (long code)
    queue_ttl_default_s=TWILIO_MAX_VALIDITY_S,  # 10 h antes del error 30001
    account_budget_usd_month=50.0,  # presupuesto de la cuenta (memoria del proyecto)
    source="https://www.twilio.com/en-us/sms/pricing/mx",
)

# --- estados de Twilio --------------------------------------------------------
#
# Una lista de "buenos" se queda ciega ante el estado que Twilio invente mañana.
# Por eso hay DOS conjuntos con papeles distintos y todo lo demás es peor caso:
#   - CONFIRMED: la única palabra que significa "llegó al teléfono".
#   - IN_FLIGHT: aceptado y en camino; NO es entrega.
# Cualquier otra cosa (incluida una futura) ⇒ NotifyError ⇒ escala al correo.
# Fallar hacia "avisa también por otro canal" es el error barato; el caro es
# dar por bueno un estado que nadie ha leído.
DELIVERY_CONFIRMED_STATUSES = frozenset({"delivered", "read"})
IN_FLIGHT_STATUSES = frozenset({"accepted", "scheduled", "queued", "sending", "sent"})
# Terminales de fallo: el mensaje NO llegará a ningún teléfono ⇒ no hay
# duplicado posible ⇒ el reintento del orquestador es seguro.
TERMINAL_FAILURE_STATUSES = frozenset({"failed", "undelivered", "canceled"})


def is_delivery_confirmed(status: str) -> bool:
    """¿Ese estado significa que el mensaje llegó al teléfono?

    ``sent`` de Twilio significa "Twilio se lo dio a la operadora", no "el
    teléfono lo tiene". Confundirlos es la mentira de T-2.75 una capa más abajo.
    """
    return status in DELIVERY_CONFIRMED_STATUSES


# --- GSM-7: el acento que triplica la factura ---------------------------------
#
# El precio es por SEGMENTO. Un solo carácter fuera del alfabeto GSM-7 pasa el
# mensaje ENTERO a UCS-2 y el segmento baja de 160 a 70 caracteres: el mismo
# texto pasa de 1 a 2 segmentos, y hasta 3 si llenaba el segmento GSM-7
# (160/67). Doble o triple coste, y doble o triple consumo del límite de tasa,
# que Twilio cuenta en *segmentos* por segundo y no en mensajes.
# "ALERTA SÍSMICA" lo dispara: la Í no existe en GSM-7 (la É y la Ñ sí).

_GSM7_BASIC = (
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
_GSM7_EXTENDED = "^{}\\[~]|€"  # cada uno cuesta DOS unidades (lleva ESC delante)
_GSM7_ALPHABET = frozenset(_GSM7_BASIC) | frozenset(_GSM7_EXTENDED)

_GSM7_SINGLE, _GSM7_MULTI = 160, 153
_UCS2_SINGLE, _UCS2_MULTI = 70, 67


@dataclass(frozen=True)
class SegmentCount:
    """Lo que de verdad se factura de un cuerpo de SMS."""

    encoding: str  # 'GSM-7' | 'UCS-2'
    units: int
    segments: int

    @property
    def cost_usd(self) -> float:
        return round(self.segments * TWILIO_LIMITS.cost_per_segment_usd, 6)


def sms_segments(body: str) -> SegmentCount:
    """Segmentos facturables de ``body`` (GSM 03.38 / UCS-2, tabla de Twilio:
    https://www.twilio.com/docs/glossary/what-sms-character-limit)."""
    if all(ch in _GSM7_ALPHABET for ch in body):
        units = sum(2 if ch in _GSM7_EXTENDED else 1 for ch in body)
        single, multi, encoding = _GSM7_SINGLE, _GSM7_MULTI, "GSM-7"
    else:
        # UTF-16: un emoji son DOS unidades (par sustituto), no una.
        units = len(body.encode("utf-16-le")) // 2
        single, multi, encoding = _UCS2_SINGLE, _UCS2_MULTI, "UCS-2"
    segments = 1 if units <= single else math.ceil(units / multi)
    return SegmentCount(encoding=encoding, units=units, segments=max(segments, 1))


def to_gsm7(text: str) -> str:
    """Pliega ``text`` al alfabeto GSM-7 **por derivación, no por tabla**.

    Se descompone en Unicode y se tiran las marcas combinantes: así ``Í→I`` y
    ``ú→u`` sin enumerar acentos, y ``Ñ``/``É``/``¿`` —que SÍ están en GSM-7—
    sobreviven intactos. Lo irrepresentable (emoji, hanzi) desaparece y los
    huecos se colapsan. El resultado es total: para CUALQUIER entrada devuelve
    algo que ``sms_segments`` codifica como GSM-7.

    No es cosmética: es la diferencia entre pagar 1 segmento y pagar 3, y entre
    consumir 1 s de MPS y consumir 3 dentro de una ventana de 10 s.
    """
    out: list[str] = []
    for char in text:
        if char in _GSM7_ALPHABET:
            out.append(char)
            continue
        folded = "".join(
            c
            for c in unicodedata.normalize("NFKD", char)
            if not unicodedata.combining(c) and c in _GSM7_ALPHABET
        )
        out.append(folded if folded else " ")
    return " ".join("".join(out).split())


def _truncate_gsm7(text: str, budget: int) -> str:
    """Corta a ``budget`` unidades GSM-7 sin partir un carácter de extensión."""
    used, kept = 0, []
    for char in text:
        cost = 2 if char in _GSM7_EXTENDED else 1
        if used + cost > budget:
            break
        used += cost
        kept.append(char)
    return "".join(kept).rstrip()


def compose_sms_body(message: dict) -> str:
    """Cuerpo del SMS: GSM-7 y **un solo segmento**, pase lo que pase.

    Se construye sobre el ``headline`` que ya arma el orquestador (que distingue
    incidente / solicitud de dictamen / personas en riesgo), así que no hay un
    segundo catálogo de textos que se desincronice. Se trunca el titular —donde
    vive el nombre del sitio— y **nunca la referencia del incidente**: eso es lo
    que el operador teclea en la consola.
    """
    headline = str(message.get("headline") or "TAKAB Ailert: notificacion de incidente")
    incident = str(message.get("incident_id") or "")
    tail = f" #{incident[:8]}" if incident else ""
    budget = _GSM7_SINGLE - len(tail)
    return _truncate_gsm7(to_gsm7(headline), budget) + tail


# --- límites frente al SLA ----------------------------------------------------


@dataclass(frozen=True)
class DeadlineHeadroom:
    """¿Cabe el SLA del SMS dentro del límite de tasa declarado?"""

    position: int
    window_s: float
    mps: float
    max_segments: int

    @property
    def reachable(self) -> bool:
        return self.max_segments > 0


def sms_deadline_headroom(settings) -> DeadlineHeadroom:
    """Cuántos segmentos caben en la ventana que el PLAN le deja al SMS.

    La posición se lee de ``CASCADE_ORDER``, no se copia: si alguien reordena la
    cascada, la ventana se recalcula sola en vez de quedarse mintiendo.
    """
    position = CASCADE_ORDER.index("sms")
    window_s = settings.notify_sms_deadline_s - settings.notify_step_s * position
    mps = TWILIO_LIMITS.sender_mps
    return DeadlineHeadroom(
        position=position,
        window_s=window_s,
        mps=mps,
        max_segments=max(int(window_s * mps), 0),
    )


def messages_per_budget(budget_usd: float) -> int:
    """Segmentos que compra ``budget_usd`` al precio declarado. $50 = 274."""
    return int(budget_usd / TWILIO_LIMITS.cost_per_segment_usd)


def resolve_validity_period_s(raw: float) -> int:
    """``ValidityPeriod`` legal (1..36 000 s). Fuera de rango se ajusta y GRITA.

    No revienta: una cifra mal puesta en un env no puede tumbar el canal por el
    que se avisa de un sismo. Pero tampoco se corrige en silencio.
    """
    value = int(round(raw))
    clamped = min(max(value, TWILIO_MIN_VALIDITY_S), TWILIO_MAX_VALIDITY_S)
    if clamped != value:
        logger.warning(
            "notify[sms] ValidityPeriod %s fuera del rango de Twilio (%s..%s): se usa %s",
            value,
            TWILIO_MIN_VALIDITY_S,
            TWILIO_MAX_VALIDITY_S,
            clamped,
        )
    return clamped


# --- el provider --------------------------------------------------------------


@dataclass(frozen=True)
class TwilioReceipt:
    """Lo que Twilio contestó. Observabilidad, **no** prueba de entrega."""

    sid: str
    status: str
    segments: int
    encoding: str
    cost_usd: float

    @property
    def delivery_confirmed(self) -> bool:
        return is_delivery_confirmed(self.status)


class TwilioSmsProvider:
    """SMS por la REST API de Twilio, detrás del contrato ``NotifyProvider``.

    Habla HTTP directo con ``httpx`` (ya es dependencia y es lo que usa
    ``WebhookProvider``) en vez del SDK: una dependencia menos y un transporte
    inyectable, que es lo que permite probar todo esto **sin una sola llamada
    de red**.
    """

    simulated = False

    def __init__(
        self,
        *,
        account_sid: str,
        auth_token: str,
        from_number: str,
        messaging_service_sid: str = "",
        timeout_s: float = 5.0,
        validity_period_s: int = 300,
        status_callback_url: str = "",
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        # Ni una operación falible aquí: un constructor que revienta deja al
        # worker sin arrancar y, con él, sin ningún canal de aviso.
        self._account_sid = account_sid
        self._auth_token = auth_token
        self._from_number = from_number
        self._messaging_service_sid = messaging_service_sid
        self._timeout_s = timeout_s
        self._validity_period_s = validity_period_s
        self._status_callback_url = status_callback_url
        self._transport = transport
        self._url = f"{_API_ROOT}/Accounts/{account_sid}/Messages.json"
        # (destino, incidente) → instante en que deja de poder duplicar. El TTL
        # es el ValidityPeriod: pasado ese instante Twilio ya descartó lo
        # encolado, luego no queda nada vivo que duplicar. [T-2.77] La mecánica
        # es común con WhatsApp y vive en providers.DuplicateGuard.
        self._guard = DuplicateGuard(clock=clock or time.monotonic)
        self.last_receipt: TwilioReceipt | None = None

    # -- guarda de duplicados --------------------------------------------------

    @property
    def pending_keys(self) -> int:
        """Claves vivas en la guarda (para comprobar que no se acumulan)."""
        return self._guard.pending

    def _already_issued(self, key: tuple[str, str]) -> bool:
        return self._guard.seen(key)

    def _remember(self, key: tuple[str, str]) -> None:
        """Marca que ese (destino, incidente) puede tener un mensaje VIVO."""
        self._guard.remember(key, self._validity_period_s)

    # -- envío -----------------------------------------------------------------

    def _scrub(self, text: str) -> str:
        """El token jamás sale en un error ni en un log (regla de oro 6)."""
        return text.replace(self._auth_token, "***") if self._auth_token else text

    def send(self, target: dict, message: dict) -> None:
        to = target.get("to")
        if not isinstance(to, str) or not to.strip():
            raise NotifyError("sms sin destinatario")
        if "," in to or ";" in to:
            # Cortafuegos de gasto: este canal es la guardia del SOC, no un
            # difusor. Un abanico se abre con una ficha y un presupuesto, no
            # metiendo comas en un rule_set.
            raise NotifyError("sms: un destino por mensaje (este canal no hace fan-out)")
        to = to.strip()

        key = (to, str(message.get("incident_id") or ""))
        if self._already_issued(key):
            raise NotifyError(
                "sms: posible duplicado — ya se emitió un mensaje para este incidente "
                "a este número y pudo estar en vuelo; se escala en vez de duplicar"
            )

        body = compose_sms_body(message)
        count = sms_segments(body)
        data = {
            "To": to,
            "Body": body,
            "ValidityPeriod": str(self._validity_period_s),
        }
        if self._messaging_service_sid:
            data["MessagingServiceSid"] = self._messaging_service_sid
        else:
            data["From"] = self._from_number
        if self._status_callback_url:
            data["StatusCallback"] = self._status_callback_url

        try:
            with httpx.Client(timeout=self._timeout_s, transport=self._transport) as client:
                response = client.post(
                    self._url, data=data, auth=(self._account_sid, self._auth_token)
                )
        except httpx.HTTPError as exc:
            # AMBIGUO: la petición pudo llegar y crear el mensaje.
            self._remember(key)
            raise NotifyError(f"twilio: sin respuesta ({type(exc).__name__})") from None

        if response.status_code >= 500:
            # AMBIGUO igual: un 5xx puede venir después de haber creado.
            self._remember(key)
            raise NotifyError(f"twilio: HTTP {response.status_code} (envío incierto)")
        if response.status_code >= 400:
            # Rechazo EXPLÍCITO: no se creó nada ⇒ el reintento es seguro.
            motivo = f"twilio: HTTP {response.status_code} {_detail(response)}"
            raise NotifyError(self._scrub(motivo))

        try:
            payload = response.json()
        except ValueError:
            self._remember(key)
            raise NotifyError("twilio: respuesta ilegible (envío incierto)") from None

        sid = str(payload.get("sid") or "")
        status = str(payload.get("status") or "")
        if not sid:
            self._remember(key)
            raise NotifyError("twilio: respuesta sin sid (envío incierto)")
        if status in TERMINAL_FAILURE_STATUSES:
            # No llegará a ningún teléfono: sin duplicado posible, sin recordar.
            raise NotifyError(self._scrub(f"twilio: mensaje {sid} en estado {status}"))
        if status not in IN_FLIGHT_STATUSES and not is_delivery_confirmed(status):
            self._remember(key)
            raise NotifyError(f"twilio: estado desconocido {status!r} (mensaje {sid})")

        self._remember(key)
        self.last_receipt = TwilioReceipt(
            sid=sid,
            status=status,
            segments=count.segments,
            encoding=count.encoding,
            cost_usd=count.cost_usd,
        )
        confirmada = "CONFIRMADA" if is_delivery_confirmed(status) else "NO confirmada"
        logger.info(
            "notify[sms] twilio sid=%s status=%s · entrega %s · %d segmento(s) %s ~USD %.4f",
            sid,
            status,
            confirmada,
            count.segments,
            count.encoding,
            count.cost_usd,
        )


def _detail(response: httpx.Response) -> str:
    """Motivo legible del rechazo de Twilio (``code``/``message``), acotado."""
    try:
        payload = response.json()
    except ValueError:
        return response.text[:200]
    code = payload.get("code")
    detail = str(payload.get("message") or "")[:200]
    return f"[{code}] {detail}" if code else detail


# --- construcción -------------------------------------------------------------

SMS_HINT = (
    "TAKAB_API_NOTIFY_SMS_ACCOUNT_SID + TAKAB_API_NOTIFY_SMS_AUTH_TOKEN + "
    "TAKAB_API_NOTIFY_SMS_FROM (o _MESSAGING_SERVICE_SID)"
)


def build_sms_provider(settings):
    """Twilio si están las TRES piezas; si no, simulado (T-2.75).

    Media credencial es cero credencial, y además grita: un canal a medio
    configurar que se creyera real marcaría ``sent`` sin entregar nada, que es
    justo lo que T-2.75 acaba de erradicar.
    """
    account_sid = (settings.notify_sms_account_sid or "").strip()
    auth_token = (settings.notify_sms_auth_token or "").strip()
    from_number = (settings.notify_sms_from or "").strip()
    service_sid = (settings.notify_sms_messaging_service_sid or "").strip()

    faltan = [
        name
        for name, value in (
            ("account_sid", account_sid),
            ("auth_token", auth_token),
            ("from/messaging_service_sid", from_number or service_sid),
        )
        if not value
    ]
    if faltan:
        if len(faltan) < 3:
            logger.error(
                "canal sms: credenciales de Twilio A MEDIAS (falta %s) — el canal NO "
                "asciende a real; los jobs quedarán 'simulated' y nadie recibirá un SMS.",
                ", ".join(faltan),
            )
        return SimulatedProvider("sms", hint=SMS_HINT)

    validity = resolve_validity_period_s(settings.notify_sms_validity_period_s)
    headroom = sms_deadline_headroom(settings)
    logger.info(
        "canal sms REAL (twilio) · coste USD %.4f/segmento + USD %.2f/mes de número · "
        "%.0f MPS declarado · ValidityPeriod %ss (default de Twilio: %ss) · "
        "presupuesto USD %.0f/mes = %d segmentos · SLA de %.0fs %s "
        "(ventana %.0fs ⇒ %d segmento(s))",
        TWILIO_LIMITS.cost_per_segment_usd,
        TWILIO_LIMITS.number_rental_usd_month,
        TWILIO_LIMITS.sender_mps,
        validity,
        TWILIO_LIMITS.queue_ttl_default_s,
        TWILIO_LIMITS.account_budget_usd_month,
        messages_per_budget(TWILIO_LIMITS.account_budget_usd_month),
        settings.notify_sms_deadline_s,
        "ALCANZABLE" if headroom.reachable else "INALCANZABLE",
        headroom.window_s,
        headroom.max_segments,
    )
    if not settings.notify_sms_status_callback_url:
        logger.warning(
            "canal sms: sin StatusCallback configurado ⇒ NO hay confirmación de entrega. "
            "Un 'notify_sent' de sms significa ACEPTADO POR TWILIO, no entregado al teléfono."
        )
    return TwilioSmsProvider(
        account_sid=account_sid,
        auth_token=auth_token,
        from_number=from_number,
        messaging_service_sid=service_sid,
        timeout_s=settings.notify_sms_timeout_s,
        validity_period_s=validity,
        status_callback_url=(settings.notify_sms_status_callback_url or "").strip(),
    )
