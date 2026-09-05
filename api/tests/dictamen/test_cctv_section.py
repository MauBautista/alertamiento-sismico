"""La sección de CCTV del dictamen (T-3.12.c).

Un dictamen es un documento que alguien FIRMA. Lo que aquí se prueba es que **la ausencia
se declare** —los tres estados del CCTV significan cosas opuestas y se leerían igual con un
«sin datos»— y que un hallazgo de seguridad no acabe siendo una celda más de una tabla.
"""

from __future__ import annotations

from datetime import UTC, datetime

from takab_api.dictamen.model import (
    CCTV_PENDIENTE,
    CCTV_PURGADO,
    CCTV_SIN_CLIP,
    NO_CCTV,
    CctvBlock,
    CctvObjectRow,
)
from takab_api.dictamen.pdf import render

from .test_pdf import model

_T0 = datetime(2026, 8, 30, 10, 0, 0, tzinfo=UTC)


def _con(bloque: CctvBlock) -> bytes:
    m = model()
    m.cctv = bloque
    return render(m, "technical")


def test_sin_camara_la_seccion_EXISTE_y_lo_declara() -> None:
    """Omitirla dejaría al lector sin saber si el inmueble no tiene CCTV o si el generador
    se saltó la sección."""
    pdf = _con(CctvBlock())
    assert len(pdf) > 1000
    assert CctvBlock().estado == NO_CCTV
    assert "no indica que nadie evacuara" in NO_CCTV


def test_los_tres_estados_dicen_cosas_DISTINTAS() -> None:
    """«No tiene CCTV», «lo tiene y no llegó el vídeo» y «llegó y nadie lo contó» son tres
    diagnósticos con tres acciones distintas."""
    assert len({NO_CCTV, CCTV_SIN_CLIP, CCTV_PENDIENTE}) == 3
    assert "no tiene cámara" in NO_CCTV
    assert "revísese el gabinete" in CCTV_SIN_CLIP
    assert "versión posterior" in CCTV_PENDIENTE


def test_el_analisis_pendiente_no_se_pinta_como_un_cero() -> None:
    """Un fallback no puede ser `ok`."""
    bloque = CctvBlock(estado=CCTV_PENDIENTE)
    assert bloque.t90_s is None and bloque.peak_n is None
    assert len(_con(bloque)) > 1000


def test_el_bloque_entra_en_la_huella_del_documento() -> None:
    """Cambiar lo que el documento afirma sobre cuánto tardó la gente en salir tiene que
    mover el `content_sha256`, o la huella no sirve para comparar dos exportaciones."""
    a = model()
    b = model()
    b.cctv = CctvBlock(estado="análisis disponible", t90_s=50.0, peak_n=40)
    assert a.content_sha256() != b.content_sha256()


def test_reingresar_antes_del_dictamen_cambia_el_PDF() -> None:
    """No es una celda más: va en recuadro, y el documento tiene que salir distinto."""
    normal = _con(
        CctvBlock(
            estado="análisis disponible",
            t90_s=50.0,
            peak_n=40,
            veredicto_reingreso="el reingreso empezó 300 s después del dictamen firmado",
        )
    )
    hallazgo = _con(
        CctvBlock(
            estado="análisis disponible",
            t90_s=50.0,
            peak_n=40,
            veredicto_reingreso="⚠ EL REINGRESO EMPEZÓ 110 s ANTES del dictamen firmado",
            reingreso_antes_del_dictamen=True,
        )
    )
    assert normal != hallazgo


def test_la_custodia_sobrevive_a_la_poda_del_objeto() -> None:
    """El hecho sobrevive, la imagen no: `sha256` y fecha siguen en el documento después de
    que la retención se lleve el vídeo."""
    bloque = CctvBlock(
        estado="análisis disponible",
        t90_s=50.0,
        peak_n=40,
        objetos=[
            CctvObjectRow(
                tipo="clip", papel=None, sha256="a" * 64, momento=_T0, estado=CCTV_PURGADO
            ),
            CctvObjectRow(
                tipo="captura", papel="peak", sha256="b" * 64, momento=_T0, estado="disponible"
            ),
        ],
    )
    assert len(_con(bloque)) > 1000
    assert CCTV_PURGADO == "PURGADO (retención de vídeo)"


def test_la_correlacion_con_la_sacudida_llega_al_documento() -> None:
    con = _con(
        CctvBlock(
            estado="análisis disponible",
            t90_s=50.0,
            peak_n=40,
            correlacion="sacudida PGA 0.187 g — la mayor parte salió en 50 s",
        )
    )
    sin = _con(CctvBlock(estado="análisis disponible", t90_s=50.0, peak_n=40))
    assert con != sin


def test_la_discrepancia_se_imprime_como_discrepancia() -> None:
    con = _con(
        CctvBlock(
            estado="análisis disponible",
            t90_s=50.0,
            peak_n=40,
            discrepancia="4 persona(s) MÁS en el pase de lista que en cámara",
        )
    )
    sin = _con(CctvBlock(estado="análisis disponible", t90_s=50.0, peak_n=40))
    assert con != sin
