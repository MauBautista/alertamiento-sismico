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
from pathlib import Path

import pytest
from pypdf import PdfReader

from takab_api.documentos import membrete
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
#
# [T-7.21 · PENDIENTES §4.8] Los cuatro datos LLEGARON el 2026-09-19, así que
# estos casos cambiaron de lado: antes fijaban que la ausencia se declaraba,
# ahora fijan que lo impreso es lo declarado. Lo que NO se retira es la
# maquinaria de declarar: se prueba contra una `Identidad()` construida vacía
# aquí mismo, porque el día que se añada un quinto campo —o se revoque uno de
# los cuatro— tiene que seguir funcionando, y la constante ya no la ejerce.


def test_los_cuatro_datos_ESTAN_y_el_bloque_sigue_teniendo_cuatro_renglones() -> None:
    """Y se declaran los CUATRO: un bloque que encoge esconde que falta algo."""
    assert TAKAB.completa
    rotulos = [r for r, _ in TAKAB.lineas()]
    assert rotulos == ["RAZÓN SOCIAL", "DOMICILIO", "CLASIFICACIÓN", "FIRMA POR TAKAB"]
    assert PENDIENTE not in dict(TAKAB.lineas()).values()
    assert TAKAB.aviso() is None


def test_la_maquinaria_de_declarar_la_ausencia_SIGUE_viva() -> None:
    """La constante ya no la ejerce; el mecanismo tiene que seguir en pie."""
    aviso = Identidad().aviso()
    assert aviso is not None
    assert "razón social" in aviso and "domicilio" in aviso
    assert "§4.8" in PENDIENTE


def test_una_cadena_VACIA_no_cuenta_como_dato() -> None:
    """`completa` y `lineas()` tenían criterios distintos, y se contradecían.

    Con `is not None`, un `firmante=""` daba `completa is True` **y** un papel
    que imprimía `PENDIENTE` en ese renglón. Es justo la contradicción que este
    módulo existe para impedir, y estaba esperando a la primera cadena vacía —
    que es la tentación obvia para expresar «no hay firmante nominal».
    """
    casi = Identidad(
        razon_social="Ejemplo de prueba",
        domicilio="Calle de prueba 1",
        clasificacion="confidencial",
        firmante="",
    )
    assert not casi.completa
    assert casi.aviso() is not None
    assert dict(casi.lineas())["FIRMA POR TAKAB"] == PENDIENTE


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


def test_la_hoja_en_blanco_IMPRIME_la_razon_social_declarada() -> None:
    """Y la declarada es la de `identidad.py`, no una parecida.

    El cruce va contra la constante y no contra un literal repetido aquí: una
    copia del nombre legal en un test es otro sitio donde diverge.
    """
    texto = _texto(hoja_en_blanco())
    assert "RAZÓN SOCIAL" in texto
    assert TAKAB.razon_social is not None
    assert TAKAB.razon_social in " ".join(texto.split())
    assert "PENDIENTE" not in texto
    # La guarda antifalsificación se queda: el papel no puede inventarse una
    # forma societaria que el acta no dice.
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
def test_el_pie_CABE_en_su_celda(degradado: bool, monkeypatch) -> None:
    """`cell()` no envuelve: lo que no cabe se dibuja encima de lo de al lado.

    Se miden **las mismas cadenas que el pie imprime** —no una copia escrita en
    el test— y con el PEOR caso real: el folio más largo que produce el
    generador, con la huella entera y con instante sellado. El que revienta
    nunca es el caso corto, y una copia en el test se separa del código a la
    primera.

    ⚠️ **[T-7.42] El caso `degradado` era un NO-OP.** Ponía `pdf.degraded = True`
    DESPUÉS de construir, y para entonces `_install_fonts` ya había elegido las
    DejaVu: se medían las anchuras de la tipografía BUENA transcodificando el
    texto a latin-1, que es justo lo que no ocurre cuando las fuentes faltan.
    Ahora se le esconde el directorio —la avería real: la imagen sin los
    `.ttf`— y las anchuras salen de Helvetica y Courier, que es lo que fpdf2
    usaría. Importa desde esta ficha y no antes: hasta hoy `_linea_huella()`
    devolvía en todo documento real la frase corta de ausencia, y desde hoy son
    85 caracteres de monoespaciada en el pie de TODAS las páginas.
    """
    if degradado:
        monkeypatch.setattr(membrete, "_FONTS", Path("/tipografia/que/no/viajo/en/la/imagen"))
    pdf = MembretePDF("TKB-FOLIO-MUY-LARGO-DE-PRUEBA-01", "sub", sellado=SELLO, huella="f" * 64)
    assert pdf.degraded is degradado, (
        "el caso no está ejerciendo el camino que dice: si esto falla, la prueba "
        "vuelve a medir la tipografía que no se va a usar"
    )
    pdf.add_page()

    def ancho(texto: str, fuente: str, tam: float) -> float:
        pdf.set_font(fuente, "", tam)
        return pdf.get_string_width(pdf.text_of(texto))

    banda = CONTENT_W
    assert ancho(pdf._linea_identidad(), pdf.body_font, 7) <= banda - _ANCHO_PAGINA
    assert ancho("Pág. 9 de 99", pdf.body_font, 7) <= _ANCHO_PAGINA
    assert ancho(pdf._linea_huella(), pdf.mono_font, 6.5) <= banda - _ANCHO_SELLO
    assert ancho(pdf._sello(), pdf.body_font, 7) <= _ANCHO_SELLO
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


# ──────────────────── 6 · [T-7.21] el emisor legal, y lo que puede desbordar
#
# Dos superficies nuevas, y las dos son de la misma familia que el resto del
# fichero: sitios donde algo se dibuja FUERA y nada se pone en rojo.


def test_el_EMISOR_del_pie_cabe_en_su_banda() -> None:
    """`cell()` no envuelve, y el pie ganó dos renglones con datos LARGOS.

    La razón social son 84 caracteres y el domicilio 79. Medido a 7 pt sobre la
    banda útil suman 236.7 mm contra 185.9 disponibles — por eso van en dos
    renglones y a 6 pt. Si mañana crece el domicilio, o alguien sube el cuerpo
    de letra, esto se pone rojo antes de que el papel salga pisado.
    """
    pdf = MembretePDF("TKB-MEM-001", "prueba", sellado=SELLO, huella=None)
    pdf.add_page()
    pdf.set_font(pdf.body_font, "", 6)
    for texto in pdf._lineas_emisor():
        ancho = pdf.get_string_width(pdf.text_of(texto))
        assert ancho <= CONTENT_W, (
            f"el renglón del emisor mide {ancho:.1f} mm y la banda son {CONTENT_W}: "
            f"se dibujaría encima de lo de al lado · {texto!r}"
        )


def test_los_dos_renglones_del_emisor_NO_caben_emparejados() -> None:
    """La razón por la que son dos, medida y no supuesta.

    Si un día caben juntos, esta prueba se pone roja y quien la lea decide con
    el número delante — que es lo contrario de heredar una decisión sin su
    aritmética, que es como se arruinó la migración de formato de esta ficha.
    """
    pdf = MembretePDF("TKB-MEM-001", "prueba", sellado=SELLO, huella=None)
    pdf.add_page()
    pdf.set_font(pdf.body_font, "", 7)
    juntos = pdf.get_string_width(pdf.text_of(" · ".join(pdf._lineas_emisor())))
    assert juntos > CONTENT_W


def test_la_hoja_en_blanco_NO_repite_el_emisor_en_el_pie() -> None:
    """Es el único papel cuyo cuerpo ya lo dice entero — y con los CUATRO datos."""
    from takab_api.documentos.hoja import _Hoja

    assert _Hoja.emisor_en_pie is False
    assert MembretePDF.emisor_en_pie is True
    texto = " ".join(_texto(hoja_en_blanco()).split())
    assert TAKAB.razon_social is not None
    assert texto.count(TAKAB.razon_social) == 1


def test_la_RESERVA_del_pie_se_deriva_de_sus_renglones() -> None:
    """Era un `20.0` tecleado al lado de un `set_y(-19)`: dos números a mano.

    El pie acaba de ganar dos renglones. Con la reserva tecleada, subirla se
    quedaba en «acordarse», y olvidarlo no rompe nada visible: el texto salta de
    página, pero el pie se dibuja encima del cuerpo de la última.
    """
    esperado = (
        membrete._PIE_TRAS_FILETE
        + sum(membrete._PIE_RENGLONES)
        + membrete._PIE_DEGRADADA
        + membrete._PIE_AIRE
    )
    assert membrete.PIE_MM == pytest.approx(esperado)
    assert len(membrete._PIE_RENGLONES) == 4, "el pie tiene cuatro renglones fijos"


def test_NINGUN_texto_del_SVG_se_sale_de_la_hoja() -> None:
    """La pieza que NO tenía guarda, y que estaba rota.

    ⚠️ Medido el 2026-09-19 sobre el `carta.svg` COMITEADO: el `<text>` del
    aviso —203 caracteres en sans a 2.6 desde x=15— terminaba en x=292.8, es
    decir **91.9 mm fuera del filete y 76.9 fuera de una hoja de 215.9**. Nadie
    lo vio nunca porque `test_el_svg_y_el_pdf_miden_LO_MISMO` compara el
    `viewBox` con el `/MediaBox`: mide la HOJA, no lo dibujado.

    Se comprueban las DOS identidades a propósito. La vacía es la que estaba
    rota, y es la que vuelve el día que se añada un campo nuevo.
    """
    import re

    from takab_api.documentos import hoja as _hoja

    tope = membrete.PAGE_W - membrete.MARGIN
    patron = re.compile(r'<text x="([\d.]+)" y="[\d.]+" class="(\w+)">(.*?)</text>')
    fuentes = {
        "valor": (_hoja._MONO, _hoja._FS_VALOR, _hoja._AVANCE_MONO),
        "rotulo": (_hoja._SANS, _hoja._FS_VALOR, _hoja._AVANCE_SANS),
        "aviso": (_hoja._SANS, _hoja._FS_AVISO, _hoja._AVANCE_SANS),
        "subtitulo": (_hoja._SANS, 2.6, _hoja._AVANCE_SANS),
        "pie": (_hoja._SANS, 2.5, _hoja._AVANCE_SANS),
    }
    for nombre, identidad in (("real", TAKAB), ("vacía", Identidad())):
        svg = hoja_svg(identidad)
        for x, clase, texto in patron.findall(svg):
            crudo = texto.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
            fichero, tamano, respaldo = fuentes[clase]
            fin = float(x) + _hoja._ancho(crudo, fichero, tamano, respaldo)
            assert fin <= tope, (
                f"identidad {nombre}: el <text class={clase!r}> termina en {fin:.2f} mm "
                f"y el filete está en {tope} · {crudo[:60]!r}"
            )


def test_el_AVANCE_declarado_es_el_de_la_tipografia_REAL() -> None:
    """Un número de tipografía tecleado envejece en silencio.

    `_AVANCE_MONO` sólo se usa cuando la fuente no viajó, así que un valor mal
    no rompe nada hasta el día degradado — el peor día para descubrirlo.
    """
    from fontTools.ttLib import TTFont

    from takab_api.documentos import hoja as _hoja

    for fichero, declarado in ((_hoja._MONO, _hoja._AVANCE_MONO), (_hoja._SANS, None)):
        fuente = TTFont(membrete._FONTS / fichero)
        upm = fuente["head"].unitsPerEm
        hmtx = fuente["hmtx"]
        anchos = {hmtx[n][0] for n in set(fuente.getBestCmap().values()) if n in hmtx.metrics}
        if declarado is not None:
            assert len(anchos) == 1, "la monoespaciada dejó de serlo"
            assert anchos.pop() / upm == pytest.approx(declarado, abs=1e-6)


def test_el_SVG_envuelve_lo_que_no_cabe_en_un_renglon() -> None:
    """Y que envuelva de verdad: la razón social son 84 caracteres y caben 79."""
    from takab_api.documentos import hoja as _hoja

    caben = int(_hoja._ANCHO_VALOR // (_hoja._FS_VALOR * _hoja._AVANCE_MONO))
    assert TAKAB.razon_social is not None
    assert len(TAKAB.razon_social) > caben, "el caso interesante dejó de serlo"
    renglones = _hoja._envuelve(
        TAKAB.razon_social, _hoja._MONO, _hoja._FS_VALOR, _hoja._ANCHO_VALOR, _hoja._AVANCE_MONO
    )
    assert len(renglones) == 2
    assert " ".join(renglones) == TAKAB.razon_social, "envolver no puede perder ni añadir texto"


def test_el_SVG_parte_una_PALABRA_que_no_cabe_entera() -> None:
    """Una URL o un hash no tienen espacios, y el contrato es que nada se sale."""
    from takab_api.documentos import hoja as _hoja

    palabra = "x" * 400
    renglones = _hoja._envuelve(
        palabra, _hoja._MONO, _hoja._FS_VALOR, _hoja._ANCHO_VALOR, _hoja._AVANCE_MONO
    )
    assert len(renglones) > 1
    assert "".join(renglones) == palabra
    for renglon in renglones:
        ancho = _hoja._ancho(renglon, _hoja._MONO, _hoja._FS_VALOR, _hoja._AVANCE_MONO)
        assert ancho <= _hoja._ANCHO_VALOR


# ───────────────── [T-8.12 · A-245] el filete del recuadro cubre TODO su texto


def _recuadro(y0: float, renglones: int):  # noqa: ANN202
    """Un `callout` de `renglones` renglones que entra en `y0`, con su filete y su texto."""
    from fpdf import FPDF

    from tests.documentos.cajas_de_texto import cajas_impresas

    filetes: list[tuple[int, float, float]] = []
    original = FPDF.line

    def espia(self, x1, y1, x2, y2):  # noqa: ANN001, ANN202
        if x1 == x2 == membrete.MARGIN:
            filetes.append((self.page, min(y1, y2), max(y1, y2)))
        return original(self, x1, y1, x2, y2)

    FPDF.line = espia  # type: ignore[method-assign]
    try:
        with cajas_impresas() as cap:
            pdf = membrete.MembretePDF("TKB-RECUADRO", "recuadro")
            pdf.add_page()
            pdf.set_y(y0)
            pdf.callout(" ".join(f"renglón{i:03d}" for i in range(renglones * 12)))
            pdf.output()
    finally:
        FPDF.line = original  # type: ignore[method-assign]
    textos = [c for c in cap.textos if "renglón" in c.texto]
    return filetes, textos


def test_el_filete_del_recuadro_cubre_TODO_su_texto() -> None:
    """Medía 8 mm fijos: con tres renglones o más la barra se quedaba a media altura."""
    filetes, textos = _recuadro(100.0, 5)
    assert len(textos) >= 4, "el recuadro de prueba no salió de varios renglones"
    [(pagina, arriba, abajo)] = filetes
    assert all(c.pagina == pagina for c in textos)
    assert arriba <= min(c.y0 for c in textos) + 0.5
    assert abajo >= max(c.y1 for c in textos) - 0.5, (
        f"el filete acaba en {abajo:.1f} mm y el texto baja hasta "
        f"{max(c.y1 for c in textos):.1f} mm"
    )


def test_un_recuadro_que_NO_cabe_salta_ENTERO_de_pagina() -> None:
    """Partido, la barra se quedaba en una página y el texto seguía en la otra."""
    tope = membrete.PAGE_H - membrete.PIE_MM
    filetes, textos = _recuadro(tope - 10.0, 5)
    paginas = {c.pagina for c in textos}
    assert len(paginas) == 1, f"el texto del recuadro quedó partido en las páginas {paginas}"
    [(pagina, _arriba, abajo)] = filetes
    assert pagina in paginas, "el filete quedó en otra página que su texto"
    assert abajo <= tope + 0.05


# ───────────── [T-8.12 · 2ª vuelta] el subtítulo de la cabecera cabe en la hoja


def _renglones_de_cabecera(subtitulo: str):  # noqa: ANN202
    from tests.documentos.cajas_de_texto import cajas_impresas

    with cajas_impresas() as cap:
        pdf = membrete.MembretePDF("TKB-CABECERA", subtitulo)
        pdf.add_page()
        pdf.para("cuerpo")
        pdf.add_page()
        pdf.output()
    # La cabecera es lo que queda por ENCIMA del filete, en cada página.
    return [c for c in cap.textos if c.y1 <= membrete.CUERPO_Y - 4]


@pytest.mark.parametrize("largo", [110, 400])
def test_un_SUBTITULO_largo_no_se_sale_del_canto_de_la_hoja(largo: int) -> None:
    """`cell(0, …)` no envuelve ni recorta. Medido por el verificador: con un
    inmueble de 110 caracteres el subtítulo acababa en x = 219.8 mm, sobre una hoja
    de 215.9, en TODAS las páginas del técnico. Primero baja el cuerpo lo justo;
    si ni así cabe, se recorta con «…» —el nombre entero está en la portada—."""
    nombre = ("Torre Corporativa Reforma 222 · Edificio B Norte · " * 10)[:largo]
    subtitulo = f"DICTAMEN OPERATIVO PRELIMINAR · {nombre} (CDMX-REF-222)"
    renglones = _renglones_de_cabecera(subtitulo)
    assert len(renglones) >= 2, "la cabecera no se imprimió en las dos páginas"
    borde = membrete.PAGE_W - membrete.MARGIN
    for c in renglones:
        assert c.x1 <= borde + 0.05, f"la cabecera acaba en x = {c.x1:.1f} mm (borde {borde})"
        assert c.texto.startswith("DICTAMEN OPERATIVO PRELIMINAR · Torre"), c.texto
    if largo == 400:
        assert all(c.texto.endswith("…") for c in renglones), "recortó sin decirlo"


def test_un_SUBTITULO_que_ya_cabia_sale_IDENTICO() -> None:
    corto = "DICTAMEN OPERATIVO PRELIMINAR · Planta Cholula (CHL-A)"
    [primero, *_] = _renglones_de_cabecera(corto)
    assert primero.texto == corto
