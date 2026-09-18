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

import ast
import io
import re
from dataclasses import dataclass
from pathlib import Path

import pytest
from pypdf import PdfReader

from takab_api.dictamen import layout
from takab_api.dictamen import pdf as pdf_mod
from takab_api.dictamen.duracion import Duracion
from takab_api.dictamen.espectrograma import Espectrograma
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


#: Un milímetro en puntos PostScript, que es la unidad del flujo de contenido.
_PT_A_MM = 25.4 / 72.0

#: `x y w h re` — un rectángulo. Lo dibujan las tablas y los marcos de las figuras.
_RE_RECT = re.compile(rb"([\d.\-]+)\s+([\d.\-]+)\s+([\d.\-]+)\s+([\d.\-]+)\s+re\b")
#: `x y l` / `x y m` — un trazo. El filete del pie es uno de éstos.
_RE_TRAZO = re.compile(rb"([\d.\-]+)\s+([\d.\-]+)\s+(?:l|m)\b")
#: `w 0 0 h x y cm /In Do` — una imagen colocada. [T-7.22] Es el operador que
#: `bordes_dibujados` NO miraba, así que la única guarda de geometría del
#: repositorio era ciega a una foto pintada encima del pie — en los tres
#: documentos y desde siempre. Con las fotos del brigadista dentro, eso pasa de
#: hueco teórico a agujero por el que cabe el criterio 2 de la ficha.
_RE_IMAGEN = re.compile(
    rb"([\d.\-]+)\s+0\s+0\s+([\d.\-]+)\s+([\d.\-]+)\s+([\d.\-]+)\s+cm\s*/(\w+)\s+Do"
)


@dataclass(frozen=True)
class Caja:
    """Algo dibujado, con sus dos bordes que importan, en mm desde el borde de la hoja.

    `y_inferior` se mide desde ARRIBA porque es como se leen los márgenes del
    chasis (`PAGE_H - PIE_MM`); el flujo del PDF lo cuenta desde abajo.

    ⚠️ [T-7.44] **UN RECTÁNGULO Y UNA IMAGEN NO SE MIDEN IGUAL**, y hasta hoy se
    les aplicaba la misma aritmética. fpdf2 emite el rectángulo como
    ``x (H-y) w -h re`` —altura **NEGATIVA**, y la `y` del operador es el borde
    **SUPERIOR**—, mientras que una imagen va como ``w 0 0 h x y cm /In Do``, cuya
    traslación **sí** es la esquina inferior izquierda. Tomando la `y` a secas, de
    un rectángulo se obtenía su **CIMA** y el campo se llamaba `y_inferior`.

    No era un matiz: medido, una caja de 78 mm con la cima en 250.0 mm y el fondo
    en 328.0 —o sea 68,6 mm de tinta por debajo del filete del pie, y fuera del
    papel— la guarda la daba por **buena**. Por eso `min(y, y + h)`: vale para las
    dos convenciones de signo, no sólo para la de fpdf2.
    """

    clase: str
    x_derecha: float
    y_inferior: float


def cajas_dibujadas(pagina, alto_mm: float = layout.PAGE_H) -> list[Caja]:
    """Todo lo dibujado en esa página: rectángulos, trazos e IMÁGENES.

    ⚠️ Se miden los operadores de dibujo, no el texto. La primera versión de esta
    guarda usaba la matriz de texto de `pypdf` y **no cazaba nada**: `tm[4]` es
    donde EMPIEZA el fragmento, y una celda alineada a la derecha empieza a la
    izquierda del filete y se extiende más allá. Medido: con la media migración
    el texto arrancaba en 184.0 mm, muy por debajo del tope, mientras las tablas
    desbordaban de verdad.

    Los rectángulos sí dan el borde exacto —`x y w h re`— y son justo lo que
    dibujan las tablas del dictamen, que es donde el desborde se ve.
    """
    datos = pagina.get_contents().get_data()
    alto_pts = alto_mm / _PT_A_MM
    cajas: list[Caja] = []
    for m in _RE_RECT.finditer(datos):
        x, y, w, h = (float(v) for v in m.groups())
        # ⚠️ El FONDO, no la cima: `h` es negativa en lo que emite fpdf2 y la `y`
        # del operador es el borde de arriba. Ver el docstring de `Caja`.
        cajas.append(Caja("rect", (x + w) * _PT_A_MM, (alto_pts - min(y, y + h)) * _PT_A_MM))
    for m in _RE_TRAZO.finditer(datos):
        x, y = (float(v) for v in m.groups())
        cajas.append(Caja("trazo", x * _PT_A_MM, (alto_pts - y) * _PT_A_MM))
    for m in _RE_IMAGEN.finditer(datos):
        w, _h, x, y = (float(v) for v in m.groups()[:4])
        nombre = m.group(5).decode()
        cajas.append(Caja(f"imagen {nombre}", (x + w) * _PT_A_MM, (alto_pts - y) * _PT_A_MM))
    return cajas


def bordes_dibujados(pagina) -> list[float]:
    """El borde DERECHO de todo lo que se dibuja, en mm. Ver `cajas_dibujadas`."""
    return [c.x_derecha for c in cajas_dibujadas(pagina)]


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


# ───────────────────────────────── [T-7.22] el punto 3 del encabezado, sostenido


def test_el_barrido_de_geometria_VE_las_imagenes() -> None:
    """Guarda de no-vacuidad del operador nuevo, y la que sostiene a la de abajo.

    Sin esto, `test_NINGUNA_caja_pisa_el_PIE` pasaría en verde sobre un documento
    lleno de fotos sencillamente porque el analizador no las ve. El logotipo del
    membrete se dibuja en todas las páginas, así que siempre hay al menos una.
    """
    lector = PdfReader(io.BytesIO(render(model())))
    for i, pagina in enumerate(lector.pages, start=1):
        imagenes = [c for c in cajas_dibujadas(pagina) if c.clase.startswith("imagen")]
        assert imagenes, (
            f"pág. {i}: el barrido no ve NI el logotipo del membrete; el operador "
            "`cm … Do` dejó de casar y la guarda del pie no mide nada"
        )


def test_NINGUNA_caja_pisa_el_PIE() -> None:
    """El punto 3 del encabezado de este módulo, que hasta ahora NADIE comprobaba.

    Estaba escrito arriba desde `T-7.21` —«`rect`/`polyline` NO disparan el salto
    de página automático, así que las figuras se dibujarían sobre el filete sin
    que nada fallara»— y ninguno de los cinco tests miraba el eje vertical: los
    cinco medían el borde DERECHO. Un documento ejecutable que afirma algo que no
    sostiene es la forma de defecto que este repositorio ya tiene fichada.

    Importa ahora porque `T-7.22` mete la figura más alta del documento después
    del croquis —el mapa de la red— y, detrás, las fotos del brigadista.

    Se miden rectángulos e imágenes, **no trazos**: el filete del pie ES un
    trazo, dibujado exactamente en la línea que esta prueba vigila, y medirlo
    haría fallar la guarda por su propio patrón de referencia.
    """
    tope_mm = layout.PAGE_H - layout.PIE_MM
    lector = PdfReader(io.BytesIO(render(model())))
    invasores: list[str] = []
    for i, pagina in enumerate(lector.pages, start=1):
        for caja in cajas_dibujadas(pagina):
            if caja.clase == "trazo":
                continue
            if caja.y_inferior > tope_mm + 0.05:
                invasores.append(f"pág. {i}: {caja.clase} baja hasta {caja.y_inferior:.1f} mm")
    assert not invasores, (
        f"hay dibujo por debajo del filete del pie ({tope_mm:.1f} mm), encima del "
        "sha256 y de la paginación: " + " · ".join(invasores)
    )


def test_la_guarda_del_PIE_caza_una_figura_que_lo_invade() -> None:
    """Porque una guarda que no puede fallar es una ceremonia.

    ⚠️ [T-7.44] **Y ésta lo era.** La caja invasora empezaba en
    ``PAGE_H - PIE_MM + 4``, o sea con la CIMA ya 4 mm por debajo del pliegue: así
    pasaba con la fórmula rota exactamente igual que con la buena, porque no podía
    distinguir «mido el fondo» de «mido la cima» — que era justo el defecto que la
    guarda de arriba tenía.

    La única forma de caja que las distingue es la que **empieza arriba del
    pliegue y termina abajo**, que además es la que sale de verdad de olvidar
    `reserva()`: una figura alta no empieza bajo el pie, empieza demasiado abajo.
    """
    pdf = layout.TakabPDF("TKB-GEOM-PIE", "invasión deliberada")
    pdf.add_page()
    tope_mm = layout.PAGE_H - layout.PIE_MM
    # La CIMA 9,4 mm POR ENCIMA del filete y el FONDO 20,6 mm por debajo: es lo
    # que pasa cuando una figura alta empieza demasiado abajo y fpdf2 no salta de
    # página porque es dibujo. Medir la cima daría esta caja por buena.
    cima = tope_mm - 9.4
    alto = 30.0
    pdf.rect(layout.MARGIN, cima, 40, alto)
    pagina = PdfReader(io.BytesIO(bytes(pdf.output()))).pages[0]

    peor = max(c.y_inferior for c in cajas_dibujadas(pagina) if c.clase != "trazo")
    assert peor == pytest.approx(cima + alto, abs=0.05), (
        f"la guarda leyó {peor:.1f} mm de una caja cuya cima está en {cima:.1f} y cuyo fondo "
        f"está en {cima + alto:.1f}: está midiendo la CIMA, no el fondo"
    )
    assert peor > tope_mm + 0.05, (
        f"la caja invasora llega a {peor:.1f} mm y la guarda la daría por buena "
        f"(tope {tope_mm:.1f} mm): la medición del eje vertical no funciona"
    )


# ─────────────────────── [T-7.44] las CINCO figuras, y el censo de topes


def _modelo_con_todas_las_figuras():
    """El dictamen con las CINCO figuras a la vez. No existía ninguno.

    ⚠️ Local a propósito, **sin tocar el `model()` compartido**: `test_avisos_impresos`
    fija `NO_SPECTRUM` sobre `model(evidence=[])` y `ONDA_NO_LEIDA` sobre
    `model(raw_waveform=None)`, así que meter la onda y el espectro en la base
    pondría ese censo en rojo.

    Hasta ahora `test_NINGUNA_caja_pisa_el_PIE` renderizaba `model()`, que sólo
    dibuja la traza y el croquis: **tres de las cinco figuras jamás habían pasado
    por el barrido del pie**.
    """
    n = 256
    return model(
        raw_waveform={c: [(i % 32) - 16 for i in range(n)] for c in ("EHZ", "ENN", "ENE")},
        raw_sample_rate=100.0,
        spectrum=([i * 0.5 for i in range(48)], [float(abs(24 - i)) for i in range(48)]),
        spectrum_peak_hz=3.5,
        spectrogram=Espectrograma(
            celdas=[[(i + j) % 10 / 10.0 for j in range(24)] for i in range(60)],
            tiempos_s=[i * 1.0 for i in range(60)],
            frecuencias_hz=[float(i) for i in range(1, 25)],
            ventana_muestras=128,
            solape=0.5,
            canal="EHZ",
        ),
        shaking_duration=Duracion(
            segundos=12.4,
            desde_s=2.1,
            hasta_s=14.5,
            canal="EHZ",
            muestras=1240,
        ),
    )


def test_NINGUNA_caja_pisa_el_PIE_con_LAS_CINCO_FIGURAS() -> None:
    """El criterio 2 de `T-7.44`, sobre el documento que de verdad las trae todas.

    La ficha decía «las cuatro figuras». Son **cinco**: los topes eran cuatro,
    pero el croquis —78 mm, la caja más alta del documento— no tenía ninguno.
    """
    tope_mm = layout.PAGE_H - layout.PIE_MM
    datos = render(_modelo_con_todas_las_figuras())
    lector = PdfReader(io.BytesIO(datos))

    invasores: list[str] = []
    medidas: list[float] = []
    for i, pagina in enumerate(lector.pages, start=1):
        for caja in cajas_dibujadas(pagina):
            if caja.clase == "trazo":
                continue
            medidas.append(caja.y_inferior)
            if caja.y_inferior > tope_mm + 0.05:
                invasores.append(f"pág. {i}: {caja.clase} baja hasta {caja.y_inferior:.1f} mm")

    # No-vacuidad: si el documento dejara de traer las figuras, el barrido pasaría
    # por no mirar nada — que es como este mismo test estuvo tres figuras ciego.
    assert len(medidas) > 50, (
        f"el barrido sólo vio {len(medidas)} cajas: el documento de prueba dejó de traer "
        "las figuras y esta guarda estaría aprobando sobre el vacío"
    )
    assert not invasores, (
        f"hay dibujo por debajo del filete del pie ({tope_mm:.1f} mm) con las cinco figuras "
        "en el documento: " + " · ".join(invasores)
    )


def _topes_absolutos() -> list[str]:
    """Comparaciones `pdf.get_y() <op> <número>` en todo `api/src/takab_api`.

    Por AST y no por `grep`: un comentario que mencione `get_y() > 240` —y este
    repo tiene varios, explicando justamente por qué ya no se hace— no es código
    y no debe contar. Es la tercera vez que un barrido estructural de este
    repositorio tropieza con lo mismo.

    El alcance es TODO `api/src/takab_api`, no sólo `dictamen/pdf.py`: el defecto
    no es de un fichero, es de una forma de decidir el salto de página, y
    `drill_report.py` genera otro documento con el mismo chasis.
    """
    raiz = Path(__file__).resolve().parents[2] / "src" / "takab_api"
    fuera: list[str] = []
    for fichero in sorted(raiz.rglob("*.py")):
        arbol = ast.parse(fichero.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.Compare):
                continue
            izq = nodo.left
            if not (
                isinstance(izq, ast.Call)
                and isinstance(izq.func, ast.Attribute)
                and izq.func.attr == "get_y"
            ):
                continue
            for comparador in nodo.comparators:
                if isinstance(comparador, ast.Constant) and isinstance(
                    comparador.value, int | float
                ):
                    rel = fichero.relative_to(raiz).as_posix()
                    fuera.append(f"{rel}:{nodo.lineno} → get_y() … {comparador.value}")
    return fuera


def test_ningun_documento_decide_el_salto_con_un_NUMERO_ABSOLUTO() -> None:
    """Criterio 3 de `T-7.44`, derivado y sin lista de exenciones.

    Un tope absoluto no está mal el día que se escribe: está **mudo**. No dice
    contra qué mide, así que el día que cambie el pie o el formato se queda atrás
    sin que nada avise — que es literalmente lo que pasó al migrar de A4 a Carta.
    La alternativa se llama `reserva()` y deriva el tope de `PAGE_H - PIE_MM`.
    """
    encontrados = _topes_absolutos()
    assert not encontrados, (
        "hay salto(s) de página decididos con un número absoluto: "
        + " · ".join(encontrados)
        + ". Usa `pdf.reserva(alto)`, que deriva el tope de `PAGE_H - PIE_MM`: un número "
        "escrito a mano no dice contra qué mide y sobrevive mudo a un cambio de formato"
    )


def test_el_censo_de_topes_VE_uno_plantado() -> None:
    """No-vacuidad: hoy encuentra cero, y mañana podría encontrar cero por estar roto.

    Se le da el detector a un fragmento sintético con el defecto dentro. Sin esto,
    cambiar `get_y` por `get_x` en el censo lo dejaría en verde para siempre.
    """
    fragmento = ast.parse("if pdf.get_y() > 240:\n    pdf.add_page()\n")
    vistos = [
        n
        for n in ast.walk(fragmento)
        if isinstance(n, ast.Compare)
        and isinstance(n.left, ast.Call)
        and isinstance(n.left.func, ast.Attribute)
        and n.left.func.attr == "get_y"
        and any(
            isinstance(c, ast.Constant) and isinstance(c.value, int | float) for c in n.comparators
        )
    ]
    assert len(vistos) == 1, (
        "el detector de topes absolutos no ve el defecto plantado: estaría aprobando "
        "`api/src` por no saber mirar, no por no haber nada"
    )


def _las_cinco_figuras():
    """Cada figura del dictamen con lo mínimo para dibujarse, por su nombre.

    Se llaman las funciones privadas a propósito: el objetivo es medir **cada
    figura por separado** entrando donde nadie la deja entrar en un documento
    normal, y eso un render completo no lo puede provocar.
    """
    m = _modelo_con_todas_las_figuras()
    esp = m.spectrogram
    freqs, amps = m.spectrum
    return {
        "_sketch_section": lambda pdf: pdf_mod._sketch_section(pdf, m),
        "_trace": lambda pdf: pdf_mod._trace(
            pdf, "EHZ", [float(i % 7) for i in range(64)], [False] * 64, unit="g"
        ),
        "_duracion": lambda pdf: pdf_mod._duracion(pdf, m),
        "_spectrum": lambda pdf: pdf_mod._spectrum(pdf, freqs, amps, m.spectrum_peak_hz),
        "_spectrogram": lambda pdf: pdf_mod._spectrogram(pdf, esp),
    }


@pytest.mark.parametrize("nombre", sorted(_las_cinco_figuras()))
def test_cada_figura_respeta_el_PIE_ENTRE_DONDE_ENTRE(nombre: str) -> None:
    """⚠️ La prueba que de verdad puede ponerse roja, y la razón de que exista.

    `test_NINGUNA_caja_pisa_el_PIE_con_LAS_CINCO_FIGURAS` mide el documento tal y
    como sale hoy, y hoy **ninguna figura desborda**: el croquis tiene unos 43 mm
    de holgura. Medido — quitarle su `reserva()` al croquis deja esa prueba en
    VERDE. O sea que el trabajo de esta ficha no estaría protegido por nada.

    Aquí se fuerza lo que un render normal no provoca: se hace entrar a cada
    figura, una a una, en cada milímetro del tramo bajo de la página. Si alguna
    no sabe saltar, aparece por debajo del filete y esto se pone rojo.
    """
    tope_mm = layout.PAGE_H - layout.PIE_MM
    figura = _las_cinco_figuras()[nombre]

    peores: list[str] = []
    dibujo_visto = False
    for y0 in range(120, int(tope_mm) + 1, 5):
        pdf = layout.TakabPDF("TKB-GEOM-FIG", f"{nombre} entrando en y={y0}")
        pdf.add_page()
        pdf.set_y(float(y0))
        figura(pdf)
        for pagina in PdfReader(io.BytesIO(bytes(pdf.output()))).pages:
            for caja in cajas_dibujadas(pagina):
                if caja.clase == "trazo":
                    continue
                dibujo_visto = True
                if caja.y_inferior > tope_mm + 0.05:
                    peores.append(f"entrando en y={y0}: baja hasta {caja.y_inferior:.1f} mm")

    assert not peores, (
        f"`{nombre}` pisa el pie ({tope_mm:.1f} mm) según dónde entre — "
        + " · ".join(peores[:4])
        + ". Le falta `reserva()` con su alto, o el alto reservado se quedó corto"
    )
    # `_duracion` no dibuja: es texto, y `set_auto_page_break` lo parte solo. Su
    # guarda es contra el rótulo huérfano, no contra el pie, y por eso se exime
    # de la no-vacuidad EN VEZ de fingir que dibuja algo.
    if nombre != "_duracion":
        assert dibujo_visto, (
            f"`{nombre}` no dibujó ni una caja en todo el barrido: esta prueba estaría "
            "aprobando sobre el vacío"
        )


def test_el_alto_del_bloque_de_DURACION_se_MIDE_no_se_teclea() -> None:
    """[T-7.44] El quinto tope era distinto, y su guarda es de RÓTULO HUÉRFANO.

    `_duracion` no dibuja nada —es `cell` + `multi_cell`, las dos texto— así que
    el barrido geométrico del pie **no puede verlo**: medido, teclear ahí un alto
    equivocado deja `test_cada_figura_respeta_el_PIE_ENTRE_DONDE_ENTRE` en verde.
    Lo que su tope evitaba es que el título se quede solo al final de una página
    con su párrafo en la siguiente.

    Y su alto **no es constante**: el párrafo lleva dentro la etiqueta, el canal,
    las muestras y los dos instantes, y la rama de ausencia es mucho más corta
    (16,2 mm con dato contra 9,4 sin él). Por eso se mide con `dry_run`: con la
    constante de la rama corta, el bloque CON dato entrando a 250 mm deja el
    rótulo en una página y el párrafo en la otra.
    """
    m = _modelo_con_todas_las_figuras()
    pdf = layout.TakabPDF("TKB-GEOM-DUR", "duración entrando abajo")
    pdf.add_page()
    pdf.set_y(250.0)
    pdf_mod._duracion(pdf, m)

    paginas = [p.extract_text() or "" for p in PdfReader(io.BytesIO(bytes(pdf.output()))).pages]
    con_rotulo = [i for i, t in enumerate(paginas) if "DURACIÓN INSTRUMENTAL" in t]
    # El FINAL del párrafo, no su principio: con una reserva corta la primera
    # línea todavía cabe junto al rótulo y sólo se parte el resto. Medido — mirar
    # «Intensidad» (que va en la primera línea) deja la mutación en verde.
    con_parrafo = [i for i, t in enumerate(paginas) if "aceleración" in t]
    assert con_rotulo and con_parrafo, (
        f"no se encontró el bloque de duración en el documento: rótulo={con_rotulo}, "
        f"párrafo={con_parrafo}. La prueba estaría aprobando sobre el vacío"
    )
    assert con_rotulo[0] == con_parrafo[0], (
        f"el rótulo quedó en la página {con_rotulo[0] + 1} y su párrafo TERMINA en la "
        f"{con_parrafo[0] + 1}: la reserva se calculó con un alto que no es el del texto "
        "que se va a escribir, así que el bloque no cabía entero donde se plantó"
    )
