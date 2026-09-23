"""[T-7.22] Las fotografías del brigadista LLEGAN al papel, y caen donde deben.

El espía de texto es ciego a las imágenes: una fotografía que no se embebe, o que
se pinta encima del pie, pasa todas las suites de render en verde. Esto es la otra
mitad.

## El criterio de la meta de F4 estaba VACÍO tal como se escribió

«pypdf cuenta ≥ 4 imágenes». MEDIDO **antes** de esta ficha: el dictamen técnico
daba `3 páginas → 3 imágenes` sin una sola fotografía, porque `page.images` cuenta
referencias de recurso **por página** y el logotipo del membrete sale en todas. Un
dictamen de cuatro páginas lo habría cumplido con cero fotos. Eso es «un verde que
no significa bien, sino no sé».

Aquí se cuenta de dos formas que no pueden engañarse igual:

1. **Por `/DCTDecode`**, el filtro de un flujo JPEG. MEDIDO: el dictamen de hoy
   tiene **cero** —su única imagen es el logotipo, que es PNG/Flate—, así que hoy
   ese contador es un censo de fotografías exacto, y su no-vacuidad es
   demostrable con el documento sin fotos.
2. **Por identidad DECLARADA**: cada fotografía que el modelo enumera con bytes
   tiene su XObject, o su ausencia impresa. Es lo que impide que el criterio se
   ponga rojo porque un brigadista subió dos veces la misma foto —fpdf2 cachea por
   contenido y las colapsaría en un XObject, sin que eso sea un defecto—.
"""

from __future__ import annotations

import hashlib
import io

import pytest
from PIL import Image
from pypdf import PdfReader

from takab_api.dictamen import layout
from takab_api.dictamen import pdf as pdf_mod
from takab_api.dictamen.model import DanoFila, FotoFila
from takab_api.dictamen.pdf import render
from takab_api.documentos.fotos import SIN_BLOB, preparar
from tests.dictamen.test_pdf import _OPENED, model
from tests.documentos.cajas_de_texto import Capturadas, cajas_impresas
from tests.documentos.espia import espia_del_render
from tests.documentos.test_geometria import cajas_dibujadas


def _jpeg(semilla: int, w: int = 1600, h: int = 1200) -> bytes:
    """Una fotografía sintética REPRODUCIBLE y distinta por semilla."""
    im = Image.new("RGB", (w, h), (120, 90, 60))
    px = im.load()
    for y in range(0, h, 4):
        for x in range(0, w, 4):
            px[x, y] = ((x * semilla) % 256, (y * 13) % 256, (x + y + semilla) % 256)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _foto(semilla: int, *, declarada_mal: bool = False) -> FotoFila:
    crudo = _jpeg(semilla)
    d = preparar(crudo)
    medido = hashlib.sha256(crudo).hexdigest()
    return FotoFila(
        evidence_id=f"{semilla:08d}-aaaa-bbbb-cccc-dddddddddddd",
        sha256_declarado="f" * 64 if declarada_mal else medido,
        sha256_medido=medido,
        sha256_impreso=d.sha256,
        ancho=d.ancho,
        alto=d.alto,
        jpeg=d.jpeg,
    )


def _dano(fotos: list[FotoFila], **over) -> DanoFila:
    base = {
        "report_id": "d-1",
        "rol": "brigadista",
        "zona": "Nivel 3",
        "categorias": [{"key": "grieta", "severity": "alta"}],
        "personas_en_riesgo": False,
        "notas": None,
        "ts": _OPENED,
        "fotos": fotos,
        "fotos_omitidas": 0,
    }
    return DanoFila(**{**base, **over})


def _con_cuatro_fotos() -> bytes:
    return render(model(danos=[_dano([_foto(i) for i in (3, 5, 7, 11)])]))


# ───────────────────────────────────── la no-vacuidad, que es la mitad del censo


def test_el_dictamen_SIN_fotos_no_tiene_NINGUN_jpeg() -> None:
    """Lo que hace que contar `/DCTDecode` sea un censo de fotografías y no un número.

    MEDIDO: la única imagen del documento sin daños es el logotipo del membrete, y
    es PNG/Flate. Si algún día el logotipo pasara a JPEG, este test se pone rojo y
    el de abajo deja de significar lo que dice — que es exactamente cuándo hay que
    enterarse.
    """
    pdf = render(model(danos=[]))
    assert pdf.count(b"/DCTDecode") == 0, (
        "el documento sin fotografías ya trae un flujo JPEG: contar `/DCTDecode` "
        "deja de ser un censo de las fotos del brigadista"
    )
    # Y sí trae el logotipo, o el contraste de arriba no probaría nada.
    lector = PdfReader(io.BytesIO(pdf))
    assert any(p.images for p in lector.pages), "el documento no lleva ni el logotipo"


# ──────────────────────────────────────────── el criterio de F4, hecho de verdad


def test_CUATRO_fotografias_llegan_al_papel_como_JPEG() -> None:
    """El criterio de la meta de F4, contando lo que pretende contar.

    No es `sum(len(p.images))`: eso cuenta el logotipo una vez por página y lo
    cumpliría un documento de cuatro páginas sin una sola fotografía.
    """
    pdf = _con_cuatro_fotos()
    assert pdf.count(b"/DCTDecode") == 4, (
        f"se embebieron {pdf.count(b'/DCTDecode')} flujos JPEG y el reporte traía 4"
    )


def test_cada_foto_DECLARADA_tiene_su_XObject() -> None:
    """Por identidad, no por número.

    fpdf2 cachea las imágenes por contenido: si un brigadista sube dos veces la
    misma fotografía, las dos colapsan en UN XObject — y eso no es un defecto. Un
    criterio de «≥ N imágenes distintas» se pondría rojo por ello. Lo que sí tiene
    que cumplirse es que cada fotografía enumerada esté, o diga por qué no.
    """
    fotos = [_foto(i) for i in (3, 5, 7, 11)]
    lector = PdfReader(io.BytesIO(render(model(danos=[_dano(fotos)]))))
    distintos = {i.indirect_reference.idnum for p in lector.pages for i in p.images}
    # +1 por el logotipo del membrete, que se embebe una sola vez y se reutiliza.
    assert len(distintos) == len(fotos) + 1, (
        f"{len(distintos)} XObjects para {len(fotos)} fotografías más el logotipo"
    )


def test_dos_fotos_IDENTICAS_no_ponen_el_censo_rojo() -> None:
    """El lado que un «≥ 4 distintas» habría roto sin que hubiera defecto."""
    repetida = _foto(3)
    pdf = render(model(danos=[_dano([repetida, _foto(5), repetida])]))
    lector = PdfReader(io.BytesIO(pdf))
    distintos = {i.indirect_reference.idnum for p in lector.pages for i in p.images}
    assert len(distintos) == 3, f"dos copias de la misma foto dieron {len(distintos)} XObjects"


# ─────────────────────────────────────────────── dónde caen, no solo si están


def test_NINGUNA_fotografia_pisa_el_PIE_ni_se_sale_del_filete() -> None:
    """`pdf.image()` NO dispara el salto de página de fpdf2, igual que `rect`.

    Sin `reserva()` antes de cada fila, una fotografía se pinta sobre el sha256 y
    la paginación — y hasta `T-7.22` la guarda de geometría ni siquiera sabía leer
    el operador de imagen, así que no podía verlo en ninguno de los documentos.
    """
    lector = PdfReader(io.BytesIO(_con_cuatro_fotos()))
    tope_abajo = layout.PAGE_H - layout.PIE_MM
    tope_derecha = layout.PAGE_W - layout.MARGIN
    vistas = 0
    for i, pagina in enumerate(lector.pages, start=1):
        for caja in cajas_dibujadas(pagina):
            if not caja.clase.startswith("imagen"):
                continue
            vistas += 1
            assert caja.y_inferior <= tope_abajo + 0.05, (
                f"pág. {i}: {caja.clase} baja hasta {caja.y_inferior:.1f} mm "
                f"y el filete del pie está en {tope_abajo:.1f} mm"
            )
            assert caja.x_derecha <= tope_derecha + 0.05, (
                f"pág. {i}: {caja.clase} llega a {caja.x_derecha:.1f} mm"
            )
    assert vistas >= 5, f"el barrido solo vio {vistas} imágenes colocadas: no mide nada"


# ────────────────────────────────────────── lo que el papel DICE de cada foto


def test_el_pie_de_foto_lleva_las_TRES_huellas() -> None:
    """Imprimir sólo la del original junto a píxeles que NO son ese original
    convierte «verifique el sha256» en falso — el defecto de `T-5.26`."""
    foto = _foto(3)
    with espia_del_render() as cap:
        render(model(danos=[_dano([foto])]))
    seccion = cap.seccion("DAÑOS REPORTADOS EN CAMPO")
    assert foto.sha256_declarado in seccion
    assert foto.sha256_impreso in seccion
    assert "DERIVADA SIN METADATOS" in seccion, (
        "el papel no dice que lo impreso es una derivada: el lector creería que "
        "el hash de arriba es el de estos píxeles"
    )
    assert "coincide con la declarada" in seccion


def test_un_DESAJUSTE_de_huella_se_grita() -> None:
    """`evidence_objects.sha256` es lo que DECLARÓ el dispositivo y el servidor
    nunca verificó. Medirlo aquí es gratis —los bytes hay que bajarlos igual— y un
    desajuste es lo más importante que esta sección puede decir de una fotografía
    de evidencia."""
    with espia_del_render() as cap:
        render(model(danos=[_dano([_foto(3, declarada_mal=True)])]))
    seccion = cap.seccion("DAÑOS REPORTADOS EN CAMPO")
    assert "NO COINCIDE CON LA DECLARADA" in seccion


def test_una_foto_AUSENTE_se_declara_con_su_motivo() -> None:
    """Y con su identificador, para poder buscarla en el expediente."""
    fantasma = FotoFila(
        evidence_id="99999999-aaaa-bbbb-cccc-dddddddddddd",
        sha256_declarado="a" * 64,
        motivo=SIN_BLOB,
    )
    with espia_del_render() as cap:
        render(model(danos=[_dano([fantasma])]))
    seccion = cap.seccion("DAÑOS REPORTADOS EN CAMPO")
    assert "NO IMPRESA" in seccion
    assert SIN_BLOB in seccion
    assert "99999999" in seccion


# ─────────────────────────────────────────────────────────── el determinismo


def test_el_documento_CON_fotos_sigue_siendo_determinista() -> None:
    """La promesa que sostiene «verifique el sha256», con el codificador JPEG dentro."""
    assert _con_cuatro_fotos() == _con_cuatro_fotos()


def test_la_huella_de_CONTENIDO_cambia_con_las_fotografias() -> None:
    """Sin la huella de la derivada dentro del modelo, dos informes del mismo
    incidente con fotografías DISTINTAS imprimirían el MISMO «SHA-256 DEL
    CONTENIDO» en el pie — y es justo el número que el documento manda verificar.

    Los bytes no entran crudos en esa huella (`documentos/huella.para_la_huella`);
    su sha256 sí, y
    esto es lo que lo demuestra.
    """
    a = model(danos=[_dano([_foto(3)])])
    b = model(danos=[_dano([_foto(5)])])
    assert a.content_sha256() != b.content_sha256()


def test_la_huella_de_CONTENIDO_no_arrastra_los_bytes() -> None:
    """Se calcula al menos dos veces por documento (portada y pie).

    Con los bytes crudos dentro, cada llamada serializaría megabytes de `repr`. Se
    comprueba sobre el payload, no cronometrando: una prueba de tiempo en CI es
    una prueba intermitente.
    """
    from takab_api.documentos.huella import payload_de_la_huella

    # ⚠️ [T-7.43] Esto reconstruía la receta a mano con `asdict` para poder mirar el
    # payload, así que vigilaba una COPIA: una regresión en la receta de verdad —por
    # ejemplo cambiar `asdict` por `getattr` campo a campo, que mete 2.2 MB de JPEG
    # crudo— habría dejado este test en verde. Ahora llama a la receta.
    m = model(danos=[_dano([_foto(i) for i in (3, 5, 7, 11)])])
    payload = payload_de_la_huella(m)
    assert "\\\\x" not in payload, "los bytes de las fotografías se colaron en la huella"
    assert payload.count("<") >= 4, "las fotografías no dejaron su marca de tamaño"
    # Y la huella de cada derivada SÍ está: es lo que hace que el hash cambie.
    for foto in m.danos[0].fotos:
        assert foto.sha256_impreso in payload


# ─────────────────── [T-8.12 · A-050 · A-051] nada se imprime ENCIMA de otra cosa
#
# Hasta aquí todo se probaba con CUATRO fotos APAISADAS: número par y proporción
# 4:3. Los dos defectos vivían justo fuera de ese caso:
#
# * **A-050** — con UNA foto (o con la última de un número impar) el pie de foto
#   se escribía con `new_y=TOP` y el cursor volvía ARRIBA del pie: el reporte
#   siguiente, o el título «15. EVACUACIÓN OBSERVADA (CCTV)», se imprimía encima
#   de las huellas. Es el 100 % de los incidentes reales con una foto.
# * **A-051** — una foto de teléfono en VERTICAL (3:4) sale a 768×1024 y se
#   imprimía a 88×117 mm con una reserva de 98. `pdf.image()` no salta de
#   página, así que según dónde empezara la fila la foto bajaba sobre el pie.
#
# Ninguna guarda podía verlo: la de geometría mide operadores de DIBUJO y es
# ciega al texto a propósito. `tests/documentos/cajas_de_texto.py` mide cada
# renglón en el punto por el que pasa todo el texto de fpdf2.


def _retrato(semilla: int) -> FotoFila:
    """Una foto de teléfono en VERTICAL, 1200×1600: la que desbordaba (A-051)."""
    crudo = _jpeg(semilla, w=1200, h=1600)
    d = preparar(crudo)
    medido = hashlib.sha256(crudo).hexdigest()
    return FotoFila(
        evidence_id=f"{semilla:08d}-aaaa-bbbb-cccc-dddddddddddd",
        sha256_declarado=medido,
        sha256_medido=medido,
        sha256_impreso=d.sha256,
        ancho=d.ancho,
        alto=d.alto,
        jpeg=d.jpeg,
    )


def test_la_guarda_de_SOLAPES_de_texto_caza_uno_plantado() -> None:
    """No-vacuidad: dos renglones en el mismo sitio TIENEN que verse.

    Sin esto, un espía que dejara de capturar —otra versión de fpdf2, otro
    nombre del método— dejaría en verde todas las pruebas de abajo.
    """
    with cajas_impresas() as cap:
        pdf = layout.TakabPDF("TKB-SOLAPE", "solape deliberado")
        pdf.add_page()
        pdf.set_font(pdf.body_font, "", 10)
        pdf.set_xy(layout.MARGIN, 120)
        pdf.cell(80, 5, pdf.text_of("15. EVACUACIÓN OBSERVADA (CCTV)"))
        pdf.set_xy(layout.MARGIN, 121)
        pdf.cell(80, 5, pdf.text_of("IMPRESA 0123456789abcdef"))
        pdf.output()
    assert Capturadas.solapes(cap.desde("15. EVACUACIÓN")), "la guarda no ve un solape plantado"


@pytest.mark.parametrize(
    ("fotos", "caso"),
    [
        (lambda: [_foto(3)], "una foto apaisada"),
        (lambda: [_foto(3), _foto(5), _foto(7)], "tres apaisadas (impar)"),
        (lambda: [_foto(i) for i in (3, 5, 7, 11)], "cuatro apaisadas (par)"),
        (lambda: [_retrato(3)], "una en vertical"),
        (lambda: [_retrato(3), _retrato(5), _retrato(7)], "tres en vertical"),
    ],
)
def test_NADA_se_imprime_encima_de_otra_cosa_desde_los_DANOS(fotos, caso: str) -> None:  # noqa: ANN001
    """Texto contra texto y texto contra foto, desde el título de la §14 al final."""
    with cajas_impresas() as cap:
        render(model(danos=[_dano(fotos()), _dano([_foto(13)], report_id="d-2")]))
    desde = cap.desde("DAÑOS REPORTADOS EN CAMPO")
    assert sum(1 for c in desde if c.clase == "imagen") >= 2, "el barrido no vio las fotos"
    solapes = Capturadas.solapes(desde)
    assert not solapes, f"con {caso}, se imprime encima de otra cosa: " + " · ".join(
        f"pág. {a.pagina} «{a.texto[:30] or a.clase}» ↔ «{b.texto[:30] or b.clase}»"
        for a, b in solapes[:4]
    )


def test_una_foto_en_VERTICAL_cabe_en_la_misma_caja_que_una_apaisada() -> None:
    """Encajada en 88×88 mm conservando la proporción: nunca 117 mm de alto."""
    with cajas_impresas() as cap:
        render(model(danos=[_dano([_retrato(3), _foto(5)])]))
    fotos = [c for c in cap.imagenes if c.x1 - c.x0 > 40]
    assert len(fotos) == 2
    for c in fotos:
        assert c.y1 - c.y0 <= pdf_mod._FOTO_W + 0.05, f"una foto mide {c.y1 - c.y0:.1f} mm de alto"
        assert c.x1 - c.x0 <= pdf_mod._FOTO_W + 0.05
    retrato = fotos[0]
    proporcion = (retrato.y1 - retrato.y0) / (retrato.x1 - retrato.x0)
    assert proporcion == pytest.approx(1024 / 768, rel=0.01), "la foto se deformó al encajarla"


def test_las_fotos_respetan_el_PIE_ENTRE_DONDE_ENTREN() -> None:
    """El barrido de `test_geometria` para las figuras, hecho aquí con fotos reales.

    Se hace entrar la fila de fotos —en vertical, que es la más alta, y con un
    desajuste de huella, que alarga el pie de foto a cinco renglones— en cada
    tramo de la mitad baja de la página. Ni la foto ni su pie pueden quedar por
    debajo del filete del pie de página.
    """
    tope = layout.PAGE_H - layout.PIE_MM
    dano = _dano([_retrato(3), _foto(5, declarada_mal=True), _retrato(7)])
    peores: list[str] = []
    vistas = 0
    for y0 in range(110, int(tope) + 1, 6):
        with cajas_impresas() as cap:
            pdf = layout.TakabPDF("TKB-FOTOS", f"fotos entrando en y={y0}")
            pdf.add_page()
            pdf.set_y(float(y0))
            pdf_mod._fotos_del_reporte(pdf, dano)
            pdf.output()
        for c in cap.cajas:
            # El membrete (cabecera y pie) se imprime FUERA del cuerpo a propósito.
            if c.clase == "texto" and (c.y0 < layout.CUERPO_Y - 0.5 or c.y0 >= tope):
                continue
            vistas += c.clase == "imagen"
            if c.y1 > tope + 0.05:
                peores.append(f"y={y0}: {c.clase} «{c.texto[:20]}» baja hasta {c.y1:.1f} mm")
    assert vistas >= 3, "el barrido no vio las fotos"
    assert not peores, "las fotos o su pie pisan el pie de página: " + " · ".join(peores[:4])
