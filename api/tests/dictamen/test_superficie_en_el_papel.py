"""[T-9.53 · D-44 · D-45] La §8 con la superficie ESTIMADA y la cartografía embebida.

Lo que se defiende, por lo que costaría equivocarse:

1. **La superficie se pinta DEBAJO de lo medido y rotulada como estimación.** La
   imagen se embebe en el rectángulo que resulta de proyectar su `bbox` con el
   MISMO croquis que sitúa los inmuebles: una imagen colocada «a ojo» sería una
   segunda escala en la misma figura.
2. **La §5 deriva de lo que la §8 imprime** (`D-44` enmienda a `NO_MMI`): con
   superficie impresa sale `MMI_ESTIMADA` y NO `NO_MMI`; sin ella, al revés. Las
   dos direcciones, porque una sola deja pasar el aviso que sale siempre.
3. **Sin superficie se dice por qué** (`superficie.MOTIVOS`), no se calla.
4. **Las atribuciones salen de `atribuciones.json`**, no escritas a mano, y sólo
   las de lo que se dibujó.
5. **Sin red**: la cartografía se lee del paquete; ni una petición.

Los bloques se construyen por la RUTA REAL —`calculo.calcula` + `superficie.estima`
→ `lectura.desde_mapa` → `builder.bloque_de_shakemap`— y no a mano: el defecto que
más ha costado en esta sección nació de fixtures escritas a mano.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

import fpdf
import pytest

from takab_api import geodatos
from takab_api.dictamen import pdf as pdf_mod
from takab_api.dictamen.builder import bloque_de_shakemap
from takab_api.dictamen.model import (
    LEYENDA_SUPERFICIE_ZONAS,
    MMI_ESTIMADA,
    NO_MMI,
    SHAKEMAP_A_DEMANDA,
    SHAKEMAP_NO_CALCULADO,
    SHAKEMAP_NO_LEIDO,
    SHAKEMAP_PENDIENTE,
    ShakemapBlock,
)
from takab_api.dictamen.pdf import MAPA_SACUDIDA, render
from takab_api.shakemap import calculo as shk
from takab_api.shakemap import gmice
from takab_api.shakemap import superficie as SUP
from takab_api.shakemap.lectura import desde_mapa
from tests.dictamen.test_pdf import model
from tests.documentos.espia import espia_del_render
from tests.shakemap.test_calculo import EPICENTRO as EPICENTRO_REF
from tests.shakemap.test_calculo import NIVELES as NIVELES_REF
from tests.shakemap.test_calculo import TOPE_KM as TOPE_REF
from tests.shakemap.test_calculo import _medida as _medida_ref

_CALCULADO = datetime(2026, 8, 3, 10, 5, 0, tzinfo=UTC)
_INC = "11111111-2222-3333-4444-555555555555"
#: Los umbrales por defecto del dictamen v2 (VERDE < 0.04 g, ROJO ≥ 0.10 g).
_UMBRALES = (0.04, 0.10)


def _mapa(*, calibrado_cdmx: bool = True) -> shk.Mapa:
    """Dos inmuebles: CDMX (calibrado, según el caso) y Puebla (sin calibrar)."""
    medidas = [
        _medida_ref(),
        _medida_ref(
            site_id="22222222-2222-2222-2222-222222222222",
            site_code="PUE-01",
            site_name="Planta Puebla",
            lat=19.0414,
            lon=-98.2063,
            dist_km=56.0,
            pga_g=0.012,
        ),
    ]
    mapa = shk.calcula(
        medidas,
        epicentro=EPICENTRO_REF,
        niveles=NIVELES_REF,
        cobertura_km=25.0,
        radio_max_km=TOPE_REF,
    )
    estaciones = [
        SUP.Estacion(lat=m.lat, lon=m.lon, pga_g=m.pga_g, calibrado=calibrado)
        for m, calibrado in zip(medidas, (calibrado_cdmx, False), strict=True)
    ]
    epi = EPICENTRO_REF
    sup, motivo = SUP.estima(
        estaciones, SUP.EpicentroLey(epi.lat, epi.lon, epi.depth_km, epi.magnitud)
    )
    return dataclasses.replace(mapa, superficie=sup, superficie_motivo=motivo)


def _bloque(*, calibrado_cdmx: bool = True, a_demanda: bool = False) -> ShakemapBlock:
    salida, malla = desde_mapa(_INC, _mapa(calibrado_cdmx=calibrado_cdmx), calculado_en=_CALCULADO)
    return bloque_de_shakemap(
        salida, "CDMX-01", malla=malla, umbrales=_UMBRALES, a_demanda=a_demanda
    )


def _capturado(bloque: ShakemapBlock):
    with espia_del_render() as cap:
        render(model(shakemap=bloque), "technical")
    return cap


# ───────────────────────────────────────── el bloque, por la ruta real


def test_el_bloque_lleva_la_superficie_su_cita_y_los_umbrales_del_sitio() -> None:
    b = _bloque()
    assert b.superficie is not None
    assert b.superficie.n_sensores == 2 and b.superficie.n_calibrados == 1
    assert b.superficie_motivo is None
    assert b.superficie_cita_mmi == gmice.CITA
    assert (b.banda_verde_max_g, b.banda_rojo_min_g) == _UMBRALES
    assert b.superficie_mmi_max == gmice.mmi_de_pga(b.superficie_pga_max_g)
    assert b.calculado_para_el_documento is False


def test_sin_calibrados_el_bloque_trae_el_MOTIVO_y_no_una_superficie() -> None:
    b = _bloque(calibrado_cdmx=False)
    assert b.superficie is None
    assert b.superficie_motivo == SUP.MOTIVO_SIN_CALIBRADOS


# ───────────────────────────────────────────── lo que el papel DICE


def test_con_superficie_la_leyenda_dice_ESTIMADO_N_y_M_bandas_zonas_y_MMI_maxima() -> None:
    b = _bloque()
    seccion = _capturado(b).seccion(MAPA_SACUDIDA)
    assert "ESTIMADO a partir de 2 sensores (1 calibrado)" in seccion
    assert "no observada" in seccion
    assert gmice.CITA in seccion, "la MMI estimada sale sin decir de qué relación"
    # Las tres bandas con SUS umbrales en g: los del sitio, no unos de la página.
    assert "VERDE < 0.040 g" in seccion
    assert "AMARILLO 0.040–0.100 g" in seccion
    assert "ROJO ≥ 0.100 g" in seccion
    assert LEYENDA_SUPERFICIE_ZONAS in seccion
    romano = gmice.romano(b.superficie_mmi_max)
    assert "MMI MÁXIMA ESTIMADA EN LA ZONA AJUSTADA" in seccion
    assert f"{romano} (estimada)" in seccion


def test_la_quinta_seccion_dice_MMI_ESTIMADA_con_superficie_y_NO_MMI_sin_ella() -> None:
    """`D-44` cambia la regla «NO_MMI sale SIEMPRE» por «sólo sin superficie».

    Las DOS direcciones: con una sola, un aviso que saliera siempre pasaría.
    """
    con = _capturado(_bloque()).texto
    assert MMI_ESTIMADA in con
    assert NO_MMI not in con, (
        "el documento imprime una MMI ESTIMADA en la §8 y en la §5 dice que no se reporta MMI"
    )

    sin = _capturado(_bloque(calibrado_cdmx=False)).texto
    assert NO_MMI in sin
    assert MMI_ESTIMADA not in sin, "la §5 anuncia una MMI que la §8 no dibuja"


def test_la_quinta_seccion_se_DERIVA_de_lo_que_la_octava_imprime_no_del_bloque() -> None:
    """Un bloque con superficie cuyo mapa no se imprime (lectura fallida) no puede
    anunciar la MMI estimada: la §8 se rinde antes de dibujarla."""
    b = dataclasses.replace(_bloque(), fallo_de_lectura="la lectura del snapshot falló")
    texto = _capturado(b).texto
    assert MMI_ESTIMADA not in texto
    assert NO_MMI in texto


def test_sin_superficie_se_dice_POR_QUE() -> None:
    seccion = _capturado(_bloque(calibrado_cdmx=False)).seccion(MAPA_SACUDIDA)
    assert SUP.MOTIVOS[SUP.MOTIVO_SIN_CALIBRADOS] in seccion
    assert "ESTIMADO a partir de" not in seccion


def test_un_snapshot_anterior_a_D44_no_inventa_motivo() -> None:
    """Superficie y motivo en `None`: el snapshot no la trae, y eso es lo que se dice."""
    b = dataclasses.replace(_bloque(), superficie=None, superficie_motivo=None)
    seccion = _capturado(b).seccion(MAPA_SACUDIDA)
    assert "el snapshot no la trae" in seccion
    for frase in SUP.MOTIVOS.values():
        assert frase not in seccion


def test_las_ATRIBUCIONES_salen_del_json_y_solo_las_de_lo_dibujado() -> None:
    atrib = geodatos.carga("atribuciones.json")
    seccion = _capturado(_bloque()).seccion(MAPA_SACUDIDA)
    assert atrib["estados"]["corta"] in seccion
    # El marco cubre la CDMX (el inmueble del dictamen está allí): se pintan sus zonas.
    assert atrib["ntc_cdmx"]["corta"] in seccion
    # Lo que NO se dibuja no se atribuye.
    assert atrib["relieve"]["corta"] not in seccion
    assert atrib["edafologia"]["corta"] not in seccion


def test_sin_la_CDMX_en_el_marco_no_se_atribuye_su_zonificacion() -> None:
    """Un mapa en Oaxaca no dibuja las zonas de la CDMX, ni las atribuye."""
    b = _bloque()
    lejos = [dataclasses.replace(p, lat=p.lat - 2.5, lon=p.lon + 2.0) for p in b.puntos]
    b = dataclasses.replace(
        b,
        puntos=lejos,
        anillos=[],
        epicentro_lat=b.epicentro_lat - 2.5,
        epicentro_lon=b.epicentro_lon + 2.0,
        superficie=None,
        superficie_motivo=SUP.MOTIVO_SIN_CALIBRADOS,
    )
    atrib = geodatos.carga("atribuciones.json")
    seccion = _capturado(b).seccion(MAPA_SACUDIDA)
    assert atrib["ntc_cdmx"]["corta"] not in seccion
    assert atrib["estados"]["corta"] in seccion


# ─────────────────────────────── el cálculo a demanda y su fallo


def test_calculado_para_ESTE_documento_se_dice() -> None:
    seccion = _capturado(_bloque(a_demanda=True)).seccion(MAPA_SACUDIDA)
    assert SHAKEMAP_A_DEMANDA in seccion
    assert SHAKEMAP_A_DEMANDA not in _capturado(_bloque()).seccion(MAPA_SACUDIDA)


def test_un_calculo_a_demanda_FALLIDO_se_declara_y_no_se_disfraza() -> None:
    b = ShakemapBlock(fallo_de_calculo="el cálculo a demanda falló")
    cap = _capturado(b)
    seccion = cap.seccion(MAPA_SACUDIDA)
    assert SHAKEMAP_NO_CALCULADO in seccion
    assert SHAKEMAP_NO_LEIDO not in seccion, "no se leyó nada: se intentó CALCULAR"
    assert SHAKEMAP_PENDIENTE not in seccion, "«no ha corrido» no es «falló al calcular»"
    assert NO_MMI in cap.texto


# ─────────────────────────────────────────── lo que la figura DIBUJA


class _Espia:
    """Imágenes, polilíneas y recortes emitidos DENTRO de la figura de la §8."""

    def __init__(self) -> None:
        self.imagenes: list[tuple[float, float, float, float]] = []
        self.polilineas = 0
        self.poligonos = 0
        self.recortes: list[tuple[float, float, float, float]] = []
        self.marco: tuple[float, float, float, float] | None = None
        self.dibujo = None


def _figura(bloque: ShakemapBlock) -> _Espia:
    e = _Espia()
    dentro = False
    originales = {
        n: getattr(fpdf.FPDF, n) for n in ("image", "polyline", "polygon", "rect_clip", "rect")
    }
    original_mapa = pdf_mod._mapa_de_la_sacudida

    def image(self, name, x=None, y=None, w=0, h=0, *a, **k):  # noqa: ANN001, ANN202
        # Sólo DESPUÉS del marco: la `reserva()` de la figura puede saltar de página
        # y el membrete de la nueva estampa su logotipo dentro de esta llamada.
        if dentro and e.marco is not None:
            e.imagenes.append((float(x), float(y), float(w), float(h)))
        return originales["image"](self, name, x, y, w, h, *a, **k)

    def polyline(self, *a, **k):  # noqa: ANN002, ANN003, ANN202
        if dentro:
            e.polilineas += 1
        return originales["polyline"](self, *a, **k)

    def polygon(self, *a, **k):  # noqa: ANN002, ANN003, ANN202
        if dentro:
            e.poligonos += 1
        return originales["polygon"](self, *a, **k)

    def rect_clip(self, x, y, w, h):  # noqa: ANN001, ANN202
        if dentro:
            e.recortes.append((float(x), float(y), float(w), float(h)))
        return originales["rect_clip"](self, x, y, w, h)

    def rect(self, x, y, w, h, *a, **k):  # noqa: ANN001, ANN202
        if dentro and e.marco is None:
            e.marco = (float(x), float(y), float(w), float(h))
        return originales["rect"](self, x, y, w, h, *a, **k)

    def marca(pdf, b, dibujo):  # noqa: ANN001, ANN202
        nonlocal dentro
        dentro = True
        e.dibujo = dibujo
        try:
            return original_mapa(pdf, b, dibujo)
        finally:
            dentro = False

    for n, f in (
        ("image", image),
        ("polyline", polyline),
        ("polygon", polygon),
        ("rect_clip", rect_clip),
        ("rect", rect),
    ):
        setattr(fpdf.FPDF, n, f)
    pdf_mod._mapa_de_la_sacudida = marca  # type: ignore[assignment]
    try:
        render(model(shakemap=bloque), "technical")
    finally:
        for n, f in originales.items():
            setattr(fpdf.FPDF, n, f)
        pdf_mod._mapa_de_la_sacudida = original_mapa  # type: ignore[assignment]
    return e


def test_la_superficie_se_EMBEBE_donde_la_pone_el_croquis() -> None:
    b = _bloque()
    e = _figura(b)
    assert len(e.imagenes) == 1, f"se esperaba UNA imagen (la superficie): {e.imagenes}"
    assert e.marco is not None
    x0, y0, _, _ = e.marco
    sup = b.superficie
    xo, yn = e.dibujo.proyecta(sup.norte, sup.oeste)
    xe, ys = e.dibujo.proyecta(sup.sur, sup.este)
    x, y, w, h = e.imagenes[0]
    assert x == pytest.approx(x0 + xo, abs=0.01)
    assert y == pytest.approx(y0 + yn, abs=0.01)
    assert w == pytest.approx(xe - xo, abs=0.01)
    assert h == pytest.approx(ys - yn, abs=0.01)
    assert w > 0 and h > 0


def test_la_cartografia_se_dibuja_RECORTADA_al_marco() -> None:
    e = _figura(_bloque())
    assert e.marco is not None
    assert e.recortes, "la cartografía se pinta sin recorte: se saldría encima de la página"
    assert e.recortes[0] == pytest.approx(e.marco)
    assert e.polilineas > 0, "no se dibujó ni un contorno estatal"
    assert e.poligonos > 0, "no se rellenó ninguna zona de la CDMX estando en el marco"


def test_sin_superficie_NO_se_embebe_imagen() -> None:
    assert _figura(_bloque(calibrado_cdmx=False)).imagenes == []


def test_el_croquis_proyecta_igual_que_proyecto_los_puntos() -> None:
    """`Sketch.proyecta` es la MISMA transformación que situó cada punto."""
    e = _figura(_bloque())
    for p, q in zip(pdf_mod._puntos_del_mapa(_bloque()), e.dibujo.points, strict=True):
        x, y = e.dibujo.proyecta(p.lat, p.lon)
        assert (x, y) == pytest.approx((q.x, q.y))


def test_la_superficie_ENCUADRA_y_cae_entera_dentro_del_marco() -> None:
    """Sus esquinas entran al encuadre como los anillos: la imagen no se sale.

    Con dos inmuebles juntos y sin anillos el encuadre lo marcaban ellos —unos
    kilómetros— y la superficie, 60 km como mínimo, desbordaba por los cuatro
    lados: el recorte la escondía en pantalla, pero una imagen fuera de su caja
    es otra escala dentro de la misma figura.
    """
    b = dataclasses.replace(_bloque(), anillos=[], epicentro_lat=None, epicentro_lon=None)
    e = _figura(b)
    assert e.marco is not None and len(e.imagenes) == 1
    x0, y0, ancho, alto = e.marco
    x, y, w, h = e.imagenes[0]
    assert x >= x0 - 0.05 and y >= y0 - 0.05
    assert x + w <= x0 + ancho + 0.05 and y + h <= y0 + alto + 0.05
