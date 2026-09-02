"""Reporte post-simulacro (T-5.14) — la evidencia que se le enseña a Protección Civil.

**El problema que cierra.** El acuse por sitio estaba bien hecho y era honesto —
distingue *sin gabinete comandable* de *sin acuse*, dos cosas que colapsar sería
mentir—, pero le faltaban las dos que el cliente pide: **el tiempo** (no existía
en ninguna capa) y **la salida** (no había PDF ni CSV; el propio código llamaba a
esto «la evidencia de cumplimiento» y solo se podía mirar en una pantalla).

**Las tres categorías no se colapsan, y ése es el punto del documento.** Un sitio
que no tenía gabinete comandable **no es** un sitio que no acusó: el primero es un
problema de inventario y el segundo de operación, y la reacción de quien lee el
reporte es distinta. Van en tres bloques con su conteo.

**Y un sitio sin acuse NO cuenta como cero en el tiempo.** Meterlo en la media la
hundiría hacia abajo justo con los sitios que peor están, que es la forma más
elegante de que un número diga lo contrario de lo que pasa.

El documento es **determinista** (mismo modelo, mismos bytes) porque su sello fija
la fecha de creación al arranque del simulacro y no al reloj de quien exporta —
sin eso, dos exportaciones del mismo simulacro darían hashes distintos y la
huella no probaría nada.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from fpdf.enums import XPos, YPos

from takab_api.dictamen.layout import MUTED, TakabPDF

#: Lo que el documento declara que NO es. Va impreso, como el del dictamen.
DESLINDE = (
    "Reporte operativo de simulacro. Acredita QUÉ gabinetes acusaron la orden y en cuánto "
    "tiempo; no acredita que las personas evacuaran ni sustituye el acta del simulacro que "
    "levanta la brigada del inmueble."
)


@dataclass(frozen=True)
class SitioReporte:
    site_name: str
    commandable: bool
    acked: bool
    latency_s: float | None


@dataclass
class ReporteSimulacro:
    folio: str
    tenant_name: str
    drill_id: str
    started_at: datetime | None
    stopped_at: datetime | None
    duration_s: int
    note: str
    sitios: list[SitioReporte] = field(default_factory=list)

    # --- los tres grupos, derivados y sin colapsar -------------------------
    @property
    def acusaron(self) -> list[SitioReporte]:
        return [s for s in self.sitios if s.commandable and s.acked]

    @property
    def no_acusaron(self) -> list[SitioReporte]:
        return [s for s in self.sitios if s.commandable and not s.acked]

    @property
    def sin_gabinete(self) -> list[SitioReporte]:
        return [s for s in self.sitios if not s.commandable]

    @property
    def latencias(self) -> list[float]:
        return sorted(s.latency_s for s in self.acusaron if s.latency_s is not None)

    @property
    def latencia_mediana_s(self) -> float | None:
        """`None` si nadie acusó. Los que no acusaron NO entran como cero."""
        v = self.latencias
        if not v:
            return None
        m = len(v) // 2
        return v[m] if len(v) % 2 else (v[m - 1] + v[m]) / 2

    @property
    def latencia_maxima_s(self) -> float | None:
        v = self.latencias
        return v[-1] if v else None


def _t(segundos: float | None) -> str:
    """`252.0` → `4 min 12 s`. Sin dato dice SIN ACUSE, jamás `0 s`."""
    if segundos is None:
        return "SIN ACUSE"
    s = int(round(segundos))
    return f"{s // 60} min {s % 60:02d} s" if s >= 60 else f"{s} s"


def render(rep: ReporteSimulacro) -> bytes:
    """PDF determinista del post-simulacro."""
    pdf = TakabPDF(rep.folio, f"REPORTE DE SIMULACRO · {rep.tenant_name}")
    # La fecha del sello es la del SIMULACRO, no la de la exportación: si fuera la
    # segunda, dos exportaciones del mismo simulacro darían hashes distintos y la
    # huella dejaría de probar nada.
    pdf.seal(rep.started_at)
    pdf.add_page()

    pdf.section("1", "EL SIMULACRO")
    pdf.field("IDENTIFICADOR", rep.drill_id)
    pdf.field("INICIO", f"{rep.started_at:%Y-%m-%d %H:%M:%S} UTC" if rep.started_at else "S/D")
    pdf.field("FIN", f"{rep.stopped_at:%Y-%m-%d %H:%M:%S} UTC" if rep.stopped_at else "SIN CERRAR")
    pdf.field("DURACIÓN PEDIDA", f"{rep.duration_s} s")
    if rep.note:
        pdf.field("NOTA", rep.note)

    pdf.section("2", "ACUSE POR SITIO")
    # Las tres categorías con su conteo, y SIN colapsar: «no tenía gabinete» es un
    # problema de inventario y «no acusó» uno de operación.
    pdf.field("SITIOS QUE ACUSARON", f"{len(rep.acusaron)} de {len(rep.sitios)}")
    pdf.field("SITIOS QUE NO ACUSARON", str(len(rep.no_acusaron)))
    pdf.field("SITIOS SIN GABINETE COMANDABLE", str(len(rep.sin_gabinete)))

    pdf.ln(1)
    pdf.set_font(pdf.mono_font, "", 7.5)
    for s in rep.acusaron:
        pdf.cell(
            0,
            3.8,
            pdf.text_of(f"ACUSÓ           {s.site_name:<34} {_t(s.latency_s)}"),
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
    for s in rep.no_acusaron:
        pdf.cell(
            0,
            3.8,
            pdf.text_of(f"NO ACUSÓ        {s.site_name:<34} —"),
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
    for s in rep.sin_gabinete:
        pdf.cell(
            0,
            3.8,
            pdf.text_of(f"SIN GABINETE    {s.site_name:<34} —"),
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )

    pdf.section("3", "TIEMPOS")
    if rep.latencia_mediana_s is None:
        pdf.callout(
            "NINGÚN SITIO ACUSÓ · no hay tiempos que reportar. La ausencia no es un cero: "
            "significa que no hubo un solo acuse, no que fueran instantáneos.",
            MUTED,
        )
    else:
        pdf.field("MEDIANA", _t(rep.latencia_mediana_s))
        pdf.field("MÁXIMO", _t(rep.latencia_maxima_s))
        pdf.para(
            "Calculados SOLO sobre los sitios que acusaron. Los que no acusaron no entran "
            "como cero: meterlos hundiría la media justo con los sitios que peor están.",
            size=7.5,
            muted=True,
        )

    pdf.section("4", "DESLINDE")
    pdf.callout(DESLINDE, (20, 24, 30))
    return bytes(pdf.output())
