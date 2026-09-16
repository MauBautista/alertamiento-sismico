"""[T-7.21] La hoja membretada EN BLANCO: el papel para lo que el sistema no genera.

Un acta a mano, una carta al cliente, una nota de una visita. Todo eso sale hoy
en papel sin membrete o en una plantilla que alguien rehízo; esto le da el mismo
chasis que el dictamen, el reporte de simulacro y el informe del evento.

Se emiten DOS formatos y no es redundancia:

* **`carta.pdf`** — para imprimir. Lo dibuja el propio `MembretePDF`, así que si
  el membrete cambia, la hoja cambia con él: no hay una segunda copia del diseño
  que se quede atrás. Es la razón de que esto viva en `api/` y no en un script
  de dibujo aparte.
* **`carta.svg`** — para editar. Vectorial y de texto plano, se abre en cualquier
  editor y se escribe encima.

⚠️ **Los dos se COMITEAN, así que los dos tienen que ser deterministas byte a
byte**, o `git diff --exit-code shared/brand/membrete` —que es lo que corre el
Goal de F4— parpadea en cada regeneración y acaba ignorándose.

Para el PDF eso significa `seal()` a un instante FIJO: fpdf2 estampa
`/CreationDate` y `/ID` con el reloj, y sin fijarlos dos generaciones de la misma
hoja darían ficheros distintos. Se usa `SELLO_DE_LA_HOJA` y no la fecha de hoy
porque una hoja en blanco no tiene fecha: la pone quien la use.
"""

from __future__ import annotations

from datetime import UTC, datetime

from takab_api.documentos.identidad import TAKAB, Identidad
from takab_api.documentos.membrete import (
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

#: El instante con el que se sella la hoja. **Fijo a propósito**: una hoja en
#: blanco no tiene fecha de suceso, y usar el reloj rompería el determinismo que
#: el artefacto comiteado necesita.
SELLO_DE_LA_HOJA = datetime(2026, 1, 1, tzinfo=UTC)

_FOLIO = "SIN FOLIO"
_SUBTITULO = "HOJA MEMBRETADA · el contenido lo aporta quien la usa"


class _Hoja(MembretePDF):
    tipo = "HOJA EN BLANCO"


def hoja_en_blanco(identidad: Identidad = TAKAB) -> bytes:
    """El PDF de la hoja, en Carta y determinista."""
    pdf = _Hoja(_FOLIO, _SUBTITULO, sellado=None, huella=None)
    pdf.seal(SELLO_DE_LA_HOJA)
    pdf.add_page()
    _emisor(pdf, identidad)
    return bytes(pdf.output())


def _emisor(pdf: MembretePDF, identidad: Identidad) -> None:
    """El bloque de quién emite, con las ausencias declaradas."""
    pdf.set_y(CUERPO_Y)
    for rotulo, valor in identidad.lineas():
        pdf.field(rotulo, valor)
    aviso = identidad.aviso()
    if aviso is not None:
        pdf.callout(aviso)


def hoja_svg(identidad: Identidad = TAKAB) -> str:
    """La misma hoja, en vectorial editable.

    Se escribe como plantilla literal —sin base64, sin rasters incrustados— para
    que el fichero sea texto comparable en un diff y determinista sin esfuerzo.
    Las medidas salen de las MISMAS constantes que el PDF: si el membrete cambia
    de márgenes, las dos cambian juntas.
    """
    lineas = identidad.lineas()
    aviso = identidad.aviso()
    campos: list[str] = []
    y = CUERPO_Y
    for rotulo, valor in lineas:
        campos.append(
            f'  <text x="{MARGIN}" y="{y}" class="rotulo">{_escapa(rotulo)}</text>\n'
            f'  <text x="{MARGIN + 52}" y="{y}" class="valor">{_escapa(valor)}</text>'
        )
        y += 6.0
    bloque_aviso = ""
    if aviso is not None:
        bloque_aviso = f'\n  <text x="{MARGIN}" y="{y + 4}" class="aviso">{_escapa(aviso)}</text>'
    return _PLANTILLA.format(
        ancho=PAGE_W,
        alto=PAGE_H,
        margen=MARGIN,
        derecha=PAGE_W - MARGIN,
        filete_cabecera=26.0,
        filete_pie=PAGE_H - PIE_MM,
        ink=_hex(INK),
        muted=_hex(MUTED),
        rule=_hex(RULE),
        subtitulo=_escapa(_SUBTITULO),
        campos="\n".join(campos),
        aviso=bloque_aviso,
        pie=_escapa(f"TAKAB AILERT · {_Hoja.tipo} · {_FOLIO} · EVIDENCIA INMUTABLE"),
    )


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def _escapa(texto: str) -> str:
    return texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


#: Sin `id` aleatorios ni fecha: el fichero es el mismo en cada corrida.
_PLANTILLA = """<?xml version="1.0" encoding="UTF-8"?>
<!-- Generado por shared/brand/generar.py (T-7.21). No editar a mano: se regenera. -->
<svg xmlns="http://www.w3.org/2000/svg" width="{ancho}mm" height="{alto}mm"
     viewBox="0 0 {ancho} {alto}">
  <style>
    text {{ font-family: "DejaVu Sans", sans-serif; }}
    .subtitulo {{ font-size: 2.6px; fill: {muted}; letter-spacing: 0.1px; }}
    .rotulo {{ font-size: 2.8px; fill: {muted}; }}
    .valor {{ font-size: 2.8px; fill: {ink}; font-family: "DejaVu Sans Mono", monospace; }}
    .aviso {{ font-size: 2.6px; fill: {muted}; }}
    .pie {{ font-size: 2.5px; fill: {muted}; }}
  </style>
  <rect width="{ancho}" height="{alto}" fill="#FFFFFF"/>
  <text x="{margen}" y="22" class="subtitulo">{subtitulo}</text>
  <line x1="{margen}" y1="{filete_cabecera}" x2="{derecha}" y2="{filete_cabecera}"
        stroke="{rule}" stroke-width="0.2"/>
{campos}{aviso}
  <line x1="{margen}" y1="{filete_pie}" x2="{derecha}" y2="{filete_pie}"
        stroke="{rule}" stroke-width="0.2"/>
  <text x="{margen}" y="{filete_pie}" dy="3.2" class="pie">{pie}</text>
</svg>
"""
