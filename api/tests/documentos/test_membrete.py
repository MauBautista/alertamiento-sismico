"""[T-7.21] El membrete: lo que todo papel del sistema tiene que decir de sí mismo.

Se comprueba con `pypdf` y no con `pdftotext`: aquél es un paquete de Python y
éste es poppler, que sería **la primera dependencia de un binario del sistema**
de esta suite — CI hace `pip install -e ".[dev]"` y nada más. El Goal de F4 ya
pedía `pypdf` para contar imágenes, así que no estrena nada.

Lo que fija, por orden de lo que costaría equivocarse:

1. **La identidad legal no se inventa.** Los cuatro datos de `PENDIENTES §4.8` no
   están; el papel lo DICE en vez de rellenarlos con algo verosímil. Un
   «TAKAB S.A. de C.V.» inventado en un documento firmado es la mentira más cara
   que puede contar este producto, y además invisible: nadie revisa un pie.
2. **La fecha del pie es la SELLADA**, no la de generación. `generated_at` del
   dictamen es `datetime.now()`, así que imprimirla haría que dos generaciones
   del mismo modelo dieran archivos distintos y «verifique el sha256» sería falso.
3. **El hash va entero o se declara su ausencia.** Truncarlo es el defecto que
   `T-5.26` ya arregló una vez: un sha a medias no verifica nada.
4. **El pie cabe.** `cell()` de fpdf2 NO envuelve: el texto de más se dibuja
   encima de la paginación sin poner nada en rojo.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime

import pytest
from pypdf import PdfReader

from takab_api.documentos.hoja import hoja_en_blanco, hoja_svg
from takab_api.documentos.identidad import PENDIENTE, TAKAB, Identidad
from takab_api.documentos.membrete import (
    _ANCHO_PAGINA,
    _ANCHO_SELLO,
    AVISO_DEGRADADA,
    CONTENT_W,
    MembretePDF,
)

SELLO = datetime(2026, 3, 14, 15, 9, 26, tzinfo=UTC)


def _texto(pdf: bytes) -> str:
    return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf)).pages)


def _documento(**kw) -> bytes:
    pdf = MembretePDF(kw.pop("folio", "TKB-MEM-001"), kw.pop("subtitle", "prueba"), **kw)
    pdf.seal(SELLO)
    pdf.add_page()
    pdf.para("cuerpo")
    return bytes(pdf.output())


# ───────────────────────────────────────────── 1 · la identidad no se inventa


def test_los_cuatro_datos_que_FALTAN_se_declaran() -> None:
    """Y se declaran los CUATRO: un bloque que encoge esconde que falta algo."""
    assert not TAKAB.completa
    rotulos = [r for r, _ in TAKAB.lineas()]
    assert rotulos == ["RAZÓN SOCIAL", "DOMICILIO", "CLASIFICACIÓN", "FIRMA POR TAKAB"]
    assert all(v == PENDIENTE for _, v in TAKAB.lineas())


def test_el_aviso_dice_QUE_falta_y_DONDE_esta_fichado() -> None:
    aviso = TAKAB.aviso()
    assert aviso is not None
    assert "razón social" in aviso and "domicilio" in aviso
    assert "§4.8" in PENDIENTE


def test_con_los_cuatro_datos_el_aviso_DESAPARECE() -> None:
    """Rellenarlos tiene que ser UNA edición, y esto lo demuestra."""
    completa = Identidad(
        razon_social="Ejemplo de prueba",
        domicilio="Calle de prueba 1",
        clasificacion="confidencial",
        firmante="Quien firme",
    )
    assert completa.completa
    assert completa.aviso() is None
    assert PENDIENTE not in dict(completa.lineas()).values()


def test_la_hoja_en_blanco_NO_inventa_una_razon_social() -> None:
    texto = _texto(hoja_en_blanco())
    assert "RAZÓN SOCIAL" in texto
    assert "PENDIENTE" in texto
    assert "S.A. de C.V." not in texto, "el papel se inventó una razón social"


# ────────────────────────────────────────────────── 2 · la fecha y el sellado


def test_el_pie_lleva_el_instante_SELLADO_y_no_la_hora_de_generacion() -> None:
    texto = _texto(_documento(sellado=SELLO))
    assert "2026-03-14 15:09 UTC" in texto
    # Y lo rotula como EVENTO: no es la hora en que se imprimió el papel, y el
    # documento no puede insinuar que lo sea.
    assert "EVENTO 2026-03-14" in texto


def test_sin_instante_sellado_el_pie_NO_se_inventa_uno() -> None:
    texto = _texto(_documento(sellado=None))
    assert "EVENTO" not in texto


def test_el_mismo_documento_produce_los_mismos_bytes() -> None:
    """La promesa que sostiene «verifique el sha256»."""
    assert _documento(sellado=SELLO) == _documento(sellado=SELLO)


# ─────────────────────────────────────────────────────────── 3 · la huella


def test_la_huella_va_ENTERA_en_el_pie() -> None:
    huella = "a" * 64
    texto = _texto(_documento(huella=huella))
    assert huella in texto, "el sha256 salió truncado: es el defecto de T-5.26"


def test_sin_huella_se_DECLARA_en_vez_de_dejar_el_hueco() -> None:
    texto = _texto(_documento(huella=None))
    assert "SIN HUELLA DE CONTENIDO" in texto


# ─────────────────────────────────────────────── 4 · el pie cabe, y se lee


@pytest.mark.parametrize("degradado", [False, True])
def test_el_pie_CABE_en_su_celda(degradado: bool) -> None:
    """`cell()` no envuelve: lo que no cabe se dibuja encima de lo de al lado.

    Se miden **las mismas cadenas que el pie imprime** —no una copia escrita en
    el test— y con el PEOR caso real: el folio más largo que produce el
    generador, con `build` y con instante sellado. El que revienta nunca es el
    caso corto, y una copia en el test se separa del código a la primera.
    """
    pdf = MembretePDF("TKB-FOLIO-MUY-LARGO-DE-PRUEBA-01", "sub", sellado=SELLO, build="abc1234")
    pdf.degraded = degradado
    pdf.add_page()

    def ancho(texto: str, fuente: str, tam: float) -> float:
        pdf.set_font(fuente, "", tam)
        return pdf.get_string_width(pdf.text_of(texto))

    banda = CONTENT_W
    assert ancho(pdf._linea_identidad(), pdf.body_font, 7) <= banda - _ANCHO_PAGINA
    assert ancho("Pág. 9 de 99", pdf.body_font, 7) <= _ANCHO_PAGINA
    assert ancho("SHA-256 DEL CONTENIDO " + "f" * 64, pdf.mono_font, 6.5) <= banda - _ANCHO_SELLO
    assert ancho(pdf._sello_y_build(), pdf.body_font, 7) <= _ANCHO_SELLO
    if degradado:
        assert ancho(AVISO_DEGRADADA, pdf.body_font, 7) <= banda


def test_el_hash_cabe_en_su_linea() -> None:
    pdf = MembretePDF("TKB-X", "sub", huella="f" * 64)
    pdf.add_page()
    pdf.set_font(pdf.mono_font, "", 6.5)
    ancho = pdf.get_string_width(pdf._linea_huella())
    assert ancho <= CONTENT_W - _ANCHO_SELLO, (
        f"la línea del hash mide {ancho:.1f} mm y su celda {CONTENT_W - _ANCHO_SELLO:.1f} mm"
    )


def test_el_tipo_de_documento_sale_en_el_pie() -> None:
    from takab_api.dictamen.layout import TakabPDF

    assert TakabPDF.tipo == "DICTAMEN"
    pdf = TakabPDF("TKB-T", "sub")
    pdf.add_page()
    assert "DICTAMEN" in _texto(bytes(pdf.output()))


# ────────────────────────────────────────────────────────── la hoja en blanco


def test_la_hoja_es_DETERMINISTA_en_sus_dos_formatos() -> None:
    """Se comitean las dos: si no son deterministas, `git diff` parpadea siempre."""
    assert hoja_en_blanco() == hoja_en_blanco()
    assert hoja_svg() == hoja_svg()


def test_el_svg_es_TEXTO_y_no_lleva_rasters_incrustados() -> None:
    """Un base64 dentro lo haría ilegible en un diff y pesado sin motivo."""
    svg = hoja_svg()
    assert svg.startswith("<?xml")
    assert "base64" not in svg
    assert "215.9mm" in svg and "279.4mm" in svg


def test_el_svg_y_el_pdf_miden_LO_MISMO() -> None:
    """Dos dibujos del mismo papel que no coincidan son dos papeles."""
    from takab_api.documentos.membrete import PAGE_H, PAGE_W

    svg = hoja_svg()
    assert f'viewBox="0 0 {PAGE_W} {PAGE_H}"' in svg
    caja = PdfReader(io.BytesIO(hoja_en_blanco())).pages[0].mediabox
    assert abs(float(caja.width) / 72 * 25.4 - PAGE_W) < 0.05
    assert abs(float(caja.height) / 72 * 25.4 - PAGE_H) < 0.05
