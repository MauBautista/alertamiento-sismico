"""Chasis del PDF de dictamen (T-2.41): tipografía, encabezado, pie y primitivas.

Todo el dibujo sale de fpdf2 —``line``, ``rect``, ``polyline``, ``circle``, ``table``—
sin rasterizar nada. Un vector pesa menos, no pixela al imprimir en A4 y, sobre todo,
es DETERMINISTA byte a byte: un PNG no garantiza los mismos bytes entre versiones del
codificador, y el sha256 del dictamen es lo que lo hace evidencia.

**Determinismo**: fpdf2 estampa ``/CreationDate`` con el reloj. Sin fijarlo, dos
generaciones del mismo modelo darían hashes distintos y la promesa de "verifique el
sha256" sería falsa. ``TakabPDF.seal`` lo fija a un instante del propio incidente.
"""

from __future__ import annotations

from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos

_FONTS = Path(__file__).parent / "fonts"

#: Paleta del PDF (RGB). Deliberadamente sobria: un dictamen no es un tablero.
INK = (20, 24, 30)
MUTED = (110, 120, 132)
RULE = (200, 206, 214)
VERDICT_COLORS: dict[str, tuple[int, int, int]] = {
    "no_inhabit_inspect": (196, 48, 43),
    "restricted": (214, 132, 20),
    "inhabit_monitor": (214, 168, 20),
    "normal_operation": (38, 140, 78),
}

PAGE_W = 210.0
MARGIN = 15.0
CONTENT_W = PAGE_W - 2 * MARGIN


class TakabPDF(FPDF):
    """A4 con encabezado, pie paginado y tipografía Unicode.

    ``degraded`` queda en ``True`` si las fuentes vendorizadas no viajaron en la
    imagen: el documento se genera igual con las core de fpdf2 y lo DECLARA en el pie.
    Una exportación de evidencia no puede fallar por tipografía, pero tampoco puede
    perder un carácter en silencio.
    """

    def __init__(self, folio: str, subtitle: str) -> None:
        super().__init__(format="A4")
        self.folio = folio
        self.subtitle = subtitle
        self.degraded = False
        self.set_margins(MARGIN, 18, MARGIN)
        self.set_auto_page_break(auto=True, margin=20)
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
        self.set_font(self.body_font, "B", 9)
        self.set_text_color(*INK)
        self.cell(0, 5, self.text_of("TAKAB AILERT"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_font(self.body_font, "", 7.5)
        self.set_text_color(*MUTED)
        self.cell(0, 4, self.text_of(self.subtitle), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*RULE)
        self.line(MARGIN, 26, PAGE_W - MARGIN, 26)
        self.set_y(32)
        self.set_text_color(*INK)

    def footer(self) -> None:  # noqa: D102 - contrato de fpdf2
        self.set_y(-15)
        self.set_draw_color(*RULE)
        self.line(MARGIN, self.get_y(), PAGE_W - MARGIN, self.get_y())
        self.ln(1)
        self.set_font(self.body_font, "", 7)
        self.set_text_color(*MUTED)
        left = f"{self.folio} · EVIDENCIA INMUTABLE"
        if self.degraded:
            # No se calla: un dictamen al que le faltan caracteres tiene que decirlo.
            left += " · TIPOGRAFÍA DEGRADADA (fuente Unicode ausente)"
        self.cell(CONTENT_W - 30, 4, self.text_of(left))
        self.cell(30, 4, f"Pág. {self.page_no()} de {{nb}}", align="R")

    def seal(self, created_at) -> None:
        """Metadatos fijos ⇒ mismas entradas, mismos bytes (y mismo sha256)."""
        self.set_creation_date(created_at)
        self.set_producer("TAKAB Ailert")
        self.set_creator("takab-api")
        self.set_title(self.folio)

    # --- primitivas de contenido ---------------------------------------------

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

    def verdict_banner(self, status: str, label: str, signed: bool) -> None:
        color = VERDICT_COLORS.get(status, MUTED)
        y = self.get_y()
        self.set_fill_color(*color)
        self.rect(MARGIN, y, CONTENT_W, 16, style="F")
        self.set_xy(MARGIN + 4, y + 3)
        self.set_text_color(255, 255, 255)
        self.set_font(self.body_font, "B", 13)
        self.cell(CONTENT_W - 8, 6, self.text_of(label), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_x(MARGIN + 4)
        self.set_font(self.body_font, "", 7.5)
        self.cell(
            CONTENT_W - 8,
            4,
            self.text_of("DICTAMEN FIRMADO" if signed else "DICTAMEN AUTOMÁTICO PRELIMINAR"),
        )
        self.set_xy(MARGIN, y + 19)
        self.set_text_color(*INK)
