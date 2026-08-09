"""Etiquetas de cumplimiento por tenant (T-2.82) — modelo PURO, sin DB ni HTTP.

Una etiqueta de cumplimiento **no es un dato de configuración: es una afirmación
normativa**, y acaba impresa en un dictamen que alguien firma y que puede llegar ante
un perito. Este repositorio ya se quemó con exactamente eso: la consola llegó a citar
``NOM-003-SCT`` —una norma de **transporte**— como si fuera el marco sísmico del
producto (regla de oro 11 de ``CLAUDE.md``; ``ESPECIFICACION-APP-MOVIL.md §13`` la
lista entre las cosas PROHIBIDAS, y §2.1-C fija el remedio: los strings normativos se
sirven por tenant, nunca hardcodeados).

Servir un ``jsonb`` libre y pintarlo con aire oficial reproduciría el mismo error a
escala. Las cerraduras que lo impiden, y por qué cada una:

1. **Catálogo cerrado de CLASES de afirmación** (``CATALOG``), no de normas. No se
   puede teclear una norma como si fuera una clave del sistema: se elige *qué tipo de
   cosa* se está afirmando y el texto concreto viaja como contenido del cliente. El
   catálogo, deliberadamente, **no nombra ninguna norma** — TAKAB no tiene todavía un
   marco citable confirmado (``GATE-LEGAL``, ``blueprint §9``) y fabricar uno aquí
   sería repetir el fallo con otro nombre.
2. **La procedencia no es un campo: es estructural.** Todo lo que vive en
   ``compliance_labels`` es, por definición, una declaración del cliente. No existe
   ningún hueco donde escribir "verificado por TAKAB", así que no hay nada que
   falsificar — ni desde un cuerpo HTTP ni desde un ``INSERT`` a mano.
3. **Referencia citable obligatoria.** No basta con afirmar: hay que decir *dónde lo
   dice*. No convierte la afirmación en verdad, pero la vuelve **seguible** por quien
   tenga que comprobarla, que es justo lo que faltó con ``NOM-003-SCT``.
4. **Lo ilegible se declara ilegible.** La política ``cl_admin`` del DDL deja escribir
   esta tabla a cualquier identidad interna TAKAB, también por ``psql``. Un documento
   que este módulo no entienda no se transcribe a medias ni desaparece en silencio:
   se rotula. Las dos alternativas acaban en un documento firmado.

Cuando ``GATE-LEGAL`` cierre y exista un marco citable confirmado, lo que cambia es
``DOCUMENT_VERSION`` y el catálogo — no el contrato de esta capa ni las superficies
que la pintan.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Versión del documento almacenado en ``compliance_labels.labels``. Es la costura
#: que deja evolucionar el formato sin que un render viejo interprete mal uno nuevo:
#: una versión desconocida se declara ilegible, jamás se adivina.
DOCUMENT_VERSION = 1

#: Catálogo CERRADO de clases de afirmación. Ninguna entrada nombra una norma: son
#: categorías de *quién* respalda lo que se afirma. Añadir una entrada es una decisión
#: de producto, no un formulario libre.
CATALOG: dict[str, str] = {
    "regulatory_framework": "Marco al que el cliente declara estar sujeto",
    "internal_protocol": "Protocolo interno del cliente",
    "third_party_certification": "Certificación emitida por un tercero",
    "insurance_requirement": "Requisito de la aseguradora del cliente",
    "contractual_obligation": "Obligación contractual del cliente",
}

#: Tope de afirmaciones por cliente. Coincide con el tamaño del catálogo porque las
#: clases no se repiten; existe como cinturón por si el catálogo crece.
MAX_CLAIMS = len(CATALOG)

#: Tope de caracteres de cada texto. Una etiqueta es una frase citable, no un anexo.
MAX_TEXT = 280

#: Única procedencia posible mientras GATE-LEGAL siga abierto.
PROVENANCE = "declared_by_tenant"

#: Aviso corto: viaja PEGADO a cada afirmación en la superficie móvil, porque la
#: pantalla 1.5 (``ReentryBlockedView``) pinta el valor y descarta la clave. Dice las
#: dos cosas que hay que decir: quién lo afirma y quién NO lo respalda.
DECLARED_SHORT = "Declarado por el cliente; TAKAB no lo verifica ni certifica su cumplimiento."

#: Aviso largo: acompaña al bloque en la consola y en el dictamen PDF. Nombra
#: GATE-LEGAL para que quien firme sepa que la plataforma tampoco tiene marco propio.
DECLARED_NOTICE = (
    "Las afirmaciones de este apartado las DECLARA el cliente. TAKAB Ailert no las "
    "verifica, no las certifica y no emite dictamen de cumplimiento normativo. El marco "
    "normativo citable de la plataforma está pendiente de confirmación (GATE-LEGAL); "
    "ninguna referencia de este apartado procede de TAKAB."
)

#: Ausencia. Un cliente sin etiquetas NO es un cliente conforme ni un cliente
#: incumplidor: es un cliente que no declaró nada. Decirlo con todas las letras evita
#: que un cuadro vacío se lea como cualquiera de las dos cosas.
NO_CLAIMS = (
    "SIN MARCO NORMATIVO DECLARADO POR EL CLIENTE · la ausencia de etiquetas no "
    "significa cumplimiento ni incumplimiento: significa que no se declaró ninguna."
)

_UNREADABLE_HEAD = "ETIQUETAS DE CUMPLIMIENTO ILEGIBLES · no se transcribe nada"

#: El shape viejo (mapa plano clave→texto) no dice de qué clase es la afirmación ni
#: dónde está escrita: no se puede enmarcar, luego no se publica.
UNREADABLE_LEGACY = (
    f"{_UNREADABLE_HEAD}: el registro del cliente está en un formato anterior que no "
    "declara ni la clase de la afirmación ni su referencia citable."
)

UNREADABLE_VERSION = (
    f"{_UNREADABLE_HEAD}: el registro del cliente declara una versión de documento que "
    "este sistema no sabe interpretar."
)

UNREADABLE_MALFORMED = (
    f"{_UNREADABLE_HEAD}: el registro del cliente no tiene la forma que este sistema "
    "sabe interpretar."
)

#: Clave reservada de la proyección móvil para el aviso de ilegibilidad. Empieza por
#: "_" para no colisionar jamás con una clave del catálogo.
UNREADABLE_KEY = "_ilegible"


class ComplianceError(ValueError):
    """Afirmación que el sistema se niega a guardar, con la razón en el mensaje."""


@dataclass(frozen=True, slots=True)
class ComplianceClaim:
    """Una afirmación del cliente.

    Tres campos y ni uno más. En particular **no hay campo de verificación**: no es un
    default que se pueda sobrescribir, es que no existe el hueco.
    """

    key: str
    claim: str
    reference: str


@dataclass(frozen=True, slots=True)
class ComplianceDocument:
    """Lo que se puede afirmar de un cliente, o por qué no se puede afirmar nada."""

    items: tuple[ComplianceClaim, ...] = ()
    #: Razón por la que el registro no se pudo leer. Excluyente con ``items``.
    unreadable: str | None = None

    @property
    def declared(self) -> bool:
        """¿Hay algo que el cliente haya declarado y este sistema entienda?"""
        return bool(self.items)


def _text(raw: object, *, field: str) -> str:
    if not isinstance(raw, str):
        raise ComplianceError(f"{field}: se esperaba texto")
    value = raw.strip()
    if not value:
        raise ComplianceError(f"{field}: no puede ir en blanco")
    if len(value) > MAX_TEXT:
        raise ComplianceError(f"{field}: supera {MAX_TEXT} caracteres")
    return value


def build_claims(raw_items: object) -> tuple[ComplianceClaim, ...]:
    """Valida la lista de afirmaciones que llega de fuera. Lanza ``ComplianceError``.

    Rechaza campos desconocidos a propósito: un cuerpo con ``verified: true`` no se
    ignora en silencio — se rechaza, para que quien lo intentó se entere.
    """
    if not isinstance(raw_items, list):
        raise ComplianceError("items: se esperaba una lista de afirmaciones")
    if len(raw_items) > MAX_CLAIMS:
        raise ComplianceError(f"items: máximo {MAX_CLAIMS} afirmaciones por cliente")

    claims: list[ComplianceClaim] = []
    seen: set[str] = set()
    for raw in raw_items:
        if not isinstance(raw, dict):
            raise ComplianceError("items: cada afirmación debe ser un objeto")
        extra = set(raw) - {"key", "claim", "reference"}
        if extra:
            raise ComplianceError(f"campos no admitidos: {sorted(extra)}")
        key = raw.get("key")
        if not isinstance(key, str) or key not in CATALOG:
            raise ComplianceError(f"key fuera del catálogo: {key!r}")
        if key in seen:
            raise ComplianceError(f"key repetida: {key!r}")
        seen.add(key)
        claims.append(
            ComplianceClaim(
                key=key,
                claim=_text(raw.get("claim"), field="claim"),
                reference=_text(raw.get("reference"), field="reference"),
            )
        )
    return tuple(claims)


def to_storage(claims: tuple[ComplianceClaim, ...]) -> dict:
    """Documento tal cual se guarda en ``compliance_labels.labels``."""
    return {
        "version": DOCUMENT_VERSION,
        "items": [{"key": c.key, "claim": c.claim, "reference": c.reference} for c in claims],
    }


def parse_document(raw: object) -> ComplianceDocument:
    """Lee el ``jsonb`` guardado. Nunca lanza: lo que no entiende, lo rotula.

    Es la mitad defensiva de la cerradura 4: ``cl_admin`` permite escribir esta tabla
    por ``psql`` a cualquier identidad interna, así que este lector no puede suponer
    que el escritor fue la API.
    """
    if raw is None:
        return ComplianceDocument()
    if not isinstance(raw, dict) or isinstance(raw, bool):
        return ComplianceDocument(unreadable=UNREADABLE_MALFORMED)
    if not raw:
        # `'{}'` es el DEFAULT del DDL: "no se declaró nada", no "ilegible".
        return ComplianceDocument()
    if "version" not in raw:
        return ComplianceDocument(unreadable=UNREADABLE_LEGACY)
    version = raw["version"]
    if not isinstance(version, int) or isinstance(version, bool) or version != DOCUMENT_VERSION:
        return ComplianceDocument(unreadable=UNREADABLE_VERSION)
    try:
        return ComplianceDocument(items=build_claims(raw.get("items")))
    except ComplianceError:
        return ComplianceDocument(unreadable=UNREADABLE_MALFORMED)


@dataclass(frozen=True, slots=True)
class ComplianceBlock:
    """Lo que un documento imprime de este apartado, ya resuelto en texto.

    Vive aquí y no en ``dictamen/pdf.py`` por el mismo motivo que ``dictamen/model.py``
    está separado del render: el contenido —que es donde puede haber una mentira— se
    prueba palabra por palabra sin abrir un PDF.
    """

    rows: tuple[tuple[str, str], ...] = ()
    notes: tuple[str, ...] = ()


def compliance_block(doc: ComplianceDocument) -> ComplianceBlock:
    """Bloque imprimible del marco declarado. **Nunca sale mudo.**

    Los tres estados dicen algo distinto y ninguno es el silencio: un apartado en
    blanco dentro de un dictamen firmado se lee como "todo en orden", que es
    justamente la afirmación que nadie hizo.
    """
    if doc.unreadable is not None:
        return ComplianceBlock(notes=(doc.unreadable,))
    if not doc.items:
        return ComplianceBlock(notes=(NO_CLAIMS,))
    rows: list[tuple[str, str]] = []
    for claim in doc.items:
        rows.append((CATALOG[claim.key].upper(), claim.claim))
        rows.append(("DÓNDE LO DICE", claim.reference))
    return ComplianceBlock(rows=tuple(rows), notes=(DECLARED_NOTICE,))


def mobile_projection(doc: ComplianceDocument) -> dict[str, str]:
    """Mapa ``clave → texto`` para ``GET /sites/{id}/mobile-state``.

    El contrato publicado es ``dict[str, str]`` y la pantalla 1.5 del móvil pinta el
    VALOR descartando la clave (``ReentryBlockedView``). Por eso cada valor se enmarca
    a sí mismo: sin eso, el ocupante lee una afirmación normativa desnuda bajo un
    letrero de "REINGRESO PROHIBIDO".

    Vacío devuelve ``{}`` — vacío ⇒ NADA normativo (§2.1-C). Inventar aquí un aviso
    sería exactamente el string hardcodeado que la spec prohíbe.
    """
    if doc.unreadable is not None:
        return {UNREADABLE_KEY: doc.unreadable}
    return {c.key: f"{CATALOG[c.key]}: {c.claim} · {DECLARED_SHORT}" for c in doc.items}
