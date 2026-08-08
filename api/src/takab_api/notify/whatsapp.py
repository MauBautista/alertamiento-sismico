"""Canal WhatsApp Business por **plantilla preaprobada** (T-2.77).

Se enchufa donde estaba ``SimulatedProvider("whatsapp")``: mismo contrato
``NotifyProvider`` (``simulated`` + ``send()``), **cero líneas del orquestador**.

Todo lo que sigue se verificó contra la documentación de Meta el **2026-08-07**
y la URL va pegada al dato, porque una razón escrita que no resiste comprobación
cuesta lo mismo que el código malo.

──────────────────────────────────────────────────────────────────────────────
LO QUE HACE ESTE CANAL DISTINTO A TODOS LOS DEMÁS: NO SE PUEDE IMPROVISAR TEXTO
──────────────────────────────────────────────────────────────────────────────
"Template messages are the only type of message that can be sent to WhatsApp
users outside of a customer service window"
(https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/overview).

Esa ventana la abre **el usuario**: "When a WhatsApp user messages you or calls
you, a 24-hour timer called a customer service window starts... When the window
closes, you can only send pre-approved template messages"
(https://developers.facebook.com/documentation/business-messaging/whatsapp/messages/send-messages).

Aquí el destinatario es la guardia del SOC y **nunca escribió primero**: la
ventana está SIEMPRE cerrada. Luego este canal es **100 % plantilla**, siempre,
sin caso alterno. Un mensaje de texto libre no llegaría: rebotaría con el error
131047 ("Over 24 hours since recipient's last reply",
https://developers.facebook.com/docs/whatsapp/cloud-api/support/error-codes/).

Y una plantilla no es una cadena en el código: es un **artefacto que Meta revisa
y aprueba**, cuyo texto vive en los servidores de Meta. Nosotros solo enviamos
el NOMBRE y los parámetros. De ahí sale todo el diseño de abajo.

──────────────────────────────────────────────────────────────────────────────
EL ARTEFACTO (criterio 1: plantillas aprobadas y VERSIONADAS EN EL REPO)
──────────────────────────────────────────────────────────────────────────────
``whatsapp_templates/*.json``, un fichero por plantilla, con tres bloques:

* ``template`` — **literalmente** el cuerpo de ``POST /<WABA_ID>/message_templates``
  (``name``, ``language``, ``category``, ``components``, ``parameter_format``,
  ``message_send_ttl_seconds``; https://developers.facebook.com/documentation/
  business-messaging/whatsapp/reference/whatsapp-business-account/message-template-api).
  **JSON y no YAML ni un literal de Python** justamente por eso: si el fichero
  del repo no es *exactamente* lo que se le manda a Meta hay una traducción en
  medio, y la traducción es el sitio donde el texto aprobado y el texto del repo
  se separan sin que nadie lo note. Un literal de Python, además, invita a meter
  f-strings dentro de lo que tiene que estar congelado.
* ``binding`` — de dónde sale cada ``{{n}}``. Es NUESTRO, no viaja a Meta.
* ``approval`` — el sello: ``status`` (el enum de Meta) y ``approved_digest``.

**El candado que hace que cambiar el texto EXIJA volver a aprobar.** Meta guarda
el texto; nosotros mandamos el nombre. Editar el cuerpo en el repo sin volver a
pasar por Meta **no cambia lo que lee la gente**: crea una divergencia silenciosa
entre lo que el repo afirma y lo que llega al teléfono. Por eso el sello es el
**digest del bloque que Meta revisó**: mover una coma mueve el digest y la
plantilla deja de estar aprobada en el acto. Dicho con honestidad: esto atrapa la
deriva accidental (que es la que ocurre), no a quien reescriba el digest a
propósito — ningún mecanismo dentro del repo puede atrapar eso.

──────────────────────────────────────────────────────────────────────────────
CRITERIO 2 · EL CANAL CAE, NO FINGE
──────────────────────────────────────────────────────────────────────────────
Meta pausa y deshabilita plantillas **por su cuenta**, por calidad: "Paused:
paused due to recurring negative feedback from customers, or low read-rates —
cannot be sent to customers"; "Disabled: ... cannot be sent to customers"
(templates/overview, arriba). El enum completo de estado tiene diez valores
(``APPROVED, ARCHIVED, DELETED, DISABLED, IN_APPEAL, LIMIT_EXCEEDED, PAUSED,
PENDING, PENDING_DELETION, REJECTED``; message-template-api, arriba).

Aquí **sirve ``APPROVED`` y nada más**: los otros nueve —y el que Meta invente
mañana— caen solos, sin enumerarlos.

Y la degradación no es una excepción más: **``simulated`` se DERIVA del catálogo**
(``simulated == no hay ninguna plantilla utilizable``). Así, cuando Meta pausa la
plantilla en caliente, el canal entero **se declara simulado** y el orquestador
hace exactamente lo que T-2.75 le enseñó: ``notify_simulated`` (ámbar, no verde),
``sent_at`` en NULL, escala al SMS, **terminal y sin consumir intentos**. Que es
lo correcto: reintentar contra una plantilla pausada no la despausa — solo
empeora su calificación de calidad.

Los avisos de que la plantilla está muerta llegan por dos puertas distintas, y
hay que atender las dos:

1. **Un 4xx de la familia 132xxx.** ``132015`` "Template paused due to low
   quality"; ``132016`` "Template permanently disabled after repeated pauses";
   ``132001`` "Template doesn't exist in specified language or unapproved";
   ``132007`` viola la política; ``132000`` número de parámetros; ``132012``
   formato de parámetros (error-codes, arriba). Se cuarentena **por familia, no
   por lista**: todo 132xxx significa "con ESTA plantilla no se puede hablar", y
   el 132xxx que Meta añada mañana hereda el trato sin tocar este archivo.
2. **Un HTTP 200 que dice ``paused`` por dentro.** La respuesta del POST trae
   ``messages[0].message_status`` con tres valores documentados: ``accepted``,
   ``held_for_quality_assessment`` y ``paused``
   (https://developers.facebook.com/documentation/business-messaging/whatsapp/
   reference/whatsapp-business-phone-number/message-api). Un
   ``if response.is_success: return`` habría contado un ``paused`` como enviado.

──────────────────────────────────────────────────────────────────────────────
PUBLICADO ≠ ENTREGADO
──────────────────────────────────────────────────────────────────────────────
De esos tres valores, **ninguno significa "llegó al teléfono"**. El mejor,
``accepted``, es literalmente "has been accepted by WhatsApp and is being
processed" (message-api, arriba). La palabra ``delivered`` solo aparece **después**
y **por webhook**: "each outgoing message can have up to three separate webhooks
(one for a status of sent, one for delivered, and one for read)"
(https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/components).

La prueba más fuerte de que esa distinción es real la da la propia facturación de
Meta: **"You are only charged when a template message is delivered"**
(https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing).
Meta no cobra por lo que solo aceptó. Nuestra contabilidad no puede ser más
generosa que la suya.

Consecuencia honesta: cuando este provider vuelve sin excepción, el orquestador
marca ``sent`` y escribe ``notify_sent``. **Eso significa "aceptado por Meta", NO
"entregado"** — igual que ya significaba para SES y para Twilio. El log lo dice
con todas las letras en cada envío y ``last_receipt`` guarda el ``wamid``, que es
con lo que el día del webhook habrá que casar el job. El endpoint público que
reciba ese webhook es superficie de API + infra y **no cabe en esta ficha**:
queda fichado en `T-2.77` de `takab-docs/TASKS.md`.

``held_for_quality_assessment`` merece su párrafo: Meta lo retuvo para evaluarlo
y puede salir o no. **El default ante lo desconocido es la peor causa** ⇒ no
cuenta como envío, se escala al canal siguiente. Y como *podría* acabar saliendo,
la guarda de duplicados sí lo recuerda.

──────────────────────────────────────────────────────────────────────────────
OPT-IN · EL HALLAZGO QUE NO ESTABA EN LA FICHA
──────────────────────────────────────────────────────────────────────────────
"You may only contact people on WhatsApp if: (a) they have given you their mobile
phone number; and (b) you have received opt-in permission from the recipient
confirming that they wish to receive subsequent messages or calls from you"
(https://whatsappbusiness.com/es-la/policy/ — a donde redirige 301
``business.whatsapp.com/policy``). Y el opt-in debe "clearly state that a person
is opting in to receive communication from the business" y "clearly state the
business's name" (https://developers.facebook.com/documentation/business-messaging/
whatsapp/getting-opt-in).

**Hoy TAKAB no tiene modelo de consentimiento**: ``notifications.whatsapp.to`` es
un teléfono suelto en el ``rule_set``, sin quién, sin cuándo y sin prueba. Eso no
es un detalle de este canal: es la Fase 2.8 (T-2.79) llamando a la puerta.

Mientras llega, este provider **exige una constancia mínima en el destino**
(``opt_in.at``, el instante del consentimiento) y **se niega a enviar sin ella**.
No es burocracia: enviar sin opt-in no rebota un mensaje — degrada la calidad del
número y puede **tumbar el canal para todos los tenants a la vez**. Y la fecha no
es adorno: un consentimiento sin instante no se puede probar anterior al mensaje,
luego no es un consentimiento. El fallo queda **escrito** (``notify_failed``, rojo
en la consola) en vez de desaparecer en silencio.

──────────────────────────────────────────────────────────────────────────────
COSTE
──────────────────────────────────────────────────────────────────────────────
Meta factura **por mensaje entregado** desde el 2025-07-01, por categoría, y las
utility dentro de una ventana de servicio abierta son gratis (pricing, arriba).
Aquí la ventana está siempre cerrada ⇒ **siempre se paga**. La tarifa concreta
para México (código 52) vive en un CSV/PDF descargable que **no se pudo leer**,
así que **no se declara una cifra inventada**: queda fichado en `T-2.77.a`, junto
con el alta. Lo que sí está acotado por construcción, como en el SMS, es el
volumen: un destino por tenant, sin fan-out. Un incidente = un mensaje.

Credenciales por entorno / Secrets Manager (regla de oro 6). **Sin las tres
piezas el canal cae a ``SimulatedProvider``** (T-2.75): quien no puede entregar no
se declara real.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from takab_api.notify.providers import DuplicateGuard, NotifyError, SimulatedProvider

logger = logging.getLogger("takab_api.notify")

GRAPH_HOST = "https://graph.facebook.com"

#: Directorio de artefactos que viaja con el paquete (ver pyproject: package-data).
TEMPLATES_DIR = Path(__file__).parent / "whatsapp_templates"

#: "lowercase alphanumeric and underscores only" (message-template-api).
TEMPLATE_NAME_RE = re.compile(r"^[a-z0-9_]+$")

#: "The only required component is the body component" · "Maximum of 1024
#: characters" (https://developers.facebook.com/documentation/business-messaging/
#: whatsapp/templates/components/).
BODY_MAX_CHARS = 1024

#: Rango configurable del TTL de una plantilla utility: 30 s .. 12 h (templates/
#: time-to-live). El default de Meta son 30 DÍAS, que para un sismo es absurdo.
UTILITY_TTL_MIN_S = 30
UTILITY_TTL_MAX_S = 43_200

#: El único estado del enum de Meta con el que se puede enviar algo.
APPROVED = "APPROVED"

#: Huecos posicionales del cuerpo: {{1}}, {{2}}, ...
_PLACEHOLDER_RE = re.compile(r"\{\{\s*(\d+)\s*\}\}")

# --- estados de la respuesta del POST ----------------------------------------
#
# Los tres que Meta documenta para `messages[].message_status`. Ninguno es una
# entrega. Se guardan como constantes porque cada uno recibe un trato DISTINTO
# y confundirlos es el bug que esta tarea existe para evitar.
ACCEPTED_STATUS = "accepted"  # "accepted by WhatsApp and is being processed"
HELD_STATUS = "held_for_quality_assessment"  # retenido: puede salir o no
PAUSED_STATUS = "paused"  # la plantilla está pausada: NO va a salir

#: Lo único que significa "llegó al teléfono", y solo llega por webhook.
DELIVERY_CONFIRMED_STATUSES = frozenset({"delivered", "read"})


def is_delivery_confirmed(status: str) -> bool:
    """¿Ese estado significa que el mensaje llegó al teléfono?

    ``accepted`` significa "Meta lo aceptó y lo está procesando", no "el teléfono
    lo tiene". Confundirlos es la mentira de T-2.75 una capa más abajo.
    """
    return status in DELIVERY_CONFIRMED_STATUSES


def is_template_fault(code: int | None) -> bool:
    """¿Ese código de Meta dice que la culpa es de la PLANTILLA?

    Por FAMILIA (132xxx), no por lista: 132000/132001/132005/132007/132012/
    132015/132016 son todos errores de plantilla, y el que Meta añada mañana
    hereda el trato sin tocar esta función. Lo que enumera se queda ciego ante el
    siguiente caso.
    """
    return code is not None and 132_000 <= code < 133_000


# =============================================================================
# EL ARTEFACTO
# =============================================================================


def template_digest(submission: dict) -> str:
    """SHA-256 del bloque que Meta revisó (JSON canónico: claves ordenadas).

    Es el sello de aprobación: si el texto del repo se mueve, el digest se mueve
    y la plantilla deja de estar aprobada. Canónico para que reordenar claves o
    reindentar el fichero NO desapruebe una plantilla que no ha cambiado.
    """
    body = json.dumps(submission, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ParameterBinding:
    """De dónde sale un ``{{n}}``. Nuestro; no viaja a Meta."""

    index: int
    source: str
    fallback: str
    transform: str = ""

    def resolve(self, message: dict) -> str:
        raw = message.get(self.source)
        text = "" if raw is None else str(raw)
        if self.transform == "short_id":
            text = text[:8]
        elif self.transform:
            # Un transform desconocido no se ignora en silencio: la plantilla se
            # marca inutilizable al cargar (ver TemplateSpec.from_document).
            raise NotifyError(f"whatsapp: transform desconocido {self.transform!r}")
        return text.strip() or self.fallback


@dataclass(frozen=True)
class TemplateSpec:
    """Una plantilla del repo, ya validada, con su sello de aprobación."""

    name: str
    language: str
    category: str
    body: str
    ttl_s: int
    kind: str
    bindings: tuple[ParameterBinding, ...]
    status: str
    approved_digest: str
    digest: str
    source: str
    defect: str = ""

    @property
    def placeholders(self) -> tuple[int, ...]:
        """Huecos ``{{n}}`` del cuerpo, en orden de aparición."""
        return tuple(int(m) for m in _PLACEHOLDER_RE.findall(self.body))

    @property
    def unusable_reason(self) -> str:
        """Por qué NO se puede enviar con esta plantilla (vacío = sí se puede).

        Se devuelve la razón y no un booleano porque este texto acaba en el log
        de arranque y en el error del job: "el canal cayó" sin decir por qué es
        media respuesta.
        """
        if self.defect:
            return self.defect
        if self.status != APPROVED:
            return f"estado {self.status} (Meta solo permite enviar con {APPROVED})"
        if not self.approved_digest:
            return "sin approved_digest: nadie ha sellado qué texto aprobó Meta"
        if self.approved_digest != self.digest:
            return (
                "el digest del texto no coincide con el aprobado: el cuerpo cambió "
                "en el repo y hay que volver a pedir aprobación a Meta"
            )
        return ""

    @property
    def usable(self) -> bool:
        return not self.unusable_reason

    def render(self, values: list[str]) -> str:
        """El cuerpo con los huecos rellenos. Solo para medir y para depurar: el
        texto que la gente lee lo compone Meta con la versión que aprobó."""

        def _sub(match: re.Match[str]) -> str:
            i = int(match.group(1))
            return values[i - 1] if 1 <= i <= len(values) else match.group(0)

        return _PLACEHOLDER_RE.sub(_sub, self.body)

    @classmethod
    def from_document(cls, doc: dict, source: str) -> TemplateSpec:
        """Construye la spec y **no revienta**: un artefacto inválido nace con
        ``defect`` puesto (⇒ inutilizable ⇒ el canal cae y lo dice). Reventar
        aquí dejaría al worker sin arrancar y, con él, sin NINGÚN canal."""
        submission = doc.get("template") or {}
        binding = doc.get("binding") or {}
        approval = doc.get("approval") or {}
        body_component = next(
            (
                c
                for c in submission.get("components") or []
                if isinstance(c, dict) and str(c.get("type", "")).upper() == "BODY"
            ),
            {},
        )
        bindings = tuple(
            ParameterBinding(
                index=int(p.get("index", 0)),
                source=str(p.get("source") or ""),
                fallback=str(p.get("fallback") or ""),
                transform=str(p.get("transform") or ""),
            )
            for p in binding.get("parameters") or []
        )
        spec = cls(
            name=str(submission.get("name") or ""),
            language=str(submission.get("language") or ""),
            category=str(submission.get("category") or ""),
            body=str(body_component.get("text") or ""),
            ttl_s=int(submission.get("message_send_ttl_seconds") or 0),
            kind=str(binding.get("kind") or ""),
            bindings=tuple(sorted(bindings, key=lambda b: b.index)),
            status=str(approval.get("status") or "").upper() or "PENDING",
            approved_digest=str(approval.get("approved_digest") or ""),
            digest=template_digest(submission),
            source=source,
        )
        defect = _defect_of(spec)
        return spec if not defect else cls(**{**spec.__dict__, "defect": defect})


def _defect_of(spec: TemplateSpec) -> str:
    """Lo que hace inválida a una plantilla ANTES de mirar su aprobación.

    Se comprueba al cargar y no al enviar: descubrir a mitad de un sismo que el
    nombre lleva mayúsculas es descubrirlo tarde.
    """
    if not TEMPLATE_NAME_RE.match(spec.name):
        return f"nombre {spec.name!r} inválido (Meta: minúsculas, dígitos y guion bajo)"
    if not spec.language or not spec.kind or not spec.body:
        return "artefacto incompleto (falta language, binding.kind o el componente BODY)"
    if len(spec.body) > BODY_MAX_CHARS:
        return f"cuerpo de {len(spec.body)} caracteres (Meta admite {BODY_MAX_CHARS})"
    huecos = spec.placeholders
    if huecos != tuple(range(1, len(huecos) + 1)):
        return f"huecos posicionales no correlativos: {huecos}"
    if len(spec.bindings) != len(huecos):
        return (
            f"{len(huecos)} hueco(s) en el texto y {len(spec.bindings)} binding(s): "
            "Meta rechaza el envío con 132000 (parameter count mismatch)"
        )
    if tuple(b.index for b in spec.bindings) != huecos:
        return "los índices de los bindings no cubren los huecos del texto"
    if any(b.transform not in ("", "short_id") for b in spec.bindings):
        return "binding con un transform que este módulo no sabe aplicar"
    if not UTILITY_TTL_MIN_S <= spec.ttl_s <= UTILITY_TTL_MAX_S:
        return (
            f"message_send_ttl_seconds={spec.ttl_s} fuera del rango de una plantilla "
            f"utility ({UTILITY_TTL_MIN_S}..{UTILITY_TTL_MAX_S} s)"
        )
    return ""


@dataclass
class TemplateCatalog:
    """Las plantillas del repo + la cuarentena que Meta impone en caliente."""

    templates: tuple[TemplateSpec, ...] = ()
    quarantined: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, directory: Path | str) -> TemplateCatalog:
        """Lee ``*.json`` del directorio. **Nunca levanta**: un artefacto ilegible
        se salta con un ERROR ruidoso y los sanos siguen sirviendo."""
        found: list[TemplateSpec] = []
        for path in sorted(Path(directory).glob("*.json")):
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
                found.append(TemplateSpec.from_document(doc, source=path.name))
            except (OSError, ValueError, TypeError) as exc:
                logger.error(
                    "canal whatsapp: artefacto de plantilla ilegible %s (%s) — se omite; "
                    "el canal quedará simulado si no hay ninguna otra aprobada",
                    path.name,
                    type(exc).__name__,
                )
        return cls(templates=tuple(found))

    @property
    def usable(self) -> tuple[TemplateSpec, ...]:
        """Las que se pueden enviar AHORA (aprobadas y sin cuarentena)."""
        return tuple(t for t in self.templates if t.usable and t.name not in self.quarantined)

    def get(self, kind: str, language: str) -> TemplateSpec | None:
        return next(
            (t for t in self.usable if t.kind == kind and t.language == language),
            None,
        )

    def quarantine(self, template: TemplateSpec, reason: str) -> None:
        """Meta dijo que con esa plantilla no se puede hablar. Fuera del catálogo
        hasta que un humano la vuelva a someter y el proceso reinicie."""
        self.quarantined[template.name] = reason
        logger.error(
            "canal whatsapp: plantilla %s EN CUARENTENA (%s). Quedan %d utilizable(s); "
            "si son 0 el canal se declara simulado y el orquestador escala.",
            template.name,
            reason,
            len(self.usable),
        )


# =============================================================================
# PARÁMETROS
# =============================================================================


def fold_parameter(text: str, budget: int) -> str:
    """Deja un valor de parámetro apto para Meta y acotado a ``budget``.

    **Por derivación, no por tabla**: se tira todo lo que Unicode clasifica como
    control o formato (categoría ``C*`` — saltos de línea, tabuladores, NUL,
    zero-width, soft hyphen…) y se colapsa el espacio. Así vale para el carácter
    que nadie ha visto todavía, y no para una lista de cinco que se queda ciega
    ante el sexto. A diferencia del SMS (T-2.76, GSM-7), aquí los acentos SÍ se
    conservan: WhatsApp es UTF-8 y se factura por mensaje entregado, no por
    segmento.

    Motivo real: Meta rechaza los parámetros mal formados con el error 132012, y
    un aviso de sismo que no sale por un salto de línea en el nombre de un
    edificio es un fallo caro por una causa tonta.
    """
    limpio = "".join(" " if unicodedata.category(c).startswith("C") else c for c in text)
    return " ".join(limpio.split())[:budget].strip()


def render_parameters(template: TemplateSpec, message: dict) -> list[str]:
    """Los valores de ``{{1}}..{{n}}``, en orden, ya plegados y acotados.

    El presupuesto por parámetro se **deriva** del texto aprobado (1024 menos lo
    que ocupa la parte fija, repartido entre los huecos): si mañana el cuerpo
    crece, el recorte se ajusta solo en vez de quedarse mintiendo.
    """
    huecos = template.placeholders
    if len(template.bindings) != len(huecos):
        raise NotifyError(
            f"whatsapp: la plantilla {template.name} declara {len(template.bindings)} "
            f"parámetros y su texto tiene {len(huecos)} huecos"
        )
    if not huecos:
        return []
    fijo = len(_PLACEHOLDER_RE.sub("", template.body))
    budget = max((BODY_MAX_CHARS - fijo) // len(huecos), 1)
    return [fold_parameter(b.resolve(message), budget) or b.fallback for b in template.bindings]


# =============================================================================
# EL PROVIDER
# =============================================================================


@dataclass(frozen=True)
class WhatsAppReceipt:
    """Lo que Meta contestó. Observabilidad, **no** prueba de entrega.

    ``wamid`` se guarda desde el minuto uno aunque hoy no haya webhook: es el
    identificador con el que ese día habrá que casar el desenlace tardío contra
    el job, y no se puede reconstruir después.
    """

    wamid: str
    status: str
    template: str
    category: str

    @property
    def delivery_confirmed(self) -> bool:
        return is_delivery_confirmed(self.status)


class WhatsAppTemplateProvider:
    """WhatsApp Cloud API detrás del contrato ``NotifyProvider``.

    Habla HTTP directo con ``httpx`` (ya es dependencia, es lo que usan
    ``WebhookProvider`` y el provider de Twilio) en vez de un SDK: una dependencia
    menos y un transporte inyectable, que es lo que permite probar todo esto
    **sin una sola llamada de red**.
    """

    def __init__(
        self,
        *,
        phone_number_id: str,
        access_token: str,
        graph_version: str,
        catalog: TemplateCatalog,
        language: str,
        timeout_s: float = 5.0,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        # Ni una operación falible aquí: un constructor que revienta deja al
        # worker sin arrancar y, con él, sin ningún canal de aviso.
        self._access_token = access_token
        self._timeout_s = timeout_s
        self._transport = transport
        self._language = language
        self.catalog = catalog
        self._guard = DuplicateGuard(clock=clock or time.monotonic)
        self._url = f"{GRAPH_HOST}/{graph_version}/{phone_number_id}/messages"
        self.last_receipt: WhatsAppReceipt | None = None

    # -- el contrato -----------------------------------------------------------

    @property
    def simulated(self) -> bool:
        """**Derivado, no declarado.** Sin ninguna plantilla utilizable este canal
        no puede entregar nada, y quien no puede entregar no es real (T-2.75).

        Que sea una propiedad y no un atributo es lo que hace que la degradación
        funcione EN CALIENTE: cuando Meta pausa la plantilla a mitad de la noche,
        el siguiente job ve ``simulated=True`` y acaba en ``notify_simulated``
        —ámbar, terminal, escalando al SMS— en vez de en un ``failed`` que se
        reintenta tres veces contra una plantilla muerta.
        """
        return not self.catalog.usable

    @property
    def hint(self) -> str:
        """Qué falta para que este canal entregue algo (sale en el log de arranque)."""
        razones = sorted({t.unusable_reason for t in self.catalog.templates if not t.usable})
        if self.catalog.quarantined:
            razones += [f"{n}: {r}" for n, r in sorted(self.catalog.quarantined.items())]
        if not razones:
            return ""
        return "ninguna plantilla utilizable — " + "; ".join(razones)

    @property
    def quarantined(self) -> dict[str, str]:
        return dict(self.catalog.quarantined)

    @property
    def pending_keys(self) -> int:
        return self._guard.pending

    # -- envío -----------------------------------------------------------------

    def _scrub(self, text: str) -> str:
        """El token jamás sale en un error ni en un log (regla de oro 6)."""
        return text.replace(self._access_token, "***") if self._access_token else text

    def send(self, target: dict, message: dict) -> None:
        to = target.get("to")
        if not isinstance(to, str) or not to.strip():
            raise NotifyError("whatsapp sin destinatario")
        if "," in to or ";" in to:
            # Mismo cortafuegos que el SMS: la guardia del SOC, no un difusor. Y
            # aquí además cada destinatario extra necesitaría su PROPIO opt-in.
            raise NotifyError("whatsapp: un destino por mensaje (este canal no hace fan-out)")
        to = to.strip()

        opt_in = target.get("opt_in")
        if not isinstance(opt_in, dict) or not str(opt_in.get("at") or "").strip():
            raise NotifyError(
                "whatsapp: sin opt-in fechado para este destino. La política de WhatsApp "
                "Business exige consentimiento previo; enviar sin él degrada la calidad "
                "del número y puede tumbar el canal para todos los tenants"
            )

        kind = str(message.get("kind") or "incident")
        template = self.catalog.get(kind, self._language)
        if template is None:
            # Ni texto libre (Meta lo rechazaría con 131047 fuera de la ventana),
            # ni "la plantilla parecida". Sin plantilla aprobada, silencio honesto.
            raise NotifyError(
                f"whatsapp: sin plantilla APROBADA para kind={kind!r} en {self._language!r}"
                + (f" — {self.hint}" if self.hint else "")
            )

        key = (to, str(message.get("incident_id") or ""))
        if self._guard.seen(key):
            raise NotifyError(
                "whatsapp: posible duplicado — ya se emitió un mensaje para este incidente "
                "a este número y pudo estar en vuelo; se escala en vez de duplicar"
            )

        values = render_parameters(template, message)
        payload: dict = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "template",
            "template": {"name": template.name, "language": {"code": template.language}},
        }
        if values:
            payload["template"]["components"] = [
                {"type": "body", "parameters": [{"type": "text", "text": v} for v in values]}
            ]

        try:
            with httpx.Client(timeout=self._timeout_s, transport=self._transport) as client:
                response = client.post(
                    self._url,
                    json=payload,
                    headers={"Authorization": f"Bearer {self._access_token}"},
                )
        except httpx.HTTPError as exc:
            # AMBIGUO: la petición pudo llegar y crear el mensaje.
            self._guard.remember(key, template.ttl_s)
            raise NotifyError(f"whatsapp: sin respuesta ({type(exc).__name__})") from None

        if response.status_code >= 400:
            self._handle_error(response, template, key)
        self._handle_success(response, template, key)

    # -- desenlaces ------------------------------------------------------------

    def _handle_error(self, response: httpx.Response, template: TemplateSpec, key) -> None:
        code, detail = _error_of(response)
        motivo = self._scrub(f"whatsapp: HTTP {response.status_code} [{code}] {detail}")
        if is_template_fault(code):
            # La plantilla está muerta: fuera del catálogo. Si era la única, el
            # canal entero se declara simulado en el siguiente job.
            self.catalog.quarantine(template, f"Meta devolvió {code}: {detail}"[:200])
            raise NotifyError(motivo)
        if response.status_code >= 500:
            # AMBIGUO: un 5xx puede venir después de haber creado el mensaje.
            self._guard.remember(key, template.ttl_s)
            raise NotifyError(
                self._scrub(f"whatsapp: HTTP {response.status_code} (envío incierto)")
            )
        # Rechazo EXPLÍCITO de este destinatario (131026, 131049, 131050...): no
        # se creó nada, el reintento es seguro y la plantilla no tiene la culpa.
        raise NotifyError(motivo)

    def _handle_success(self, response: httpx.Response, template: TemplateSpec, key) -> None:
        try:
            payload = response.json()
        except ValueError:
            self._guard.remember(key, template.ttl_s)
            raise NotifyError("whatsapp: respuesta ilegible (envío incierto)") from None

        messages = payload.get("messages") or []
        first = messages[0] if messages and isinstance(messages[0], dict) else {}
        wamid = str(first.get("id") or "")
        status = str(first.get("message_status") or "")
        if not wamid:
            self._guard.remember(key, template.ttl_s)
            raise NotifyError("whatsapp: respuesta sin wamid (envío incierto)")

        if status == PAUSED_STATUS:
            # 200 por fuera, plantilla muerta por dentro. NO se recuerda: un
            # mensaje pausado no va a salir, luego no hay duplicado posible.
            self.catalog.quarantine(template, "Meta respondió message_status=paused")
            raise NotifyError(f"whatsapp: mensaje {wamid} en estado {PAUSED_STATUS}")
        if status != ACCEPTED_STATUS:
            # `held_for_quality_assessment` y cualquier estado futuro. Puede
            # acabar saliendo ⇒ se recuerda para no duplicar; pero NO se cuenta
            # como envío: el default ante lo desconocido es la peor causa.
            self._guard.remember(key, template.ttl_s)
            raise NotifyError(f"whatsapp: message_status {status!r} no es una aceptación limpia")

        self._guard.remember(key, template.ttl_s)
        self.last_receipt = WhatsAppReceipt(
            wamid=wamid, status=status, template=template.name, category=template.category
        )
        logger.info(
            "notify[whatsapp] wamid=%s status=%s · entrega NO confirmada · plantilla %s (%s/%s)",
            wamid,
            status,
            template.name,
            template.category,
            template.language,
        )


def _error_of(response: httpx.Response) -> tuple[int | None, str]:
    """``(code, message)`` del error de Meta, acotado. Defensivo a propósito: el
    cuerpo de un 5xx puede no ser JSON, y un fallo al leer un fallo no puede
    tumbar el canal."""
    try:
        payload = response.json()
    except ValueError:
        return None, response.text[:200]
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return None, str(payload)[:200]
    raw = error.get("code")
    code = raw if isinstance(raw, int) else None
    return code, str(error.get("message") or "")[:200]


# =============================================================================
# CONSTRUCCIÓN
# =============================================================================

WHATSAPP_HINT = (
    "TAKAB_API_NOTIFY_WHATSAPP_PHONE_NUMBER_ID + TAKAB_API_NOTIFY_WHATSAPP_ACCESS_TOKEN "
    "+ TAKAB_API_NOTIFY_WHATSAPP_GRAPH_VERSION"
)


def build_whatsapp_provider(
    settings,
    *,
    transport: httpx.BaseTransport | None = None,
    clock: Callable[[], float] | None = None,
):
    """WhatsApp Cloud si están las TRES piezas; si no, simulado (T-2.75).

    La **versión de Graph cuenta como credencial** y no lleva default: va dentro
    de la ruta (``/{version}/{phone_number_id}/messages``) y Meta retira versiones
    con el tiempo, así que un default adivinado aquí se convierte en un 400 el día
    que caduque — y ese día es siempre el peor. Se declara en el entorno, donde
    alguien la puede subir sin recompilar nada.

    Ojo con la asimetría: con credenciales pero sin plantilla aprobada **sí** se
    devuelve el provider real. Su ``simulated`` es derivado, así que se declara
    simulado él solo y además puede DECIR por qué; un ``SimulatedProvider`` genérico
    solo sabría decir "falta configurar algo".
    """
    phone_number_id = (settings.notify_whatsapp_phone_number_id or "").strip()
    access_token = (settings.notify_whatsapp_access_token or "").strip()
    graph_version = (settings.notify_whatsapp_graph_version or "").strip()

    faltan = [
        name
        for name, value in (
            ("phone_number_id", phone_number_id),
            ("access_token", access_token),
            ("graph_version", graph_version),
        )
        if not value
    ]
    if faltan:
        if len(faltan) < 3:
            logger.error(
                "canal whatsapp: credenciales de Meta A MEDIAS (falta %s) — el canal NO "
                "asciende a real; los jobs quedarán 'simulated' y nadie recibirá nada.",
                ", ".join(faltan),
            )
        return SimulatedProvider("whatsapp", hint=WHATSAPP_HINT)

    directory = (settings.notify_whatsapp_templates_dir or "").strip() or TEMPLATES_DIR
    catalog = TemplateCatalog.load(directory)
    language = (settings.notify_whatsapp_language or "es_MX").strip()

    for template in catalog.usable:
        logger.info(
            "canal whatsapp REAL (cloud api) · plantilla %s (%s/%s) · kind=%s · TTL %ss · "
            "%d parámetro(s) · digest %s · se factura por mensaje ENTREGADO",
            template.name,
            template.category,
            template.language,
            template.kind,
            template.ttl_s,
            len(template.bindings),
            template.digest[:12],
        )
    if not catalog.usable:
        razones = "; ".join(sorted({t.unusable_reason for t in catalog.templates}))
        logger.error(
            "canal whatsapp: hay credenciales pero NINGUNA plantilla aprobada — %s. "
            "WhatsApp no deja improvisar texto fuera de la ventana de servicio, así que "
            "el canal se declara SIMULADO: los jobs quedarán 'simulated' (jamás 'sent') "
            "y el orquestador escalará al canal siguiente.",
            razones or "no hay artefactos",
        )
    logger.warning(
        "canal whatsapp: sin endpoint de webhook de estado ⇒ NO hay confirmación de entrega. "
        "Un 'notify_sent' de whatsapp significa ACEPTADO POR META, no entregado al teléfono."
    )
    return WhatsAppTemplateProvider(
        phone_number_id=phone_number_id,
        access_token=access_token,
        graph_version=graph_version,
        catalog=catalog,
        language=language,
        timeout_s=settings.notify_whatsapp_timeout_s,
        transport=transport,
        clock=clock,
    )
