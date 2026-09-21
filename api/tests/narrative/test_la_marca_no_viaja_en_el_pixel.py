"""T-7.27·A · La marca de agua forense va DIBUJADA, y ninguna guarda miraba los píxeles.

Las dos pruebas que decían vigilar la privacidad de la fotografía miraban BYTES: una de
verdad (`test_las_fotos_van_REENCODADAS_y_el_EXIF_del_telefono_NO_viaja`) y la otra en
base64, o sea vacua. Y la marca de agua no está en los bytes del EXIF: está pintada
encima, con las coordenadas del inmueble a cinco decimales y los ocho primeros hex del
`sub` del operador — los dos identificadores exactos que la allowlist de `redact.py`
existe para retener del JSON.

Lo que este fichero fija, y en este orden:

1. **La geometría de la marca se LEE del móvil**, no se teclea aquí. Si la marca se
   mueve de sitio, gana una línea o cambia un token, esto se pone rojo y hay que volver
   a medir el tapado. Un tapado por geometría tecleada es el censo ciego que este
   repositorio lleva seis veces pagando.
2. **El tapado se mide SOBRE LOS PÍXELES.** Se compone una captura sin marca y la misma
   con marca, se derivan las dos por el camino real (`documentos/fotos.preparar`), se
   RESTAN y se exige que todos los píxeles que cambiaron caigan dentro de la banda que
   `narrative/marca.py` tapa.
3. **Lo que no cabe, no sale**, y se declara.
4. **Y en el cuerpo HTTP real** se decodifica el base64 y se mira la imagen, que es lo
   que la aserción vacua no hacía.

⚠️ **Lo que esta guarda NO afirma.** El render de abajo es una REPRODUCCIÓN de la
composición de React Native con Pillow, no el render de Android: las métricas exactas de
la tipografía del sistema no se pueden medir desde `api/`. Lo que se afirma es que el
tapado contiene a la región que cambia una marca **con la geometría que el móvil
declara**, y que esa geometría es la que `narrative/marca.py` supone. Por eso el punto 1
existe y por eso se lee del móvil en vez de copiarse.
"""

from __future__ import annotations

import base64
import io
import json
import re
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
from PIL import Image, ImageChops, ImageDraw, ImageFont

from takab_api.documentos import fotos as fotos_mod
from takab_api.narrative import build_narrative
from takab_api.narrative.marca import (
    ALTO_BANDA_DP,
    BANDA_NO_CABE,
    ESCALA_MAXIMA,
    GAP_DP,
    LINEAS_MAX,
    MINIMO_VISIBLE,
    NO_ADELGAZA,
    NO_LEGIBLE,
    OFFSET_DP,
    PADDING_DP,
    TEXTO_DP,
    alto_de_la_banda,
    tapar_banda_forense,
)
from takab_api.narrative.prompts import INSTRUCCION_FOTOS
from takab_api.narrative.redact import imagenes_de
from tests.narrative.grabado import CHAT_CON_IMAGEN, enrutar
from tests.narrative.test_lo_que_ve_la_ia import _con_danos, _dano, _foto_cruda, _foto_fila
from tests.narrative.test_redact import BASIS
from tests.narrative.test_vision_del_modelo import _ajustes

_RAIZ = Path(__file__).resolve().parents[3]
_TOKENS = _RAIZ / "shared/design-tokens/tokens.json"
_CAMARA = _RAIZ / "mobile/src/app/camera.tsx"
_MARCA_TS = _RAIZ / "mobile/src/features/forensic/watermark.ts"
_APP_JSON = _RAIZ / "mobile/app.json"


# ── 1 · la geometría se LEE del móvil ────────────────────────────────────────


@dataclass(frozen=True)
class GeometriaDelMovil:
    """Lo que la app declara sobre dónde y cómo se pinta la marca."""

    texto_dp: float
    padding_dp: float
    gap_dp: float
    offset_dp: float
    lineas: int
    orientacion: str
    anclada_abajo: bool


def _token_px(nombre: str) -> float:
    tokens = json.loads(_TOKENS.read_text("utf-8"))
    valor = tokens.get(nombre)
    assert isinstance(valor, str) and valor.endswith("px"), (
        f"el token {nombre!r} ya no es una medida en px: {valor!r}. La marca de agua se "
        "dimensiona con él y el tapado se deriva de su valor."
    )
    return float(valor[:-2])


def _bloque(fuente: str, nombre: str) -> str:
    m = re.search(rf"\n  {nombre}:\s*\{{(.*?)\n  \}},", fuente, re.S)
    if m is None:
        m = re.search(rf"\n  {nombre}:\s*\{{([^}}]*)\}},", fuente, re.S)
    assert m is not None, (
        f"no se encontró el estilo {nombre!r} en camera.tsx. El tapado de la marca se "
        "deriva de ese bloque: si cambió de forma, vuelve a medirlo antes de seguir."
    )
    return m.group(1)


def _elementos_del_array(cuerpo: str) -> list[str]:
    """Los elementos de primer nivel del array que devuelve `watermarkLines`."""
    dentro = re.search(r"return\s*\[(.*?)\n  \];", cuerpo, re.S)
    assert dentro is not None, "watermarkLines ya no devuelve un array literal"
    texto = dentro.group(1)
    piezas: list[str] = []
    actual: list[str] = []
    profundidad = 0
    comilla: str | None = None
    for ch in texto:
        if comilla:
            actual.append(ch)
            if ch == comilla:
                comilla = None
            continue
        if ch in "\"'`":
            comilla = ch
        elif ch in "([{":
            profundidad += 1
        elif ch in ")]}":
            profundidad -= 1
        elif ch == "," and profundidad == 0:
            piezas.append("".join(actual).strip())
            actual = []
            continue
        actual.append(ch)
    resto = "".join(actual).strip()
    if resto:
        piezas.append(resto)
    return [p for p in piezas if p]


def geometria_del_movil(
    *, camara: str | None = None, marca: str | None = None, app: str | None = None
) -> GeometriaDelMovil:
    """Lee del móvil todo lo que el tapado supone. **Falla si no lo puede leer.**

    No devuelve valores por omisión a propósito: un extractor que se encoge de hombros
    cuando el fichero cambia deja el tapado apuntando a donde la marca ya no está, que
    es precisamente el fallo silencioso que esto viene a impedir.

    Los tres argumentos son la costura de la AUTOPRUEBA de abajo: sirven para pasarle
    fuentes movidas a mano y comprobar que se queja, sin tocar `mobile/`.
    """
    camara = _CAMARA.read_text("utf-8") if camara is None else camara
    caja = _bloque(camara, "watermark")
    texto = _bloque(camara, "watermarkText")

    assert 'position: "absolute"' in caja, "la marca dejó de posicionarse en absoluto"
    assert re.search(r"\btop:", caja) is None and re.search(r"\bright:", caja) is None, (
        "la marca se ancla a un borde nuevo: el tapado solo cubre la banda INFERIOR"
    )
    m_bottom = re.search(r"\bbottom:\s*space\[(\d)\]", caja)
    m_padding = re.search(r"\bpadding:\s*space\[(\d)\]", caja)
    m_gap = re.search(r"\bgap:\s*(\d+)", caja)
    m_texto = re.search(r"fontSize:\s*fontSize\.(\w+)", texto)
    assert m_bottom and m_padding and m_gap and m_texto, (
        "la caja de la marca ya no declara bottom/padding/gap/fontSize como se esperaba"
    )

    elementos = _elementos_del_array(_MARCA_TS.read_text("utf-8") if marca is None else marca)
    for pieza in elementos:
        if pieza.startswith("..."):
            assert re.match(r"^\.\.\.\(.*\?\s*\[\]\s*:\s*\[[^\]]+\]\)$", pieza, re.S), (
                f"la marca compone un número de líneas que esta guarda no sabe acotar: {pieza!r}"
            )

    return GeometriaDelMovil(
        texto_dp=_token_px(f"--tk-text-{m_texto.group(1)}"),
        padding_dp=_token_px(f"--tk-space-{m_padding.group(1)}"),
        gap_dp=float(m_gap.group(1)),
        offset_dp=_token_px(f"--tk-space-{m_bottom.group(1)}"),
        lineas=len(elementos),
        orientacion=json.loads(_APP_JSON.read_text("utf-8") if app is None else app)["expo"][
            "orientation"
        ],
        anclada_abajo=True,
    )


def contrastar(g: GeometriaDelMovil) -> None:
    """Los números de `marca.py` contra los del móvil, uno a uno.

    Vive aparte del test para que la AUTOPRUEBA de abajo pueda pasarle geometrías
    movidas a mano y exigir que se queje.
    """
    assert (g.texto_dp, g.padding_dp, g.gap_dp, g.offset_dp) == (
        TEXTO_DP,
        PADDING_DP,
        GAP_DP,
        OFFSET_DP,
    ), f"la marca cambió de medidas: {g}"
    assert g.lineas == LINEAS_MAX, (
        f"`watermarkLines` compone {g.lineas} líneas y el tapado supone {LINEAS_MAX}"
    )
    assert g.orientacion == "portrait", (
        "la app ya no está fijada en vertical: una captura apaisada deja la marca en una "
        "banda que el tapado no dimensiona"
    )
    # Y la cuenta entera, por si alguien tocara la fórmula y no los números.
    esperado = (
        g.offset_dp
        + 2 * g.padding_dp
        + g.lineas * g.texto_dp * ESCALA_MAXIMA * 1.4
        + (g.lineas - 1) * g.gap_dp
    )
    assert ALTO_BANDA_DP == pytest.approx(esperado), (
        f"el alto de la banda ({ALTO_BANDA_DP}) no es el que sale del móvil ({esperado})"
    )


def test_la_geometria_que_el_TAPADO_SUPONE_es_la_que_el_movil_declara() -> None:
    """La guarda contra el censo ciego: si la marca se mueve, esto se pone rojo ANTES de
    que la fuga vuelva en silencio."""
    contrastar(geometria_del_movil())


#: Las tres formas en que la marca puede moverse sin que nadie de `api/` se entere, con
#: la fuente movida a mano. Es la AUTOPRUEBA del extractor: sin ella, la guarda de
#: arriba prometería vigilar el móvil y lo único que afirmaría es que hoy los números
#: coinciden — un extractor que devolviera siempre lo mismo la dejaría verde.
_MOVIDAS = [
    pytest.param(
        {"camara": _CAMARA.read_text("utf-8").replace("bottom: space[3]", "top: space[3]")},
        id="la marca se va ARRIBA",
    ),
    pytest.param(
        {"camara": _CAMARA.read_text("utf-8").replace("padding: space[2]", "padding: space[5]")},
        id="la caja engorda el padding",
    ),
    pytest.param(
        {"camara": _CAMARA.read_text("utf-8").replace("gap: 2,", "gap: 9,")},
        id="crece la separación entre líneas",
    ),
    pytest.param(
        {
            "marca": _MARCA_TS.read_text("utf-8").replace(
                "fmtGps(meta.gps),", 'fmtGps(meta.gps),\n    "UNA LÍNEA MÁS",'
            )
        },
        id="la marca gana una línea",
    ),
    pytest.param(
        {"app": json.dumps({"expo": {"orientation": "default"}})},
        id="la app deja de estar fijada en vertical",
    ),
]


@pytest.mark.parametrize("movida", _MOVIDAS)
def test_si_la_marca_SE_MUEVE_esta_guarda_lo_ve(movida: dict) -> None:
    """La autoprueba del extractor, con las fuentes movidas a mano y sin tocar `mobile/`.

    Cada una de estas cinco mudanzas deja el tapado apuntando a donde la marca ya no
    está. Ninguna se puede hacer sin que esto se ponga rojo.
    """
    with pytest.raises(AssertionError):
        contrastar(geometria_del_movil(**movida))


# ── 2 · el tapado se mide SOBRE LOS PÍXELES ──────────────────────────────────

#: Las SEIS líneas que `watermarkLines` puede componer —cinco fijas más la advertencia
#: condicional de metadatos retenidos—, con los dos identificadores reales dentro. Se
#: escriben aquí porque el render necesita TEXTO; el número de líneas NO se teclea: sale
#: del móvil (`geometria_del_movil`) y lo contrasta la guarda de arriba. Las dos que
#: importan —el GPS a cinco decimales y los ocho hex del `sub`— son las que el escéptico
#: leyó a simple vista ampliando el recorte inferior de una derivada.
LINEAS_REALES = (
    "TAKAB AILERT · EVIDENCIA FORENSE",
    "METADATOS RETENIDOS · SNAPSHOT 2026-09-21 18:04:11Z · sin conexión",
    "2026-09-21 18:07:55Z · NTP +12.0 ms",
    "GPS 19.43260, -99.13320",
    "PGA 0.081 g (gabinete)",
    "OP 9f1e4a2c · SHA-256",
)

#: Diferencia por canal a partir de la cual se considera que un píxel CAMBIÓ. El JPEG es
#: con pérdida y re-encodar la misma imagen dos veces no da bit a bit lo mismo; el suelo
#: de ruido se mide abajo (`test_el_suelo_de_ruido_…`) para que este número no sea una
#: opinión.
UMBRAL_CAMBIO = 24

#: Lo que el timbre del JPEG deja en el borde de un rectángulo negro sobre contenido
#: denso. MEDIDO sobre una derivada de 768×1024: 19 en la primera fila de la banda, 11
#: dos filas más abajo y 0 a partir de la octava. No es texto: el de la marca era blanco
#: puro (255) sobre un velo al 55 %.
_TIMBRE_DEL_JPEG = 24


def _luminancia(im: Image.Image) -> tuple[int, float]:
    """`(máximo, media)` de una imagen en escala de grises. La media es lo que distingue
    una banda tapada de una banda con texto: un máximo suelto lo produce el timbre del
    JPEG, una media alta no."""
    histograma = im.histogram()
    total = sum(histograma)
    media = sum(v * n for v, n in enumerate(histograma)) / total
    return im.getextrema()[1], media


def _captura(ancho_px: int, alto_px: int) -> Image.Image:
    """Una fotografía sintética con contenido en TODA la superficie.

    Con un fondo liso el JPEG no tendría ruido y la medición saldría bonita por la razón
    equivocada: lo que se quiere medir es el cambio de la marca sobre una imagen real.
    """
    im = Image.new("RGB", (ancho_px, alto_px))
    px = im.load()
    for y in range(alto_px):
        for x in range(ancho_px):
            px[x, y] = ((x * 7 + y * 3) % 256, (y * 13) % 256, (x * x + y) % 256)
    return im


def _con_marca(base: Image.Image, *, ratio: float, escala: float, lineas: int) -> Image.Image:
    """La misma captura con la marca compuesta donde la compone el móvil.

    REPRODUCCIÓN de la composición de React Native, no el render de Android: caja
    absoluta abajo a la izquierda, `bottom`/`left` de `space[3]`, `padding` de
    `space[2]`, `gap` de 2 y el texto a `fontSize.xs` multiplicado por la escala
    tipográfica del sistema.
    """
    im = base.copy()
    d = ImageDraw.Draw(im, "RGBA")
    tam = max(1, round(TEXTO_DP * escala * ratio))
    fuente = ImageFont.load_default(size=tam)
    alto_linea = round(tam * 1.2)
    gap = round(GAP_DP * ratio)
    padding = round(PADDING_DP * ratio)
    offset = round(OFFSET_DP * ratio)
    textos = LINEAS_REALES[:lineas]
    anchos = [d.textlength(t, font=fuente) for t in textos]
    caja_w = round(max(anchos)) + 2 * padding
    caja_h = lineas * alto_linea + (lineas - 1) * gap + 2 * padding
    x0, y1 = offset, im.height - offset
    y0 = y1 - caja_h
    # El velo de la marca: `emergency.veil.base` es rgba(0, 0, 0, 0.55).
    d.rounded_rectangle((x0, y0, x0 + caja_w, y1), radius=round(4 * ratio), fill=(0, 0, 0, 140))
    y = y0 + padding
    for t in textos:
        d.text((x0 + padding, y), t, font=fuente, fill=(255, 255, 255, 255))
        y += alto_linea + gap
    return im


def _derivar(im: Image.Image) -> Image.Image:
    """Por el camino REAL: el mismo `preparar` que rellena `FotoFila.jpeg`."""
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=92)
    d = fotos_mod.preparar(buf.getvalue())
    assert d.jpeg is not None, d.motivo
    return Image.open(io.BytesIO(d.jpeg)).convert("RGB")


def _region_que_cambio(sin_marca: Image.Image, con_marca: Image.Image) -> tuple[int, int, int, int]:
    """El rectángulo que ENCIERRA a todos los píxeles que la marca cambió."""
    diff = ImageChops.difference(sin_marca, con_marca).convert("L")
    caja = diff.point(lambda v: 255 if v >= UMBRAL_CAMBIO else 0).getbbox()
    assert caja is not None, "la marca no cambió ni un píxel: la medición sería vacua"
    return caja


#: El barrido. Cada fila es (ancho_dp, alto_dp, ratio, escala, líneas) de una captura
#: verosímil: teléfono estrecho y teléfono ancho, tres densidades, la escala tipográfica
#: de fábrica y el techo de la plataforma, y la marca con y sin la línea de retenidos.
_CAPTURAS = [
    pytest.param(360, 560, 2.0, 1.0, 5, id="teléfono estrecho · escala 1.0"),
    pytest.param(360, 560, 3.0, 1.3, 6, id="teléfono estrecho · escala 1.3 · retenidos"),
    pytest.param(411, 700, 2.625, 1.0, 6, id="teléfono medio · retenidos"),
    pytest.param(448, 780, 3.0, 2.0, 6, id="Pixel 8 Pro · escala 2.0 · retenidos"),
    pytest.param(320, 480, 2.0, 1.0, 6, id="el mínimo de Android (sw320dp)"),
]


@pytest.mark.parametrize(("ancho_dp", "alto_dp", "ratio", "escala", "lineas"), _CAPTURAS)
def test_el_tapado_CUBRE_todos_los_pixeles_que_la_marca_cambia(
    ancho_dp: int, alto_dp: int, ratio: float, escala: float, lineas: int
) -> None:
    """La guarda que pidió el integrador: se DERIVA qué región cambió la marca y se
    exige que el tapado la cubra entera. Si algún píxel cambiado quedara fuera, la
    fotografía no puede salir.
    """
    base = _captura(round(ancho_dp * ratio), round(alto_dp * ratio))
    limpia = _derivar(base)
    marcada = _derivar(_con_marca(base, ratio=ratio, escala=escala, lineas=lineas))
    assert limpia.size == marcada.size

    _, arriba, _, _ = _region_que_cambio(limpia, marcada)

    banda = alto_de_la_banda(marcada.width)
    if banda > marcada.height * (1.0 - MINIMO_VISIBLE):
        pytest.fail(
            f"con esta captura la banda ({banda} px) no cabe en {marcada.size}: la foto "
            "no saldría, y el barrido está midiendo un caso que no llega al proveedor"
        )
    techo_del_tapado = marcada.height - banda
    assert arriba >= techo_del_tapado, (
        f"la marca cambia píxeles desde la fila {arriba} y el tapado empieza en la "
        f"{techo_del_tapado}: quedarían {techo_del_tapado - arriba} filas con la marca "
        "a la vista. NO SE PUEDE MANDAR ESTA FOTOGRAFÍA."
    )


def test_el_suelo_de_ruido_del_JPEG_esta_por_debajo_del_umbral() -> None:
    """El control de no-vacuidad del umbral: si el re-encodado por sí solo moviera los
    píxeles más de `UMBRAL_CAMBIO`, la región medida arriba sería la imagen entera y la
    guarda pasaría por la razón equivocada."""
    base = _captura(720, 1120)
    una = _derivar(base)
    otra = _derivar(base)
    diff = ImageChops.difference(una, otra).convert("L")
    assert diff.getextrema()[1] < UMBRAL_CAMBIO, (
        f"el ruido del JPEG llega a {diff.getextrema()[1]} y el umbral es {UMBRAL_CAMBIO}"
    )


def test_el_tapado_DEJA_NEGRA_la_banda_entera() -> None:
    """Y lo que se pinta es opaco de verdad: no un velo, no un difuminado."""
    base = _captura(768, 1024)
    marcada = _con_marca(base, ratio=2.0, escala=1.0, lineas=6)
    buf = io.BytesIO()
    marcada.save(buf, format="JPEG", quality=92)
    derivada = fotos_mod.preparar(buf.getvalue())
    tapada = tapar_banda_forense(derivada.jpeg)
    assert tapada.ok, tapada.motivo

    im = Image.open(io.BytesIO(tapada.jpeg)).convert("L")
    banda = im.crop((0, im.height - tapada.alto_banda_px, im.width, im.height))
    _maximo, _media = _luminancia(banda)
    # MEDIDO: el resto que queda es el timbre del JPEG en el BORDE de la banda —a dos
    # filas ya baja a 11 y a ocho, a 0— y no el texto, que era blanco puro sobre un velo
    # al 55 %. Sin tapar, esta misma banda da máximo 255 y media del orden de 110.
    assert _maximo <= _TIMBRE_DEL_JPEG, f"la banda tapada conserva luminancia hasta {_maximo}"
    assert _media < 0.5, f"la banda tapada conserva una media de {_media:.2f}"
    arriba = im.crop((0, 0, im.width, im.height - tapada.alto_banda_px))
    assert _luminancia(arriba)[1] > 40, "se tapó la fotografía entera, no solo la banda"


# ── 3 · lo que no cabe, no sale ──────────────────────────────────────────────


def _derivada_de(ancho: int, alto: int, *, calidad: int = 92) -> bytes:
    buf = io.BytesIO()
    _captura(ancho, alto).save(buf, format="JPEG", quality=calidad)
    return buf.getvalue()


@pytest.mark.parametrize(
    ("ancho", "alto"),
    [
        pytest.param(1024, 1024, id="cuadrada"),
        pytest.param(1024, 600, id="apaisada"),
    ],
)
def test_una_captura_que_NO_deja_ver_nada_tras_el_tapado_no_sale(ancho: int, alto: int) -> None:
    """La app está fijada en vertical: una captura que no lo es no viene de esta cámara,
    y con ella la cuenta de la banda deja de estar acotada. No se manda y se dice."""
    tapada = tapar_banda_forense(_derivada_de(ancho, alto))
    assert not tapada.ok
    assert tapada.motivo == BANDA_NO_CABE


def test_una_derivada_TAN_COMPRIMIDA_que_el_tapado_la_engorda_no_sale() -> None:
    """El presupuesto de bytes se cobra sobre lo que VIAJA, así que una tapada más gorda
    que su original dejaría el peso de la petición sin cota. Medido: un JPEG de 1024 px
    guardado a calidad 5 no baja ni re-encodando al peldaño más bajo de la escalera."""
    tapada = tapar_banda_forense(_derivada_de(768, 1024, calidad=5))
    assert not tapada.ok
    assert tapada.motivo == NO_ADELGAZA


@pytest.mark.parametrize(
    "blob",
    [
        pytest.param(None, id="S3 caído: no hay blob"),
        pytest.param(b"", id="blob vacío"),
        pytest.param(b"\xff\xd8\xff" + b"basura" * 40, id="JPEG truncado"),
    ],
)
def test_lo_que_no_se_puede_abrir_para_taparlo_NO_sale(blob: bytes | None) -> None:
    tapada = tapar_banda_forense(blob)
    assert not tapada.ok and tapada.motivo == NO_LEGIBLE


def test_la_tapada_NUNCA_pesa_mas_que_la_impresa_ni_que_el_techo_por_foto() -> None:
    """El techo por foto no es redundante: un blob que pasa la verificación de derivada
    puede ser legítimo y pesar el triple de lo que `preparar` produce."""
    gorda = _derivada_de(768, 1024, calidad=100)
    assert len(gorda) > fotos_mod.MAX_BYTES_SALIDA, (
        "el fixture no es más gordo que el techo: la guarda sería vacua"
    )
    tapada = tapar_banda_forense(gorda)
    assert tapada.ok, tapada.motivo
    assert len(tapada.jpeg) <= min(len(gorda), fotos_mod.MAX_BYTES_SALIDA)


# ── 4 · y en el CUERPO HTTP real, decodificando el base64 ────────────────────


async def test_lo_que_VIAJA_en_el_cuerpo_lleva_la_banda_tapada() -> None:
    """La aserción que faltaba. La que había hacía `json.dumps(cuerpo)` y buscaba las
    cadenas del EXIF: con la imagen en base64 eso pasa SIEMPRE, con fuga o sin ella.
    Aquí se decodifica la imagen y se mira el píxel, que es donde vive la marca."""
    m = _con_danos(verdict_basis=BASIS)
    cuerpos: list[dict] = []

    def chat(request: httpx.Request) -> httpx.Response:
        cuerpos.append(json.loads(request.content))
        return httpx.Response(200, json=CHAT_CON_IMAGEN)

    out = await build_narrative(m, _ajustes(), transport=httpx.MockTransport(enrutar(chat)))
    assert out.provider == "openrouter", out.degraded_reason

    partes = cuerpos[0]["messages"][1]["content"]
    urls = [p["image_url"]["url"] for p in partes if p["type"] == "image_url"]
    assert urls, "no viajó ninguna imagen: la medición sería vacua"
    for url in urls:
        bytes_reales = base64.b64decode(url.split(",", 1)[1])
        im = Image.open(io.BytesIO(bytes_reales)).convert("L")
        banda = alto_de_la_banda(im.width)
        recorte = im.crop((0, im.height - banda, im.width, im.height))
        maximo, media = _luminancia(recorte)
        assert maximo <= _TIMBRE_DEL_JPEG and media < 0.5, (
            "la fotografía sale hacia el tercero SIN tapar la banda de la marca de agua"
        )
        # Y lo de ARRIBA llega intacto: el tapado no es un recorte encubierto. Se
        # contrasta contra la derivada que imprime el papel, no contra un umbral a ojo.
        impresa = Image.open(io.BytesIO(m.danos[0].fotos[0].jpeg)).convert("L")
        alto_util = im.height - banda
        diff = ImageChops.difference(
            im.crop((0, 0, im.width, alto_util)), impresa.crop((0, 0, im.width, alto_util))
        )
        assert diff.getextrema()[1] < UMBRAL_CAMBIO, (
            "lo que queda a la vista no es lo que imprime el papel"
        )


async def test_la_procedencia_registra_la_huella_de_LO_QUE_SALIO() -> None:
    """Con el tapado, la huella de lo impreso deja de ser la de lo que viaja. Se anotan
    las dos: la de lo enviado es la única verificable contra el tercero; la de lo impreso
    es la única que ata la transferencia a una fotografía del expediente."""
    m = _con_danos(verdict_basis=BASIS)
    cuerpos: list[dict] = []

    def chat(request: httpx.Request) -> httpx.Response:
        cuerpos.append(json.loads(request.content))
        return httpx.Response(200, json=CHAT_CON_IMAGEN)

    out = await build_narrative(m, _ajustes(), transport=httpx.MockTransport(enrutar(chat)))
    (huella,) = out.photos_sent
    assert huella.impreso == m.danos[0].fotos[0].sha256_impreso
    assert huella.enviado != huella.impreso, "la huella de lo enviado es la de lo impreso"

    url = next(
        p["image_url"]["url"]
        for p in cuerpos[0]["messages"][1]["content"]
        if p["type"] == "image_url"
    )
    import hashlib  # noqa: PLC0415 - local: solo para contrastar el cuerpo real

    enviado = hashlib.sha256(base64.b64decode(url.split(",", 1)[1])).hexdigest()
    assert huella.enviado == enviado, "la huella anotada no es la de los bytes que salieron"
    assert out.provenance()["photos_sent"] == [
        {"enviado": huella.enviado, "impreso": huella.impreso}
    ]


def test_una_foto_que_NO_se_puede_tapar_se_declara_en_los_hechos() -> None:
    """El hueco no desaparece: `fotos_no_adjuntas` lo cuenta, igual que el papel declara
    las fotografías que no imprime."""
    from takab_api.dictamen.model import FotoFila  # noqa: PLC0415
    from takab_api.narrative.redact import facts_from  # noqa: PLC0415
    from tests.dictamen.test_pdf import model  # noqa: PLC0415

    buena = _foto_fila(_foto_cruda(), "ev-0")
    cuadrada = FotoFila(
        evidence_id="ev-1",
        sha256_declarado="b" * 64,
        sha256_impreso="d" * 64,
        jpeg=_derivada_de(1024, 1024),
    )
    m = model(danos=[_dano([buena, cuadrada])], verdict_basis=BASIS)
    imagenes = imagenes_de(m)
    assert len(imagenes) == 1, "la cuadrada salió con la marca a la vista"
    d = facts_from(m, imagenes=imagenes).damage_reports[0]
    assert (d.fotos_adjuntas, d.fotos_no_adjuntas) == (1, 1)


def test_la_instruccion_le_DICE_al_modelo_que_la_franja_va_tapada() -> None:
    """Sin esto el modelo describe la franja negra como parte de la escena —«la imagen
    aparece parcialmente oscurecida»— en un documento que se firma."""
    texto = INSTRUCCION_FOTOS.lower()
    assert "franja" in texto and "tapada" in texto
    assert "no la describas" in texto
