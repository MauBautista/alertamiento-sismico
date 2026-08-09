"""Contratos de las etiquetas de cumplimiento (T-2.82).

Lo que sale por el cable lleva SIEMPRE su marco: ``provenance`` y ``notice`` no son
campos opcionales de adorno — son la diferencia entre "el cliente declara esto" y "esto
es un hecho verificado". Van en el payload y no en el cliente a propósito: una pantalla
futura puede olvidarse de pintar un texto que es suyo; no puede olvidarse de uno que
llega dentro del dato.

Las reglas semánticas (catálogo cerrado, referencia obligatoria, sin duplicados) viven
en ``takab_api.compliance``: un solo validador para el cuerpo HTTP y para lo que se lee
de la base. Aquí solo está la forma.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from takab_api.compliance import (
    CATALOG,
    DECLARED_NOTICE,
    PROVENANCE,
    ComplianceDocument,
    compliance_block,
)


class ComplianceClaimIn(BaseModel):
    """Una afirmación tal como llega del formulario.

    ``extra="forbid"`` es una cerradura, no higiene: rechaza de plano un cuerpo con
    ``verified: true`` o ``provenance: "verified_by_takab"``. Ignorarlo en silencio
    dejaría creer al operador que su marca de verificación se guardó.
    """

    model_config = ConfigDict(extra="forbid")

    key: str
    claim: str
    reference: str


class ComplianceLabelsIn(BaseModel):
    """Reemplazo COMPLETO del documento del cliente.

    No es un PATCH: las etiquetas se leen juntas (en un dictamen se imprimen juntas),
    así que se editan juntas y el testigo de concurrencia protege al conjunto.
    """

    model_config = ConfigDict(extra="forbid")

    items: list[ComplianceClaimIn]
    #: ``updated_at`` que el editor tenía a la vista. Si el servidor tiene otro ⇒ 409.
    #: Ausente = "no lo comprobé" (mismo criterio opcional que ``base_row_version``).
    base_updated_at: datetime | None = None


class ComplianceClaimOut(BaseModel):
    """Afirmación servida. ``title`` lo pone el catálogo del SERVIDOR.

    Sin el título, ``claim`` es un string suelto que cada pantalla enmarcaría a su
    manera. Con él, la frase completa es siempre "de esta clase, el cliente declara
    esto, y aquí está escrito".
    """

    key: str
    title: str
    claim: str
    reference: str


class ComplianceDocOut(BaseModel):
    """Documento del cliente + su marco. Nunca sale uno sin el otro.

    Lo consumen dos superficies: la ficha del cliente en ``/tenants`` y el forense del
    incidente (``ForensicsOut.compliance``), que es lo que ve el inspector en la misma
    pantalla en la que FIRMA. Un solo shape para las dos: si cada una compusiera su
    propio marco, tarde o temprano una de ellas se quedaría sin él.

    ``json_schema_serialization_defaults_required`` hace que el CONTRATO diga lo mismo
    que este docstring. Todos los campos de abajo llevan default, y un campo con
    default no es ``required`` en el esquema de serialización: el OpenAPI publicado
    declaraba que ``provenance`` y ``notice`` **pueden faltar**, cuando el servidor los
    manda siempre. De ese esquema salen los tipos del SDK, así que la consola tuvo que
    escribir a mano un tipo afirmando lo contrario — dos verdades sobre el mismo cable,
    y la que mentía era la publicada. Anclado en
    ``test_el_marco_declarado_viaja_ENTERO_o_no_viaja``.
    """

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    #: Única procedencia posible mientras GATE-LEGAL siga abierto.
    provenance: str = PROVENANCE
    #: Deslinde PERMANENTE. Es el que acompaña al FORMULARIO: quien teclea una
    #: afirmación normativa tiene que estar leyendo, mientras la teclea, que TAKAB no
    #: la respalda. No depende del estado del documento.
    notice: str = DECLARED_NOTICE
    items: list[ComplianceClaimOut] = []
    #: Lo que hay que IMPRIMIR de este documento concreto, ya resuelto: el deslinde si
    #: hay afirmaciones, el literal de ausencia si no las hay, o la razón de
    #: ilegibilidad. Sale de ``compliance.compliance_block`` — la MISMA función que usa
    #: el dictamen PDF. Así las palabras del papel y las de la pantalla no pueden
    #: divergir, que es de donde salen las discrepancias que nadie perdona.
    notes: list[str] = []
    #: Por qué no se puede transcribir el registro, si es el caso. Excluyente con
    #: ``items``: nunca se sirve media verdad.
    unreadable: str | None = None


class ComplianceLabelsOut(ComplianceDocOut):
    """El documento del cliente en su ficha, con quién lo tocó y cuándo."""

    tenant_id: UUID
    updated_at: datetime | None = None
    updated_by: UUID | None = None


def doc_out(doc: ComplianceDocument) -> ComplianceDocOut:
    """``ComplianceDocument`` (interno, puro) → contrato público."""
    return ComplianceDocOut(
        items=[
            ComplianceClaimOut(
                key=c.key, title=CATALOG[c.key], claim=c.claim, reference=c.reference
            )
            for c in doc.items
        ],
        notes=list(compliance_block(doc).notes),
        unreadable=doc.unreadable,
    )
