"""Contrato de la capa narrativa (T-2.42).

La prosa RODEA al dictamen; jamás lo produce. Eso no se promete en la documentación:
se impone por tipos. ``NarrativeRequest`` recibe el veredicto **ya calculado** por
``dictamen/rules.py``, y ``Narrative`` —lo único que un proveedor puede devolver— no
tiene ningún campo de veredicto, estado, prioridad ni severidad. Un proveedor no puede
emitir un veredicto porque no hay dónde ponerlo (regla de oro 1).

Los hechos que viajan al proveedor pasan antes por ``redact.py``, que es una
**allowlist**: lo que no está enumerado allí no sale de la nube.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

#: ──────────────────────────── [T-7.26] los motivos de degradación
#:
#: Viven aquí —y no en cada módulo— porque son PROSA DE CARA AL LECTOR DEL PDF: se
#: imprimen bajo el §16 y quien los lee no sabe qué es un tenant ni un secreto de
#: AWS. Tenerlos juntos es lo que permite que los tests los citen por su nombre en
#: vez de por un trozo de frase que se desincroniza al primer retoque de redacción.
#:
#: ⚠️ La distinción que faltaba y que da sentido a toda la lista: **estar APAGADO no
#: es una degradación** (es la configuración pedida, y no lleva motivo), pero
#: **estar ENCENDIDO y no poder sí lo es**. Hasta T-7.26 las dos cosas se veían
#: exactamente igual desde el papel — que es como un `AccessDenied` al leer la clave
#: en la nube iba a pasar por «la IA está apagada».
#:
#: La excepción declarada: los dos motivos de la CUOTA (`MOTIVO_AGOTADA` y
#: `MOTIVO_TOPE_CERO`) viven en `narrative/quota.py`, pegados a la decisión que los
#: separa —«se agotó» no es «no había»— y a los dos números de los que se derivan.
#: Moverlos aquí les quitaría la razón de al lado. Lo que NO puede pasar, y es lo que
#: pasaba, es que un motivo esté tecleado en el sitio donde se usa: eso lo vigila
#: `tests/narrative/test_glosario_de_motivos.py` sobre el AST del paquete entero.

#: Ni siquiera hubo hechos que redactar: la prosa no existe. No lleva el sufijo de
#: abajo porque aquí NO hay texto determinista que ofrecer.
MOTIVO_SIN_HECHOS = "no se pudieron redactar los hechos del incidente"

#: El respaldo determinista TAMBIÉN falló. Es el mismo modo de fallo que la ficha vino
#: a cerrar, un nivel más abajo: si esto se propagara, la exportación se caería por la
#: prosa. Tampoco lleva sufijo — y quitárselo al motivo original es parte del trabajo
#: (ver `_sin_respaldo`): prometer «texto determinista» donde no lo hay es el documento
#: desmintiéndose a sí mismo tres líneas más abajo.
MOTIVO_RESPALDO_CAIDO = "y el respaldo determinista también falló"

#: Lo que se añade a todo motivo que sí tiene respaldo: el dictamen sale completo,
#: con las seis secciones, escritas por el motor determinista.
SUFIJO_DETERMINISTA = "; texto determinista"

#: Ni siquiera se pudo DECIDIR quién redacta. `select_provider` lee ajustes y sale a
#: Secrets Manager: vivía fuera de todo `try` y su excepción salía a `generate_report`.
MOTIVO_ELECCION = "no se pudo elegir el proveedor de redacción"

MOTIVO_PROVEEDOR = "el proveedor de redacción falló"
MOTIVO_CUOTA_ILEGIBLE = "no se pudo leer la cuota de redacción asistida"
MOTIVO_CLAVE_ILEGIBLE = "redacción asistida encendida pero la clave no se pudo leer"
MOTIVO_SIN_CLAVE = "redacción asistida encendida sin clave configurada" + SUFIJO_DETERMINISTA

#: ────────────────────────────── [T-7.27] los motivos de la VISIÓN del modelo
#:
#: `D-32` puso como condición que **el modelo declare que admite imágenes** antes de
#: mandarle una fotografía del brigadista. Son dos hechos distintos y llevan dos frases
#: distintas, por la misma razón que «no respondió» y «respondió que no» dejaron de ser
#: una sola en T-7.26: mandan a mirar a sitios opuestos.
#:
#: El primero es del MODELO: está en el catálogo y no admite imágenes, o el slug ya no
#: está en el catálogo. Se arregla cambiando el slug, y hasta entonces no hay nada que
#: esperar. Van por `motivo_con_causa`, así que no llevan el sufijo escrito.
MOTIVO_SIN_VISION = "el modelo de redacción no admite imágenes"
#: El segundo es del MOMENTO: el catálogo no se pudo leer (red, 5xx, respuesta ilegible).
#: Mañana puede funcionar, y por eso ni se recuerda ni se confunde con el anterior.
MOTIVO_VISION_ILEGIBLE = "no se pudo comprobar si el modelo admite imágenes"

#: [T-7.27] Lo que rotula cada sección redactada con asistencia, en el propio título.
#:
#: El §16 ya llevaba `NARRATIVE_AI_NOTE`, que es la frase larga y va al FINAL, después
#: de seis párrafos. No compiten: ésta es la etiqueta y aquélla la explicación, y un
#: test exige que salgan las dos o ninguna. Lo que no puede pasar —y pasaba— es que
#: quien hojea el documento lea la prosa entera antes de saber quién la escribió.
ROTULO_ASISTENCIA = "REDACTADO CON ASISTENCIA DE IA · NO ES EL VEREDICTO"

#: ──────────────────────── [T-7.26·2ª vuelta] los motivos del proveedor REMOTO
#:
#: Vivían sueltos dentro de `openrouter.py`, escritos a mano y sin el sufijo, de modo
#: que el PDF tenía DOS vocabularios para el mismo hecho: «el proveedor de redacción
#: falló (RuntimeError); texto determinista» por el cinturón, y «el proveedor no
#: respondió (HTTPStatusError)» por el camino que corre en producción.
#:
#: ⚠️ Y el segundo era FALSO en el caso que más importa. Con la clave revocada
#: OpenRouter **sí responde** —con un 401— y el papel decía «no respondió», que manda a
#: quien depure a mirar la red en vez del secreto. Son tres hechos distintos y hoy
#: llevan tres frases distintas, con el código HTTP dentro:
MOTIVO_PROVEEDOR_MUDO = "el proveedor de redacción no respondió"
#: 401/403: el proveedor contestó, y lo que contestó es que la credencial no vale. Es
#: el control negativo del criterio 4 de la ficha (la clave revocada) y el que tiene
#: que llevar a quien lea el papel al secreto, no al cable.
MOTIVO_PROVEEDOR_CREDENCIAL = "el proveedor de redacción no aceptó la clave"
#: Cualquier otro estado HTTP —incluido el 400 de un slug de modelo que ya no existe.
MOTIVO_PROVEEDOR_ESTADO = "el proveedor de redacción respondió con error"
MOTIVO_RESPUESTA_ILEGIBLE = "la respuesta del proveedor no se pudo interpretar" + (
    SUFIJO_DETERMINISTA
)
#: Prefijo: la razón concreta la compone `motivo_guardrail`, porque la escribe el
#: propio guardrail y enumerar aquí sus cinco frases sería un censo a mano.
MOTIVO_GUARDRAIL = "guardrail"

#: [T-7.27·A] La petición no cabe en el tope declarado y **no se emite**.
#:
#: `TOPE_PETICION_BYTES` existía desde T-7.27 y **nadie la comprobaba**: era una cota
#: declarada en una constante y medida en un test, sin una sola lectura en producción.
#: El techo de las fotografías sí está garantizado por construcción; el del TEXTO no lo
#: está por ninguna parte —`incident_actions` es append-only y exenta de poda, y la red
#: no tiene cota—, así que el incidente más cargado, que es el único en el que la cota
#: podía importar, era justo el que salía sin mirarla. Se degrada y se dice, en vez de
#: mandar un cuerpo que el proveedor va a rechazar con un estado que no explica nada.
MOTIVO_PETICION_ENORME = "la petición de redacción de este incidente rebasa su tope"


def motivo_con_causa(motivo: str, causa: str) -> str:
    """`<motivo> (<causa>); texto determinista`.

    **La causa nunca es el mensaje de una excepción ajena.** Es un nombre corto que
    escribimos o elegimos nosotros: el tipo de la excepción, el código de error de AWS
    (`AccessDeniedException`) o el estado HTTP (`HTTP 401`). El mensaje de botocore es
    del tipo «… not authorized to perform secretsmanager:GetSecretValue on resource
    arn:aws:…:634…»: se lleva por delante el ARN y el número de cuenta, y esto acaba
    impreso en un documento que sale de la organización.

    ⚠️ La regla decía «es un NOMBRE» a secas y por una rama recibía una frase entera en
    castellano (`resolve_api_key`, cuando el secreto existe y no trae la clave). No
    filtraba nada —la frase la escribimos nosotros—, pero la regla escrita ya no se
    cumplía, así que aquella rama pasó a devolver un código y esto pasó a decir cuál es
    la propiedad de verdad. Lo vigila `test_glosario_de_motivos.py`.
    """
    return f"{motivo} ({causa}){SUFIJO_DETERMINISTA}"


def motivo_guardrail(razon: str) -> str:
    """`guardrail: <razón>; texto determinista`.

    La razón la escribe `openrouter.guard` y es prosa nuestra, no del proveedor: lo
    único que puede traer de fuera son los títulos de sección que propuso y las cifras
    que se inventó, que es exactamente lo que hay que poder leer después.
    """
    return f"{MOTIVO_GUARDRAIL}: {razon}{SUFIJO_DETERMINISTA}"


@dataclass(frozen=True, slots=True)
class EstacionRedactada:
    """[T-7.27] Una estación de la red, sin decir QUIÉN es.

    Cada estación de la red es otro edificio con gente dentro: su nombre, su código y
    el de su sensor son exactamente lo que esta allowlist mantiene fuera para el
    inmueble propio. Lo que la prosa necesita para poder hablar de una fila es poder
    NOMBRARLA, y para eso basta su orden en la tabla que el documento imprime.
    """

    #: 1-based, el mismo orden de la §7 del informe: «la estación 2» es la misma en el
    #: papel y en la prosa.
    orden: int
    #: ¿Es el inmueble del incidente? El código del sitio propio ya viaja dentro del
    #: folio, así que esto no añade nada nuevo y evita que la prosa confunda el pico
    #: del edificio con el de un vecino.
    propia: bool
    dist_km: float | None
    t_teorico_s: float | None
    t_medido_s: float | None
    peak_pga_g: float | None
    #: El umbral contra el que se decidió, CON su procedencia: sin ella un `0.07 g`
    #: parece del inmueble aunque sea el de referencia (`T-7.35`).
    umbral_pga_g: float | None
    umbral_origen: str | None
    tier: str | None


@dataclass(frozen=True, slots=True)
class HitoRedactado:
    """[T-7.27] Una fila de la cronología, con su hora y sin su autor.

    Hasta esta ficha la bitácora viajaba **agregada a conteos por tipo**: la prosa sabía
    que hubo dos acuses y no podía decir en qué orden pasó nada.
    """

    #: Segundos desde la apertura del incidente. No la hora absoluta: `opened_at` ya
    #: viaja y con el desplazamiento la prosa puede contar la secuencia sin hacer
    #: aritmética —que es justo donde un modelo se inventa un número.
    t_desde_apertura_s: float
    kind: str
    #: Lo que ese verbo dice en castellano (`dictamen/bitacora.ROTULOS`), o ``None``
    #: cuando el registro no sabe rotularlo. Inventar un rótulo sería peor que
    #: declarar que no lo hay: `incident_actions` es append-only y trae verbos viejos.
    rotulo: str | None
    #: La CLASE del actor (`user`, `edge`, `system`…), jamás el identificador: el de
    #: una persona es su `sub` de Cognito y el del gabinete, su número de serie.
    actor: str


@dataclass(frozen=True, slots=True)
class DanoRedactado:
    """[T-7.27] Un reporte de daños del brigadista, por ROL y por categoría.

    `D-32` literal: «el brigadista aparece por **rol**, nunca por nombre». Lo que no
    entra, y es la mitad del trabajo: la NOTA del reporte y la de cada categoría son
    prosa libre que una persona teclea en el teléfono —hasta 2000 caracteres, sin
    validar— y pueden llevar el nombre de un ocupante o el número de un departamento.
    Tampoco el nombre de la zona, que lo escribe el cliente en su propio catálogo.
    """

    orden: int
    rol: str | None
    personas_en_riesgo: bool
    #: `(clave, severidad)` del catálogo cerrado de la app (`schemas/mobile.py`), que
    #: son enumeraciones nuestras y no texto de nadie.
    categorias: tuple[tuple[str, str], ...]
    fotos_adjuntas: int
    #: Cuántas fotografías de ESTE reporte no viajan (ilegibles, sin blob, fuera del
    #: tope o del presupuesto). Se declara por la misma razón que el papel declara las
    #: que no imprime: seis de once sin decirlo es recortar la evidencia en silencio.
    fotos_no_adjuntas: int


@dataclass(frozen=True, slots=True)
class ImagenAdjunta:
    """[T-7.27] Una fotografía lista para viajar como contenido multimodal.

    **No es un campo de `NarrativeFacts` a propósito.** Los hechos son texto que se
    serializa entero como prompt de usuario y que los tests inspeccionan buscando
    cadenas; meter aquí un blob los volvería ilegibles y pondría megabytes en cada
    `asdict`. Las imágenes viajan por su propio canal, con su propia allowlist
    (`redact.imagenes_de`), y los hechos declaran CUÁNTAS son.
    """

    #: Los bytes que VIAJAN: la derivada de `documentos/fotos.preparar` **con la banda
    #: de la marca de agua forense tapada** (`narrative/marca.py`). Nunca el blob crudo
    #: de S3 —ver `redact.imagenes_de` para la medición que lo prohíbe— y nunca la
    #: derivada sin tapar, que lleva dibujados en el píxel las coordenadas del inmueble
    #: y el identificador del operador.
    jpeg: bytes
    #: `sha256` de lo impreso — el mismo número que el papel publica para esa foto.
    #:
    #: ⚠️ [T-7.27·A] **Ya no es la huella de lo que viaja**, y eso es una consecuencia
    #: declarada del tapado: pintar encima cambia los píxeles. Se conserva porque es lo
    #: único que ata la fotografía que vio el modelo con la que imprime el documento;
    #: la que se puede verificar contra el tercero es `sha256_enviado`.
    sha256: str | None
    #: `sha256` de los bytes que SALIERON de la nube. Es el que va a la procedencia.
    sha256_enviado: str
    ancho: int | None
    alto: int | None
    #: Orden del reporte de daños del que salió, para que la prosa pueda decir de qué
    #: reporte es la fotografía que está describiendo.
    reporte: int


@dataclass(frozen=True, slots=True)
class HuellaEnviada:
    """[T-7.27·A] Qué fotografía salió, con las DOS huellas que hacen falta.

    Con una sola no se contesta la pregunta. `enviado` es el sha256 de los bytes que
    cruzaron la frontera: es el único número que alguien puede recalcular sobre lo que
    tenga el tercero. `impreso` es el de la derivada del papel: es el único que ata esa
    transferencia a una fotografía concreta del expediente. Desde que la banda de la
    marca de agua se tapa (`narrative/marca.py`) **los dos números son distintos**, y
    registrar solo uno dejaba la mitad de la trazabilidad fuera.
    """

    enviado: str
    impreso: str | None


@dataclass(frozen=True, slots=True)
class NarrativeFacts:
    """Hechos redactados del incidente. Los produce ``redact.facts_from``.

    Contiene el veredicto porque es una **entrada**: la prosa tiene que poder explicar
    por qué se dictaminó lo que se dictaminó. Lo que ningún proveedor puede hacer es
    devolver uno distinto — ver ``Narrative``.
    """

    folio: str
    opened_at: str
    severity: str
    trigger: str
    #: [T-7.36] Con qué se ABRIÓ. `trigger` es la última escalada: la ingesta lo
    #: sobrescribe, así que decir «se abrió a partir de» con él es falso en cuanto
    #: un incidente escala.
    opened_trigger: str
    state: str
    event_source: str | None

    verdict_label: str
    verdict_status: str | None
    verdict_signed: bool
    verdict_actions: tuple[str, ...]
    rule_set_version: str | None
    basis: dict = field(default_factory=dict)
    #: [T-7.38·E] ¿Consta una razón ESCRITA POR UNA PERSONA al firmar? Booleano, no
    #: el texto: la nota del inspector es prosa libre sin validar y la allowlist de
    #: `redact` existe para que no salga de la nube. Y es la CONJUNCIÓN «firmada Y
    #: con nota»: `rules.py` mete `notes` enlatado en todo dictamen automático, así
    #: que la clave sola no distingue una razón de una cadena de fábrica.
    reason_recorded: bool = False

    site_criticality: str | None = None
    felt_band: str = "unknown"
    felt_label: str = ""
    calibrated: bool = False
    peak_pga_g: float | None = None
    peak_pgv_cms: float | None = None
    lead_time: str = ""
    station_count: int = 0
    catalog_line: str | None = None
    #: [T-7.27] La tabla por estación, la misma que imprime la §7 del informe. Hasta
    #: esta ficha viajaba SOLO `station_count`: un entero con el que la prosa no podía
    #: decir una sola cosa de una estación concreta sin inventársela.
    stations: tuple[EstacionRedactada, ...] = ()
    #: [T-7.27] ¿El evento enlazado es la reproducción de un sismo HISTÓRICO? El papel
    #: lo declara en su §7 (`REPRODUCCION_NOTE`) y la prosa no lo sabía: podía redactar
    #: como sismo de hoy lo que el mismo documento rotula como ensayo tres páginas
    #: antes.
    reproduccion: bool = False

    channel_count: int = 0
    clipped_channels: tuple[str, ...] = ()
    action_counts: tuple[tuple[str, int], ...] = ()
    #: Reportes de daño, SOLO como conteo por categoría. Nunca el texto del ocupante.
    #: [T-7.27] Y ya no llega vacío siempre: se DERIVA del modelo. El canal existía
    #: —`facts_from(..., damage_counts=…)`— y el único llamador de producción no lo
    #: pasaba nunca, así que el campo era un hueco con nombre de dato.
    damage_counts: tuple[tuple[str, int], ...] = ()
    #: [T-7.27] La cronología con marca de tiempo y clase de actor.
    timeline: tuple[HitoRedactado, ...] = ()
    #: [T-7.27] Los reportes de daño, por rol y por categoría.
    damage_reports: tuple[DanoRedactado, ...] = ()
    #: [T-7.27] Cuántas fotografías se ADJUNTAN a esta petición y cuántas tiene el
    #: incidente. Las dos, y no solo la primera: si el modelo ve seis y el incidente
    #: tiene once, tiene que saber que está mirando una parte —es la misma honestidad
    #: que `DanoFila.fotos_omitidas` le exige al papel.
    photos_attached: int = 0
    photos_available: int = 0
    dictamen_count: int = 0
    has_epicenter: bool = False
    has_raw_waveform: bool = False
    #: [T-7.38·L] ¿CONSTA un objeto miniSEED en la cadena de custodia? `has_raw_waveform`
    #: responde a otra pregunta —«¿se decodificó?»— y la prosa decía «no hay forma de
    #: onda cruda archivada» sobre un incidente cuyo §10 lista el miniSEED con su hash.
    has_archived_miniseed: bool = False
    #: Cada dato que falta, con su razón. Es la materia prima de "Limitaciones".
    absences: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class NarrativeRequest:
    """Lo que se le pide a un proveedor: hechos redactados y nada más."""

    facts: NarrativeFacts
    #: Slug del modelo. Vacío ⇒ ningún proveedor remoto puede correr (ver settings).
    model: str = ""
    #: [T-7.27] Las fotografías del brigadista, ya derivadas. Vacío ⇒ el mensaje de
    #: usuario sigue siendo texto plano, exactamente como antes de esta ficha.
    images: tuple[ImagenAdjunta, ...] = ()


@dataclass(frozen=True, slots=True)
class Narrative:
    """Lo único que un proveedor puede devolver.

    **No tiene campo de veredicto, estado, prioridad ni severidad**, y un contract-test
    lo verifica sobre los nombres de los campos (``test_contract.py``). Añadir uno
    rompería el build antes de que pudiera llegar a un dictamen.
    """

    sections: tuple[tuple[str, str], ...]
    provider: str
    model: str | None = None
    #: Por qué se cayó al proveedor determinista, si se cayó. Se imprime en el PDF.
    degraded_reason: str | None = None
    latency_ms: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost_usd: float | None = None
    #: [T-7.26] Versión del prompt con el que se pidió esta prosa. Se DERIVA del texto
    #: de las plantillas (``prompts.prompt_version``), no se teclea: un número a mano
    #: se queda viejo al primer retoque de redacción y entonces el campo no significa
    #: nada. ``None`` = no se mandó ningún prompt (nadie consultó a un modelo).
    prompt_version: str | None = None
    #: [T-7.27] Las huellas de las fotografías que SALIERON de la nube en esta
    #: petición. Es la única forma de contestar «¿qué fotografías se mandaron a un
    #: tercero?», que es la pregunta que deja abierta el consentimiento contractual
    #: pendiente de `D-32`. Van las huellas y no los bytes: esto acaba en `audit_log`,
    #: que por la regla de oro 11 no se poda nunca.
    #:
    #: ⚠️ [T-7.27·A] Vacío cuando la petición **no llegó a salir**. Antes se rellenaba
    #: en la rama de fallo sin mirar de qué fallo se trataba, y un `ConnectError` —el
    #: socket no se abre siquiera— dejaba escrito en un registro que no se poda que unas
    #: fotografías habían viajado a otro país. Ver `openrouter._salieron_las_fotos`.
    photos_sent: tuple[HuellaEnviada, ...] = ()
    #: [T-7.26] sha256 de lo que devolvió el modelo, ANTES de parsear, de aplicar el
    #: guardrail y de recortar. ``None`` = no volvió nada. Cuando la respuesta se
    #: DESCARTA es cuando más falta hace: es el único rastro de qué se propuso.
    output_sha256: str | None = None

    def provenance(self) -> dict:
        """Procedencia para ``audit_log`` (verbo ``narrative_generated``).

        No hay tabla nueva: la narrativa queda congelada en el PDF, que ya es evidencia
        inmutable con sha256; la procedencia va al log append-only y sin poda.
        """
        return {
            "provider": self.provider,
            "model": self.model,
            "degraded_reason": self.degraded_reason,
            "latency_ms": self.latency_ms,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cost_usd": self.cost_usd,
            "prompt_version": self.prompt_version,
            "output_sha256": self.output_sha256,
            # Las DOS huellas por fotografía: la que se puede verificar contra el
            # tercero y la que la ata al documento. Ver `HuellaEnviada`.
            "photos_sent": [{"enviado": h.enviado, "impreso": h.impreso} for h in self.photos_sent],
            # Los TÍTULOS, no la prosa: el texto ya queda congelado en el PDF —que es
            # evidencia con sha256— y duplicarlo en una tabla que no se poda jamás
            # sería guardar el documento dos veces.
            "sections": [title for title, _ in self.sections],
        }


class NarrativeProvider(Protocol):
    """Contrato mínimo de un proveedor de prosa."""

    name: str

    async def generate(self, req: NarrativeRequest) -> Narrative: ...
