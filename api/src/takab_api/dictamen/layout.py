"""Chasis del PDF de DICTAMEN: lo que sólo el dictamen tiene.

[T-7.21] Casi todo lo que vivía aquí subió a `takab_api.documentos.membrete`,
que es el chasis compartido: cabecera, pie, tipografía, paleta y primitivas. Se
quedan aquí las DOS piezas que son del dictamen y de nadie más — el color del
veredicto y la banda que lo pinta—, porque sus claves son los cuatro veredictos
periciales y un reporte de simulacro no tiene veredicto.

`TakabPDF` conserva su nombre: lo instancian `dictamen/pdf.py` y `drill_report.py`,
y renombrarlo habría sido un cambio de superficie sin ganancia.

Lo que se re-exporta (`MARGIN`, `CONTENT_W`, `INK`, `MUTED`, `RULE`) es para no
partir a quien ya lo importaba de aquí. ⚠️ `dictamen/pdf.py` reexporta `CONTENT_W`
y `tests/dictamen/test_graficas_honestas.py` lo importa DE AHÍ: quitarlo mataría
esa suite en la colecta, no en un assert — el modo de fallo que este repositorio
ya tiene medido como «el import que tumba una suite a 0 test en silencio».
"""

from __future__ import annotations

from fpdf.enums import XPos, YPos

from takab_api.documentos.membrete import (
    CONTENT_W,
    CUERPO_Y,
    INK,
    MARGIN,
    MUTED,
    PAGE_H,
    PAGE_W,
    PIE_MM,
    RULE,
    MembretePDF,
)

__all__ = [
    "CONTENT_W",
    "CUERPO_Y",
    "INK",
    "MARGIN",
    "MUTED",
    "PAGE_H",
    "PAGE_W",
    "PIE_MM",
    "RULE",
    "VERDICT_COLORS",
    "TakabPDF",
]

VERDICT_COLORS: dict[str, tuple[int, int, int]] = {
    "no_inhabit_inspect": (196, 48, 43),
    "restricted": (214, 132, 20),
    "inhabit_monitor": (214, 168, 20),
    "normal_operation": (38, 140, 78),
}


class TakabPDF(MembretePDF):
    """El membrete, más la banda de veredicto que sólo el dictamen usa."""

    tipo = "DICTAMEN"
    #: [T-7.42] Afirma un veredicto de habitabilidad: su pie imprime la huella.
    afirma_datos = True

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
