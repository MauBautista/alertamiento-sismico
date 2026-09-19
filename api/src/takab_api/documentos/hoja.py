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
from functools import lru_cache

from takab_api.documentos import membrete as _membrete
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

# ── La caja de texto del SVG, y por qué hay que medirla ──────────────────────
#
# ⚠️ [T-7.21 · PENDIENTES §4.8] UN `<text>` DE SVG NO ENVUELVE. Dibuja la cadena
# entera en una línea y, si no cabe, la saca de la hoja sin poner nada en rojo —
# exactamente el mismo desborde mudo que `cell()` de fpdf2 provocaba en el pie y
# que esta misma ficha ya tuvo que cazar allí. El PDF no lo sufre porque
# `MembretePDF.field()` usa `multi_cell`, que sí envuelve; el SVG estaba sin
# guarda y nadie lo notó mientras los cuatro valores eran el mismo literal corto
# (`PENDIENTE · PENDIENTES-MAURICIO §4.8`, 37 caracteres).
#
# Lo destapó el dato real: la razón social con su forma societaria mide 84
# caracteres y **se salía 7.7 mm** de la hoja. El domicilio, 79, entraba por
# 0.7 mm. Un margen de 0.7 mm no es que quepa: es que todavía no se ha roto.
#
# Las medidas se DERIVAN de las mismas constantes que el PDF y de la TIPOGRAFÍA
# REAL —no de un «más o menos 0.6 em»—, igual que la geometría de la página se
# deriva de `PAGE_FORMATS` en vez de teclearse.
_X_VALOR = MARGIN + 52
_ANCHO_VALOR = round((PAGE_W - MARGIN) - _X_VALOR, 4)
_ANCHO_AVISO = round(PAGE_W - 2 * MARGIN, 4)
_FS_VALOR = 2.8
_FS_AVISO = 2.6
#: Separación entre renglones de un mismo valor envuelto.
_INTERLINEA = 3.4
#: Alto de una fila de campo cuando el valor cabe en un renglón.
_FILA = 6.0
_MONO = "DejaVuSansMono.ttf"
_SANS = "DejaVuSans.ttf"
#: Avance de la monoespaciada, en em, **si la tipografía no viajó**. Es el valor
#: real de DejaVu Sans Mono (1233/2048); `test_hoja_svg` lo re-deriva del fichero
#: y falla si dejan de coincidir, para que este número no envejezca en silencio.
_AVANCE_MONO = 1233 / 2048
#: Respaldo de la proporcional: el avance de su glifo MÁS ANCHO, que sobreestima
#: a propósito. Sin tipografía se prefiere envolver de más a salirse de la hoja.
_AVANCE_SANS = 1493 / 2048


class _Hoja(MembretePDF):
    tipo = "HOJA EN BLANCO"
    #: [T-7.21] El único papel que NO repite el emisor abajo: lo imprime entero
    #: —los cuatro datos, no dos— en el cuerpo, que es exactamente su razón de
    #: ser. Repetir la razón social al pie de una hoja cuyo cuerpo está vacío a
    #: propósito sería decir dos veces lo único que dice.
    emisor_en_pie = False
    #: [T-7.42] La ÚNICA que no afirma datos, y por eso la única cuyo pie declara
    #: la ausencia de huella. El contenido lo aporta quien la use: firmar el vacío
    #: verificaría que el vacío no cambió, que no es respaldar un dato.
    afirma_datos = False


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
    campos: list[str] = []
    y = CUERPO_Y
    for rotulo, valor in identidad.lineas():
        trozos = _envuelve(valor, _MONO, _FS_VALOR, _ANCHO_VALOR, _AVANCE_MONO)
        partes = [f'  <text x="{_mm(MARGIN)}" y="{_mm(y)}" class="rotulo">{_escapa(rotulo)}</text>']
        for i, trozo in enumerate(trozos):
            partes.append(
                f'  <text x="{_mm(_X_VALOR)}" y="{_mm(y + i * _INTERLINEA)}" '
                f'class="valor">{_escapa(trozo)}</text>'
            )
        campos.append("\n".join(partes))
        y += _FILA + (len(trozos) - 1) * _INTERLINEA
    bloque_aviso = ""
    aviso = identidad.aviso()
    if aviso is not None:
        y += 4.0
        renglones = _envuelve(aviso, _SANS, _FS_AVISO, _ANCHO_AVISO, _AVANCE_SANS)
        bloque_aviso = "\n" + "\n".join(
            f'  <text x="{_mm(MARGIN)}" y="{_mm(y + i * _INTERLINEA)}" '
            f'class="aviso">{_escapa(renglon)}</text>'
            for i, renglon in enumerate(renglones)
        )
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


@lru_cache(maxsize=4)
def _avances(fichero: str) -> tuple[int, dict[int, int], int] | None:
    """`(unidades por em, avance por codepoint, avance del glifo más ancho)`.

    Sale de la MISMA tipografía que embebe el PDF —se lee `membrete._FONTS` en
    cada llamada, no al importar, para que el parche de las pruebas que simulan
    «la fuente no viajó» valga también aquí—. Devuelve `None` si no está, y
    entonces se mide con el respaldo declarado.
    """
    try:
        from fontTools.ttLib import TTFont
    except ImportError:  # pragma: no cover - fontTools llega con fpdf2
        return None
    ruta = _membrete._FONTS / fichero
    if not ruta.exists():
        return None
    fuente = TTFont(ruta)
    upm = fuente["head"].unitsPerEm
    hmtx = fuente["hmtx"]
    por_codigo = {
        cp: hmtx[nombre][0] for cp, nombre in fuente.getBestCmap().items() if nombre in hmtx.metrics
    }
    return upm, por_codigo, max(por_codigo.values(), default=upm)


def _ancho(texto: str, fichero: str, fs: float, respaldo_em: float) -> float:
    """Ancho en mm de `texto` a `fs` unidades, con la tipografía REAL."""
    medidas = _avances(fichero)
    if medidas is None:
        return len(texto) * fs * respaldo_em
    upm, por_codigo, mas_ancho = medidas
    # Un glifo desconocido se cuenta como el más ancho de la fuente: ante la
    # duda se envuelve de más, nunca de menos. Salirse de la hoja es el fallo.
    return sum(por_codigo.get(ord(c), mas_ancho) for c in texto) * fs / upm


def _envuelve(texto: str, fichero: str, fs: float, caja: float, respaldo_em: float) -> list[str]:
    """Parte `texto` en los renglones que caben en `caja` milímetros.

    Corta por espacios y, si una sola palabra ya no cabe —una URL, un hash—, la
    parte a la fuerza: el contrato es que NINGÚN renglón se sale, y una palabra
    indivisible no es excusa para devolver uno que sí.
    """
    renglones: list[str] = []
    actual = ""
    for palabra in texto.split(" "):
        for trozo in _trocea(palabra, fichero, fs, caja, respaldo_em):
            tentativa = f"{actual} {trozo}" if actual else trozo
            if actual and _ancho(tentativa, fichero, fs, respaldo_em) > caja:
                renglones.append(actual)
                actual = trozo
            else:
                actual = tentativa
    if actual:
        renglones.append(actual)
    return renglones or [""]


def _trocea(palabra: str, fichero: str, fs: float, caja: float, respaldo_em: float) -> list[str]:
    """Una palabra más ancha que la caja, partida en pedazos que sí caben."""
    if _ancho(palabra, fichero, fs, respaldo_em) <= caja:
        return [palabra]
    pedazos: list[str] = []
    actual = ""
    for caracter in palabra:
        if actual and _ancho(actual + caracter, fichero, fs, respaldo_em) > caja:
            pedazos.append(actual)
            actual = caracter
        else:
            actual += caracter
    if actual:
        pedazos.append(actual)
    return pedazos


def _mm(valor: float) -> str:
    """Coordenada del SVG, redondeada. El fichero se comitea: tiene que salir
    igual byte a byte en cada corrida, y un `0.1 + 0.2` no lo hace."""
    return f"{round(valor, 3):g}"


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
