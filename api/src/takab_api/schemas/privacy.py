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


#: [T-2.80.b] Cómo LLEGÓ la solicitud escrita. No confundir con ``Via``, que es
#: cómo se EJERCIÓ el borrado: son dos actos distintos y separarlos es la mitad
#: del registro que exige el criterio 2 de la ficha.
RequestChannel = Literal["written", "email", "in_person", "legal_representative"]


class ErasureIn(BaseModel):
    """Ejercer cancelación u oposición. **No lleva sujeto, y es a propósito.**

    El titular del borrado es siempre el portador del token: ejercer ARCO sobre
    un tercero por esta puerta no está prohibido, es inexpresable — ni en este
    contrato ni en la función de base de datos que lo ejecuta. La puerta del
    responsable es otra (``ErasureOnBehalfIn``) y tampoco lleva sujeto: lleva la
    constancia de la solicitud recibida.

    ``confirm`` no es burocracia: la anonimización es IRREVERSIBLE (no se guarda
    en ningún sitio el mapeo que se destruye), así que un ``POST`` accidental no
    puede deshacerse. Que el cliente tenga que escribir ``true`` es lo único que
    separa un botón mal pulsado de un dato que no vuelve.
    """

    model_config = ConfigDict(extra="forbid")

    right: Right = "cancelacion"
    via: Literal["mobile", "web"] = "web"
    confirm: Literal[True]


class ErasureRequestIn(BaseModel):
    """[T-2.80.b] La CONSTANCIA de una solicitud ARCO recibida por escrito.

    Es lo que convierte "alguien me lo pidió" en algo verificable. ``proof_ref``
    dice DÓNDE está el escrito (folio, expediente, clave de objeto) y
    ``proof_digest`` prueba CUÁL es: sin el digest, la constancia sería la palabra
    del responsable contra la del titular, y con él es un documento concreto que
    no se puede sustituir después.

    ``user_sub`` viaja en claro y no es un agujero: el FK compuesto contra
    ``user_profiles (tenant_id, user_sub)`` solo admite a alguien del PROPIO
    padrón, así que nombrar a un titular de otro cliente no se rechaza por una
    comprobación — viola integridad referencial.

    Lo que este contrato NO tiene: el documento. Guardarlo aquí metería PII eterna
    en una tabla que la regla de oro 11 impide podar.
    """

    model_config = ConfigDict(extra="forbid")

    user_sub: UUID
    right: Right = "cancelacion"
    channel: RequestChannel = "written"
    #: Cuándo LLEGÓ la solicitud. Es de donde corre el plazo legal, así que lo
    #: pone quien la recibió y no el reloj del servidor.
    received_at: datetime
    proof_ref: str = Field(min_length=3, max_length=200)
    proof_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class ErasureRequestOut(BaseModel):
    """La constancia registrada. Sin PII del titular más allá de su `sub` opaco."""

    model_config = ConfigDict(from_attributes=True)

    request_id: UUID
    user_sub: UUID
    right_requested: Right
    channel: RequestChannel
    received_at: datetime
    proof_ref: str
    proof_digest: str
    #: Quién la REGISTRÓ. Nunca es el titular (la base lo impide con un CHECK):
    #: confundirlos borraría la diferencia entre "la persona lo solicitó" y "un
    #: administrador lo dio por hecho".
    created_by: UUID
    created_at: datetime


class ErasureOnBehalfIn(BaseModel):
    """[T-2.80.b] Ejecutar una constancia. **Sin sujeto y sin derecho.**

    Las dos ausencias son la tarea entera. El sujeto, porque aceptarlo reabriría
    el ARCO cruzado que T-2.80 hizo inexpresable: la constancia va en la RUTA y el
    sujeto se resuelve dentro de la base contra el padrón del tenant de la sesión.
    El derecho, porque el escrito recibido ya dice qué se pidió — dejar que el
    ejecutor lo re-declare permitiría que el registro divergiera del documento.
    """

    model_config = ConfigDict(extra="forbid")

    #: Cómo se EJERCIÓ (≠ ``channel``, que es cómo llegó la solicitud).
    via: Literal["console_admin", "out_of_band"] = "console_admin"
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
    #: [T-2.80.b] Quién EJERCIÓ el acto ante el sistema: el titular (autoservicio)
    #: o el responsable que ejecutó una constancia. Quién lo pidió materialmente
    #: está en la constancia; en autoservicio los dos coinciden por construcción.
    requested_by: UUID
    #: [T-2.80.b] La constancia que autoriza el acto, o ``null`` en autoservicio.
    #: La base impide que esa correspondencia mienta: un CHECK exige que
    #: ``request_id IS NULL`` sea exactamente ``via IN ('mobile','web')``.
    request_id: UUID | None = None
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
