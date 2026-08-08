"""T-2.79 · Contratos del aviso de privacidad y del consentimiento."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Purpose = Literal["privacy_notice", "whatsapp_alerts"]
Decision = Literal["accept", "withdraw"]
ConsentState = Literal["missing", "current", "stale", "withdrawn"]
Via = Literal["mobile", "web", "console_admin", "out_of_band"]


class NoticeOut(BaseModel):
    """El aviso vigente, con su sello y su origen."""

    purpose: Purpose
    locale: str
    version: str
    title: str
    body: str
    #: Los párrafos del CUERPO, no un resumen aparte. Un resumen que se enseña
    #: pero no se sella deja consentir un texto distinto del que se leyó.
    paragraphs: list[str]
    #: La identidad del aviso. Es lo que el consentimiento sella, y lo que hace
    #: detectable que el texto de hoy ya no es el de ayer.
    digest: str
    #: 'repo' = aviso de plataforma (artefacto de git); 'tenant' = publicado por
    #: el cliente. Un consentimiento no significa lo mismo según quién escribió.
    source: Literal["repo", "tenant"]
    notice_id: UUID | None = None
    effective_at: datetime | None = None
    #: El texto NO está revisado por LEGAL. Viaja hasta la pantalla a propósito.
    provisional: bool
    provisional_reason: str = ""


class ConsentOut(BaseModel):
    """Una decisión del registro append-only, tal como se escribió."""

    model_config = ConfigDict(from_attributes=True)

    consent_id: UUID
    decision: Decision
    notice_source: Literal["repo", "tenant"]
    notice_id: UUID | None = None
    notice_digest: str
    notice_version: str
    notice_locale: str
    via: Via
    actor_sub: UUID
    decided_at: datetime


class ConsentStatusOut(BaseModel):
    """Lo que la UI necesita para pintar los cuatro estados sin adivinar.

    ``state`` lo decide el SERVIDOR comparando digests. El cliente no recalcula
    nada: si lo hiciera habría dos verdades y la del cliente mentiría en cuanto
    el aviso cambiara entre dos peticiones.

    ``json_schema_serialization_defaults_required``: la respuesta viaja entera, así
    que ``blocks_emergency_actions`` **siempre** va — y publicarlo como opcional
    invitaba justo a lo que el propio campo existe para impedir, que una UI se
    inventara qué hacer sin él.
    """

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    notice: NoticeOut | None
    state: ConsentState
    consent: ConsentOut | None = None
    #: El consentimiento NUNCA gatea el camino crítico (reglas de oro 1 y 2).
    #: Va en el contrato para que ninguna UI se invente lo contrario.
    blocks_emergency_actions: Literal[False] = False


class ConsentHistoryOut(BaseModel):
    items: list[ConsentOut]


class ConsentIn(BaseModel):
    """Aceptar o retirar. Sin cuerpo del aviso: el servidor resuelve el vigente.

    El cliente manda el ``digest`` que tenía en pantalla y el servidor rechaza
    si ya no es el vigente (409). Sin eso, alguien que dejó la pantalla abierta
    mientras el aviso cambiaba firmaría el texto NUEVO habiendo leído el viejo —
    que es exactamente la clase de mentira que esta tarea existe para impedir.
    """

    model_config = ConfigDict(extra="forbid")

    purpose: Purpose = "privacy_notice"
    locale: str = Field(default="es-MX", pattern=r"^[a-z]{2}-[A-Z]{2}$")
    decision: Decision
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    via: Literal["mobile", "web"] = "web"


class ThirdPartyConsentIn(BaseModel):
    """Constancia del consentimiento de un tercero SIN sesión (un teléfono).

    Es el caso del opt-in de WhatsApp (T-2.77): el sujeto es un número, la
    persona no entra a la app y quien lo registra es el administrador del
    tenant. Por eso ``via`` se limita a los dos valores que describen ese acto y
    ``actor_sub`` queda escrito por separado: quién registra no es quién
    consiente, y confundirlos borraría la diferencia legalmente relevante.
    """

    model_config = ConfigDict(extra="forbid")

    purpose: Purpose = "whatsapp_alerts"
    locale: str = Field(default="es-MX", pattern=r"^[a-z]{2}-[A-Z]{2}$")
    decision: Decision
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    msisdn: str = Field(pattern=r"^\+[1-9][0-9]{7,14}$")
    via: Literal["console_admin", "out_of_band"] = "out_of_band"


class NoticeIn(BaseModel):
    """Publicar el aviso del TENANT. No hay endpoint de edición y no lo habrá."""

    model_config = ConfigDict(extra="forbid")

    purpose: Purpose = "privacy_notice"
    locale: str = Field(default="es-MX", pattern=r"^[a-z]{2}-[A-Z]{2}$")
    version: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=8, max_length=200)
    body: str = Field(min_length=40)
    effective_at: datetime | None = None


class NoticePublishedOut(BaseModel):
    notice_id: UUID
    digest: str
    version: str
    effective_at: datetime
    published_at: datetime


# ---------------------------------------------------------------------------
# T-2.80 · ARCO por anonimización con tombstone
# ---------------------------------------------------------------------------

Right = Literal["cancelacion", "oposicion"]


class ErasureIn(BaseModel):
    """Ejercer cancelación u oposición. **No lleva sujeto, y es a propósito.**

    El titular del borrado es siempre el portador del token: ejercer ARCO sobre
    un tercero no está prohibido, es inexpresable — ni en este contrato ni en la
    función de base de datos que lo ejecuta.

    ``confirm`` no es burocracia: la anonimización es IRREVERSIBLE (no se guarda
    en ningún sitio el mapeo que se destruye), así que un ``POST`` accidental no
    puede deshacerse. Que el cliente tenga que escribir ``true`` es lo único que
    separa un botón mal pulsado de un dato que no vuelve.
    """

    model_config = ConfigDict(extra="forbid")

    right: Right = "cancelacion"
    via: Literal["mobile", "web"] = "web"
    confirm: Literal[True]


class ErasureOut(BaseModel):
    """La lápida. Dice QUÉ pasó y CUÁNTO, jamás A QUIÉN se llamaba.

    ``affected`` son conteos por tabla ("se anonimizaron 3 check-ins"), no las
    filas ni su contenido. La base lo impone con un CHECK que rechaza cualquier
    valor que no sea un número: sin él, este objeto sería el sitio obvio donde
    alguien guardaría el nombre "por trazabilidad" y desharía la tarea entera.
    """

    model_config = ConfigDict(from_attributes=True)

    erasure_id: UUID
    user_sub: UUID
    right_exercised: Right
    via: Via
    affected: dict[str, int]
    #: Último ``audit_id`` del tenant en el instante del borrado.
    audit_watermark: int
    #: SHA-256 de toda la bitácora anterior a esa marca, sellado ese día.
    audit_digest: str
    erased_at: datetime
    #: ``False`` = ya se había ejercido. No es un fallo: es idempotencia.
    created: bool = False


class ErasureProofOut(BaseModel):
    """La lápida MÁS la comprobación de que la bitácora sigue cuadrando HOY.

    Un sello guardado que nadie recalcula no prueba nada. Por eso la respuesta no
    devuelve solo lo que se selló: recalcula el digest en esta misma petición y
    responde si coinciden. El criterio 3 de la ficha ("el `audit_log` sigue
    íntegro y verificable") deja así de ser una afirmación del día del
    despliegue y pasa a ser una medición que cualquiera puede pedir.
    """

    erasure: ErasureOut
    #: Recalculado AHORA sobre `audit_watermark`.
    audit_digest_now: str
    #: La comparación la hace el SERVIDOR (regla de oro 7: si la hiciera la UI,
    #: habría dos verdades y una podría pintar "íntegro" sobre un log tocado).
    audit_intact: bool
