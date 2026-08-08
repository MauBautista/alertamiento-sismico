"""El marco declarado dentro del dictamen (T-2.82).

Un dictamen es un documento que alguien FIRMA y que puede acabar ante un perito. Lo
que este apartado imprime es la parte del documento que TAKAB no midió ni verificó:
son afirmaciones del cliente. El contenido se prueba sobre el bloque —que es donde
podría colarse una mentira— y el render sobre la propiedad que un revisor externo
comprobaría: que cambiar las etiquetas cambia el PDF y su huella de contenido.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from takab_api.compliance import (
    CATALOG,
    DECLARED_NOTICE,
    NO_CLAIMS,
    UNREADABLE_LEGACY,
    ComplianceClaim,
    ComplianceDocument,
    compliance_block,
)
from takab_api.dictamen.pdf import render

from .test_pdf import model

_OPENED = datetime(2026, 8, 3, 10, 0, 0, tzinfo=UTC)

_MARCO = ComplianceClaim(
    key="regulatory_framework",
    claim="Reglamento de Construcciones del DF, Título Sexto",
    reference="Gaceta Oficial del DF, 29/01/2004, art. 139",
)
_PROTOCOLO = ComplianceClaim(
    key="internal_protocol",
    claim="Plan interno de protección civil, revisión 2026",
    reference="Acta del comité de seguridad, 14/03/2026",
)


# --- El bloque: qué se imprime, palabra por palabra --------------------------


def test_un_cliente_sin_etiquetas_NO_se_imprime_como_conforme() -> None:
    """Un hueco en blanco en un dictamen se lee como "todo en orden". Aquí se dice, y
    se dice en las dos direcciones: ni cumplimiento ni incumplimiento."""
    bloque = compliance_block(ComplianceDocument())
    assert bloque.rows == ()
    assert bloque.notes == (NO_CLAIMS,)


def test_con_etiquetas_cada_afirmacion_lleva_su_clase_y_su_referencia() -> None:
    bloque = compliance_block(ComplianceDocument(items=(_MARCO, _PROTOCOLO)))
    assert bloque.rows == (
        (CATALOG["regulatory_framework"].upper(), _MARCO.claim),
        ("DÓNDE LO DICE", _MARCO.reference),
        (CATALOG["internal_protocol"].upper(), _PROTOCOLO.claim),
        ("DÓNDE LO DICE", _PROTOCOLO.reference),
    )


def test_con_etiquetas_el_deslinde_va_SIEMPRE_debajo() -> None:
    """Sin esta nota, dos renglones con aire oficial dentro de un documento firmado
    pasan por hechos verificados. Es la lección de la cita a NOM-003-SCT."""
    assert compliance_block(ComplianceDocument(items=(_MARCO,))).notes == (DECLARED_NOTICE,)


def test_el_deslinde_dice_las_tres_cosas_que_tiene_que_decir() -> None:
    """Quién lo afirma, quién NO lo respalda, y que la plataforma tampoco tiene marco
    propio todavía. El texto es parte del trabajo, no relleno."""
    assert DECLARED_NOTICE == (
        "Las afirmaciones de este apartado las DECLARA el cliente. TAKAB Ailert no las "
        "verifica, no las certifica y no emite dictamen de cumplimiento normativo. El "
        "marco normativo citable de la plataforma está pendiente de confirmación "
        "(GATE-LEGAL); ninguna referencia de este apartado procede de TAKAB."
    )


def test_un_registro_ilegible_no_imprime_NADA_transcrito() -> None:
    """Si el registro del cliente no se entiende, el dictamen dice que no se entiende.
    Transcribirlo a medias sería afirmar sin respaldo; callarlo, mentir por omisión."""
    bloque = compliance_block(ComplianceDocument(unreadable=UNREADABLE_LEGACY))
    assert bloque.rows == ()
    assert bloque.notes == (UNREADABLE_LEGACY,)


def test_el_bloque_nunca_sale_mudo() -> None:
    """En los tres estados posibles hay algo escrito: un apartado en blanco dentro de
    un dictamen firmado es la peor de las tres salidas."""
    for doc in (
        ComplianceDocument(),
        ComplianceDocument(items=(_MARCO,)),
        ComplianceDocument(unreadable=UNREADABLE_LEGACY),
    ):
        bloque = compliance_block(doc)
        assert bloque.notes, doc
        assert all(nota.strip() for nota in bloque.notes), doc


# --- El render: que de verdad llegue al papel --------------------------------


@pytest.mark.parametrize("variant", ["technical", "executive"])
def test_las_etiquetas_cambian_los_BYTES_del_pdf(variant: str) -> None:
    """La prueba de que el apartado está cableado y no solo calculado."""
    sin = render(model(), variant)
    con = render(model(compliance=ComplianceDocument(items=(_MARCO,))), variant)
    assert sin != con
    assert con.startswith(b"%PDF")


@pytest.mark.parametrize("variant", ["technical", "executive"])
def test_dos_etiquetas_DISTINTAS_dan_pdfs_distintos(variant: str) -> None:
    """Sin esto, un render que imprimiera siempre el mismo rótulo fijo pasaría el test
    de arriba."""
    uno = render(model(compliance=ComplianceDocument(items=(_MARCO,))), variant)
    otro = render(model(compliance=ComplianceDocument(items=(_PROTOCOLO,))), variant)
    assert uno != otro


def test_las_etiquetas_entran_en_la_huella_de_contenido() -> None:
    """``content_sha256`` es lo que permite comparar dos exportaciones sin abrirlas.
    Si el marco declarado quedara fuera, se podría cambiar lo que el documento afirma
    sin que la huella se moviera."""
    base = model().content_sha256()
    assert base != model(compliance=ComplianceDocument(items=(_MARCO,))).content_sha256()
    assert (
        model(compliance=ComplianceDocument(items=(_MARCO,))).content_sha256()
        != model(compliance=ComplianceDocument(items=(_PROTOCOLO,))).content_sha256()
    )


def test_un_registro_ilegible_no_tumba_la_exportacion() -> None:
    """Una evidencia de compliance jamás se cae por un dato roto (mismo criterio que
    el miniSEED ilegible del builder)."""
    blob = render(model(compliance=ComplianceDocument(unreadable=UNREADABLE_LEGACY)))
    assert blob.startswith(b"%PDF")


def test_el_pdf_sigue_siendo_determinista_con_etiquetas() -> None:
    m = model(compliance=ComplianceDocument(items=(_MARCO, _PROTOCOLO)))
    assert render(m) == render(m)
