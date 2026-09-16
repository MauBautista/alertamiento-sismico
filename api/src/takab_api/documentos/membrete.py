"""[T-7.21] MembretePDF: el membrete que lleva todo papel que sale del sistema.

Promoción de lo que era `dictamen/layout.py::TakabPDF`. Lo hereda el dictamen
pericial, el reporte de simulacro y el informe del evento (`T-7.22`).

Todo el dibujo sale de fpdf2 —``line``, ``rect``, ``polyline``, ``circle``,
``table``— sin rasterizar más que el logotipo. Un vector pesa menos, no pixela al
imprimir y, sobre todo, es DETERMINISTA byte a byte: el sha256 del documento es
lo que lo hace evidencia.

**Determinismo**: fpdf2 estampa ``/CreationDate`` con el reloj. Sin fijarlo, dos
generaciones del mismo modelo darían hashes distintos y la promesa de «verifique
el sha256» sería falsa. ``seal`` lo fija a un instante del propio suceso.

## Tres decisiones de esta ficha, con su razón

**1 · La geometría se DERIVA de fpdf2, no se teclea.** `PAGE_W`/`CONTENT_W` eran
constantes de módulo paralelas a las de fpdf2 (`w`/`epw`), y las dos fuentes
podían divergir sin que nada las cruzara — de hecho ya divergían: el A4 de fpdf2
mide 210.0016 mm y la constante decía 210.0. A escala invisible, pero el
mecanismo es el que arruina una migración de formato hecha a medias: las tablas
usan `epw` y los filetes usaban la constante, así que cambiar sólo el formato
dibujaba las tablas 5.9 mm FUERA de su propio marco, en todas las páginas y con
la suite en verde. Ahora las dos salen de `PAGE_FORMATS`, que es de dónde las
saca fpdf2, y `tests/documentos/test_geometria.py` las cruza.

**2 · El pie se reparte POR ARITMÉTICA, no por gusto.** La ficha pide identidad,
tipo, folio, fecha, `build`, paginación y sha256. Medido sobre la banda útil de
Carta (185.9 mm) con el peor folio real: identidad 114.5 mm, paginación 15.5,
sha256 118.7 (mono 6.5), evento+build 59.6, aviso de tipografía degradada 63.8.
Las dos primeras caben emparejadas y las dos siguientes también; el aviso de
degradada no cabe con ninguna, así que ocupa su propio renglón **y sólo cuando
hace falta**. ⚠️ `cell()` de fpdf2 **no envuelve**: lo que sobra se dibuja encima
de lo de al lado sin poner nada en rojo. Truncar el hash no es opción — `T-5.26`
existe justo porque los sha salían a 32 de 64 caracteres.

**3 · La fecha del pie es la SELLADA, nunca la de generación.** `generated_at`
del dictamen es `datetime.now(tz=UTC)` (`routers/reports.py`), así que imprimirla
haría que dos generaciones del mismo modelo dieran archivos distintos. El pie
lleva el instante del SUCESO —el mismo que recibe `seal()`— y por eso su rótulo
dice «EVENTO», no «generado el»: no es lo mismo y el papel no puede insinuarlo.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos
from fpdf.fpdf import PAGE_FORMATS

_ARTE = Path(__file__).parent

#: [T-6.33] El logotipo de la cabecera, en su variante POSITIVA. Es el único
#: destino de la marca en positivo del repo, y no es un capricho: éste es el
#: único PAPEL BLANCO que el producto entrega, y va firmado. Sobre blanco, la
#: variante negativa —la de la consola, el panel y la app— se perdería.
#: Lo deriva `shared/brand/generar.py`; aquí no se edita.
LOGOTIPO = _ARTE / "marca" / "logotipo.png"
_FONTS = _ARTE / "fonts"

#: Ancho impreso de la marca, en mm.
_LOGO_MM = 34.0

#: [T-7.21] CARTA, y derivada de la tabla de fpdf2 en vez de tecleada. Es el
#: tamaño de papel de oficina en México, que es donde se imprime este documento.
_PT_A_MM = 25.4 / 72.0
_FORMATO = "letter"
PAGE_W = round(PAGE_FORMATS[_FORMATO][0] * _PT_A_MM, 4)
PAGE_H = round(PAGE_FORMATS[_FORMATO][1] * _PT_A_MM, 4)

MARGIN = 15.0
CONTENT_W = round(PAGE_W - 2 * MARGIN, 4)

#: Alto que el pie reserva. `set_auto_page_break(margin=…)` marca el corte por
#: debajo del cual fpdf2 salta de página SOLO para texto: `rect` y `polyline` no
#: lo disparan, y de ahí `reserva()`.
PIE_MM = 20.0
#: La y donde el cuerpo empieza en cada página, bajo el filete de cabecera.
CUERPO_Y = 32.0
#: La y del filete de la cabecera.
_FILETE_Y = 26.0

#: Anchos de las dos columnas derechas del pie, en mm. Medidos sobre el peor
#: caso real («Pág. 9 de 99» y «EVENTO … UTC · build abc1234»), no elegidos.
_ANCHO_PAGINA = 18.0
_ANCHO_SELLO = 62.0

#: Lo que el pie dice cuando la tipografía Unicode no viajó. Ocupa su propio
#: renglón: medido, no cabe emparejado con ninguna de las otras dos líneas.
AVISO_DEGRADADA = "TIPOGRAFÍA DEGRADADA (fuente Unicode ausente)"

#: Paleta del documento. Sobria a propósito: un dictamen no es un tablero.
#: ⚠️ `INK`/`MUTED`/`RULE` son tintas de PAPEL y no salen de `shared/brand`:
#: aquélla es la paleta de PANTALLA (`NAVY` #0B1D3A sobre fondo oscuro) y este
#: es el único soporte blanco que entrega el producto. Un navy de marca sobre
#: blanco da un gris azulado que no es el negro de un documento impreso. Se
#: declara aquí en vez de heredarse mal.
INK = (20, 24, 30)
MUTED = (110, 120, 132)
RULE = (200, 206, 214)


class MembretePDF(FPDF):
    """Carta con cabecera, pie paginado y tipografía Unicode.

    ``degraded`` queda en ``True`` si las fuentes vendorizadas no viajaron en la
    imagen: el documento se genera igual con las core de fpdf2 y lo DECLARA en el
    pie. Una exportación de evidencia no puede fallar por tipografía, pero
    tampoco puede perder un carácter en silencio.
    """

    #: Rótulo del tipo de documento en el pie. Lo fija cada subclase.
    tipo: str = "DOCUMENTO"

    def __init__(
        self,
        folio: str,
        subtitle: str,
        *,
        sellado: datetime | None = None,
        huella: str | None = None,
        build: str | None = None,
    ) -> None:
        super().__init__(format=_FORMATO.capitalize())
        self.folio = folio
        self.subtitle = subtitle
        #: El instante del SUCESO, el mismo que recibe `seal()`. No es la hora de
        #: generación: ver la decisión 3 del módulo.
        self.sellado = sellado
        #: Huella del CONTENIDO (no del archivo: no cabe dentro de sí mismo).
        #: `None` es legítimo —una hoja en blanco no tiene contenido— y se
        #: DECLARA en el pie en vez de dejar un hueco mudo.
        self.huella = huella
        self.build = build
        self.degraded = False
        # Misma regla que la tipografía: si el arte no viajó con el paquete el
        # documento SALE IGUAL, con la palabra compuesta. Una exportación de
        # evidencia no puede caerse por un adorno.
        self.sin_marca = not LOGOTIPO.exists()
        self.set_margins(MARGIN, 18, MARGIN)
        self.set_auto_page_break(auto=True, margin=PIE_MM)
        self._install_fonts()
        self.alias_nb_pages()

    def _install_fonts(self) -> None:
        try:
            self.add_font("dejavu", "", str(_FONTS / "DejaVuSans.ttf"))
            self.add_font("dejavu", "B", str(_FONTS / "DejaVuSans-Bold.ttf"))
            self.add_font("dejavumono", "", str(_FONTS / "DejaVuSansMono.ttf"))
            self.body_font = "dejavu"
            self.mono_font = "dejavumono"
        except (FileNotFoundError, RuntimeError):
            self.degraded = True
            self.body_font = "helvetica"
            self.mono_font = "courier"

    def text_of(self, value: str) -> str:
        """Con fuentes core hay que degradar a latin-1; con DejaVu pasa todo."""
        if not self.degraded:
            return value
        return value.encode("latin-1", "replace").decode("latin-1")

    # --- chasis ---------------------------------------------------------------

    def header(self) -> None:  # noqa: D102 - contrato de fpdf2
        if self.sin_marca:
            # Respaldo: la palabra compuesta con la tipografía del documento.
            self.set_font(self.body_font, "B", 9)
            self.set_text_color(*INK)
            self.cell(0, 5, self.text_of("TAKAB AILERT"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        else:
            # `x`/`y` explícitos: `header()` corre en CADA página y el cursor no
            # llega aquí en el mismo sitio en todas. fpdf2 embebe el PNG una sola
            # vez y lo reutiliza, así que repetirlo no engorda el documento.
            self.image(str(LOGOTIPO), x=MARGIN, y=10, w=_LOGO_MM)
            self.set_y(20)
        self.set_font(self.body_font, "", 7.5)
        self.set_text_color(*MUTED)
        self.cell(0, 4, self.text_of(self.subtitle), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*RULE)
        self.line(MARGIN, _FILETE_Y, PAGE_W - MARGIN, _FILETE_Y)
        self.set_y(CUERPO_Y)
        self.set_text_color(*INK)

    def footer(self) -> None:  # noqa: D102 - contrato de fpdf2
        """El membrete, repartido en líneas POR ARITMÉTICA.

        Medido sobre la banda útil de Carta (185.9 mm) con el peor folio real:

            identidad · tipo · folio · franja  114.5 mm   +  paginación  15.5
            SHA-256 del contenido               118.7 mm   +  evento+build 59.6
            tipografía degradada                 63.8 mm

        Las dos primeras caben emparejadas; la tercera no cabe con ninguna, y por
        eso sólo aparece cuando hace falta. ⚠️ `cell()` de fpdf2 **no envuelve**:
        lo que no cabe se dibuja encima de lo de al lado sin poner nada en rojo,
        así que esto no es una preferencia de diseño — es la única forma de que
        el pie no se pise a sí mismo. Lo vigila `test_el_pie_CABE_en_su_celda`.
        """
        self.set_y(-19)
        self.set_draw_color(*RULE)
        self.line(MARGIN, self.get_y(), PAGE_W - MARGIN, self.get_y())
        self.ln(1)
        self.set_font(self.body_font, "", 7)
        self.set_text_color(*MUTED)
        # [T-6.33] El NOMBRE, en texto y en todas las páginas. La cabecera lleva
        # el logotipo como arte, y un lector de pantalla —o un `pypdf` de la
        # contraparte que revisa el dictamen— no lee un PNG. En un documento
        # firmado, de quién es la firma no puede vivir sólo en una imagen.
        self.cell(CONTENT_W - _ANCHO_PAGINA, 3.6, self.text_of(self._linea_identidad()))
        self.cell(_ANCHO_PAGINA, 3.6, f"Pág. {self.page_no()} de {{nb}}", align="R")
        self.ln(3.6)

        # La huella del CONTENIDO, entera. Truncarla es el defecto que `T-5.26`
        # arregló: un sha a medias no verifica nada.
        self.set_font(self.mono_font, "", 6.5)
        self.cell(
            CONTENT_W - _ANCHO_SELLO,
            3.4,
            self.text_of(self._linea_huella()),
        )
        self.set_font(self.body_font, "", 7)
        self.cell(_ANCHO_SELLO, 3.4, self.text_of(self._sello_y_build()), align="R")

        if self.degraded:
            # No se calla: un dictamen al que le faltan caracteres tiene que
            # decirlo, y no cabe emparejado con nada. Su propia línea.
            self.ln(3.4)
            self.set_font(self.body_font, "", 7)
            self.cell(0, 3.4, self.text_of("TIPOGRAFÍA DEGRADADA (fuente Unicode ausente)"))

    def _linea_identidad(self) -> str:
        """Quién firma, qué tipo de papel es y su folio. En TODAS las páginas."""
        return f"TAKAB AILERT · {self.tipo} · {self.folio} · EVIDENCIA INMUTABLE"

    def _linea_huella(self) -> str:
        """La huella del contenido, o su ausencia DECLARADA."""
        if self.huella:
            return f"SHA-256 DEL CONTENIDO {self.huella}"
        return "SIN HUELLA DE CONTENIDO · ESTE DOCUMENTO NO AFIRMA DATOS"

    def _sello_y_build(self) -> str:
        """El instante del SUCESO y la build que lo imprimió.

        `EVENTO` y no «generado el»: es el instante que recibe `seal()` —el del
        incidente o el del arranque del simulacro—, no la hora de impresión. La
        diferencia no es pedante: `generated_at` es `datetime.now()`, y meterlo
        aquí haría que dos generaciones del mismo modelo dieran archivos
        distintos, con lo que «verifique el sha256» dejaría de ser cierto.
        """
        partes = []
        if self.sellado is not None:
            partes.append(f"EVENTO {self.sellado:%Y-%m-%d %H:%M} UTC")
        if self.build:
            partes.append(f"build {self.build}")
        return " · ".join(partes)

    def seal(self, created_at) -> None:
        """Metadatos fijos ⇒ mismas entradas, mismos bytes (y mismo sha256)."""
        self.set_creation_date(created_at)
        self.set_producer("TAKAB Ailert")
        self.set_creator("takab-api")
        self.set_title(self.folio)

    # --- primitivas de contenido ---------------------------------------------

    def reserva(self, alto: float) -> None:
        """Salta de página si `alto` mm no caben bajo el cursor.

        ⚠️ **fpdf2 no hace esto solo para el dibujo.** `set_auto_page_break` sólo
        mira el texto; `rect`, `line` y `polyline` se pintan donde se les diga,
        incluso encima del filete del pie. Todas las figuras del dictamen —la
        traza, la duración, el espectro, el espectrograma y el croquis— se
        dibujan así, y ninguna tenía guarda: sus topes eran cuatro números
        absolutos calibrados a ojo contra el corte de A4, y el croquis, que es la
        caja más alta del documento con sus 78 mm, no tenía ni eso.
        """
        if self.get_y() + alto > PAGE_H - PIE_MM:
            self.add_page()

    def section(self, number: str, title: str) -> None:
        self.ln(3)
        self.set_font(self.body_font, "B", 10)
        self.set_text_color(*INK)
        self.cell(0, 6, self.text_of(f"{number}. {title}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*RULE)
        self.line(MARGIN, self.get_y(), PAGE_W - MARGIN, self.get_y())
        self.ln(2)

    def para(self, text: str, *, size: float = 8.5, muted: bool = False) -> None:
        self.set_font(self.body_font, "", size)
        self.set_text_color(*(MUTED if muted else INK))
        self.multi_cell(0, 4.4, self.text_of(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(*INK)

    def field(self, label: str, value: str) -> None:
        self.set_font(self.body_font, "", 8)
        self.set_text_color(*MUTED)
        self.cell(52, 4.8, self.text_of(label))
        self.set_font(self.mono_font, "", 8)
        self.set_text_color(*INK)
        self.multi_cell(0, 4.8, self.text_of(value), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def callout(self, text: str, color: tuple[int, int, int] = MUTED) -> None:
        """Recuadro de AUSENCIA: por qué un dato no está, en vez de un hueco mudo."""
        self.ln(1)
        y = self.get_y()
        self.set_draw_color(*color)
        self.set_line_width(0.4)
        self.line(MARGIN, y, MARGIN, y + 8)
        self.set_line_width(0.2)
        self.set_x(MARGIN + 3)
        self.set_font(self.body_font, "", 7.5)
        self.set_text_color(*color)
        self.multi_cell(CONTENT_W - 3, 4, self.text_of(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(*INK)
        self.ln(1)
