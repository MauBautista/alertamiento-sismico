"""[T-7.21] LA GUARDA QUE NO EXISTÍA: la geometría del papel.

⚠️ **Antes de esta suite, la suite entera era CIEGA al tamaño de página.** Está
medido: `pytest api/tests/dictamen` daba **243 passed con A4 y 243 passed con
Carta**, y también 243 con la migración hecha A MEDIAS — la peor de las tres,
porque deja las tablas y el texto sobresaliendo del filete que los enmarca, en
todas las páginas. Un dictamen así se entrega a Protección Civil con todo verde.

Por eso esta suite se escribe **antes** de tocar el formato: si se migra primero,
nada avisa de lo que se rompa.

Lo que fija, por orden de lo que costaría equivocarse:

1. **El tamaño se declara en el PDF**, no en un comentario: `/MediaBox` en
   puntos. Es lo que convierte «tamaño Carta» de criterio en prosa a criterio
   medible con una línea.
2. **Nada se sale del filete.** El chasis dibuja la raya de cabecera y de pie a
   `PAGE_W - MARGIN`, pero todo `cell(0, …)` se ancla al margen derecho de
   fpdf2. Si las dos fuentes divergen —y divergen: `PAGE_W = 210.0` no es el A4
   de fpdf2, que es 210.0015…— el texto pasa por encima de la raya.
3. **Ninguna caja pisa el pie.** `rect`/`polyline` NO disparan el salto de
   página automático, así que las figuras del dictamen se dibujarían sobre el
   filete sin que nada fallara.
4. **El membrete sobrevive a la extracción de texto.** Un lector de pantalla y
   un `pypdf` de la contraparte no leen un PNG: el nombre, el folio y la
   paginación tienen que ser TEXTO en todas las páginas.
"""

from __future__ import annotations

import io
import re

import pytest
from pypdf import PdfReader

from takab_api.dictamen import layout
from takab_api.dictamen.pdf import render
from tests.dictamen.test_pdf import model

#: Carta en puntos, que es la unidad del `/MediaBox`. 215.9 mm × 279.4 mm.
CARTA_PTS = (612.0, 792.0)
#: Cuánto puede separarse la medición del valor nominal. fpdf2 redondea a 2
#: decimales al escribir el `/MediaBox`; esto no es holgura de diseño.
TOLERANCIA_PTS = 0.75


@pytest.fixture(scope="module")
def pdf() -> bytes:
    return render(model())


@pytest.fixture(scope="module")
def lector(pdf: bytes) -> PdfReader:
    return PdfReader(io.BytesIO(pdf))


def test_el_papel_es_CARTA_y_lo_declara_el_documento(lector: PdfReader) -> None:
    """El criterio de la ficha dice «tamaño Carta». Esto lo hace medible."""
    for i, pagina in enumerate(lector.pages, start=1):
        ancho = float(pagina.mediabox.width)
        alto = float(pagina.mediabox.height)
        assert abs(ancho - CARTA_PTS[0]) < TOLERANCIA_PTS, f"pág. {i}: ancho {ancho} pts"
        assert abs(alto - CARTA_PTS[1]) < TOLERANCIA_PTS, f"pág. {i}: alto {alto} pts"


def test_el_chasis_y_fpdf2_MIDEN_LO_MISMO() -> None:
    """La desincronización que arruina la migración hecha a medias.

    `PAGE_W`/`CONTENT_W` son constantes de módulo y fpdf2 tiene las suyas
    (`w`/`epw`). Las tablas del dictamen usan las de fpdf2 y los filetes usan las
    del módulo: si difieren, la tabla sobresale de su propio marco. Y difieren
    hoy en A4 por 0.0015 mm — invisible, pero el mecanismo es el mismo.
    """
    pdf = layout.TakabPDF("TKB-GEOM", "prueba de geometría")
    assert abs(pdf.w - layout.PAGE_W) < 0.01, f"fpdf2 dice {pdf.w}, el módulo {layout.PAGE_W}"
    assert abs(pdf.epw - layout.CONTENT_W) < 0.01, (
        f"ancho útil: fpdf2 {pdf.epw}, el módulo {layout.CONTENT_W}"
    )


def bordes_dibujados(pagina) -> list[float]:
    """El borde DERECHO de todo lo que se dibuja, en mm.

    ⚠️ Se miden los operadores de dibujo (`re` para rectángulos, `l`/`m` para
    líneas), no el texto. La primera versión de esta guarda usaba la matriz de
    texto de `pypdf` y **no cazaba nada**: `tm[4]` es donde EMPIEZA el fragmento,
    y una celda alineada a la derecha empieza a la izquierda del filete y se
    extiende más allá. Medido: con la media migración el texto arrancaba en
    184.0 mm, muy por debajo del tope, mientras las tablas desbordaban de verdad.

    Los rectángulos sí dan el borde exacto —`x y w h re`— y son justo lo que
    dibujan las tablas del dictamen, que es donde el desborde se ve.
    """
    datos = pagina.get_contents().get_data()
    bordes: list[float] = []
    for m in re.finditer(rb"([\d.\-]+)\s+([\d.\-]+)\s+([\d.\-]+)\s+([\d.\-]+)\s+re\b", datos):
        x, _y, w, _h = (float(v) for v in m.groups())
        bordes.append((x + w) / 72.0 * 25.4)
    for m in re.finditer(rb"([\d.\-]+)\s+([\d.\-]+)\s+(?:l|m)\b", datos):
        bordes.append(float(m.group(1)) / 72.0 * 25.4)
    return bordes


def test_NADA_se_sale_del_filete(lector: PdfReader) -> None:
    """El filete de cabecera y pie llega a `PAGE_W - MARGIN`. Nada puede pasarlo.

    Es la comprobación que caza la MEDIA migración: cambiar `format` sin mover
    las constantes deja las tablas dibujándose 5.9 mm fuera de su propio marco,
    en todas las páginas, con la suite en verde.
    """
    tope_mm = layout.PAGE_W - layout.MARGIN
    for i, pagina in enumerate(lector.pages, start=1):
        bordes = bordes_dibujados(pagina)
        if not bordes:
            continue
        peor = max(bordes)
        assert peor <= tope_mm + 0.05, (
            f"pág. {i}: se dibuja hasta {peor:.1f} mm y el filete está en {tope_mm:.1f} mm"
        )


def test_el_membrete_es_TEXTO_en_todas_las_paginas(lector: PdfReader) -> None:
    """Un `pypdf` de la contraparte no lee un PNG.

    El nombre pasó a la cabecera como arte en `T-6.33`; por eso el pie lo repite
    como texto. Esta prueba es la que impide que alguien «limpie» esa
    duplicación aparente y deje el documento sin firma legible.
    """
    for i, pagina in enumerate(lector.pages, start=1):
        texto = pagina.extract_text() or ""
        assert "TAKAB AILERT" in texto, f"pág. {i} sin el nombre como texto"
        assert "EVIDENCIA INMUTABLE" in texto, f"pág. {i} sin la franja"
        assert f"Pág. {i} de {len(lector.pages)}" in texto, f"pág. {i} sin su paginación"


def test_el_folio_se_extrae(lector: PdfReader) -> None:
    """Sin folio extraíble no se puede casar el papel con el registro."""
    texto = lector.pages[0].extract_text() or ""
    assert model().folio in texto
