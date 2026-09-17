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
    """Cambiar lo que el documento afirma sobre cuánto tardó la gente en salir tiene
    que mover el `content_sha256`.

    ⚠️ [T-7.43] El motivo ya no es «o la huella no sirve para comparar dos
    exportaciones»: comparar exportaciones **no se puede** —exportar inserta una
    fila de evidencia que la siguiente imprime— y el papel dejó de prometerlo. El
    motivo es que el número identifica esta exportación, y este campo forma parte
    de lo que afirma. El invariante general vive en
    `test_que_identifica_la_huella.py::test_NINGUN_campo_del_modelo_es_CIEGO_a_la_huella`;
    esto lo nombra para este campo en concreto.
    """
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


# ---- [T-7.38·F] la poda no se lee como «disponible» --------------------------
#
# El estado se decidía por que EXISTIERA la fila del clip. La fila sobrevive a la
# poda A PROPÓSITO —es la cadena de custodia, con su sha256 y su ventana—, así que
# un clip ya destruido se anunciaba como «CLIP DISPONIBLE · ANÁLISIS PENDIENTE» y
# el papel prometía cifras de evacuación que no van a llegar nunca.


def _clase(*disponibles: bool) -> str:
    from takab_api.schemas.cctv import clase_del_material

    return clase_del_material(list(disponibles))


def test_todos_los_clips_VIVOS_es_analisis_pendiente() -> None:
    from takab_api.schemas.cctv import CLIPS_VIVOS

    assert _clase(True, True) == CLIPS_VIVOS


def test_todos_PURGADOS_es_una_clase_propia() -> None:
    from takab_api.schemas.cctv import CLIPS_PURGADOS

    assert _clase(False, False) == CLIPS_PURGADOS


def test_ALGUNOS_purgados_NO_es_lo_mismo_que_ninguno() -> None:
    """El estado mixto era el que se colaba: recaía en «el vídeo está archivado»."""
    from takab_api.schemas.cctv import CLIPS_MIXTOS, CLIPS_VIVOS

    assert _clase(True, False) == CLIPS_MIXTOS
    assert _clase(True, False) != CLIPS_VIVOS


def test_sin_clips_es_sin_clips() -> None:
    from takab_api.schemas.cctv import CLIPS_SIN

    assert _clase() == CLIPS_SIN


def test_las_cuatro_clases_son_DISTINGUIBLES() -> None:
    """Control de ceguera: con dos clases iguales, los tests de arriba no miden."""
    from takab_api.schemas.cctv import CLIPS_MIXTOS, CLIPS_PURGADOS, CLIPS_SIN, CLIPS_VIVOS

    assert len({CLIPS_SIN, CLIPS_VIVOS, CLIPS_PURGADOS, CLIPS_MIXTOS}) == 4


# ---- [T-7.38·G] «no se observó» con la hora del reingreso escrita al lado -----


def test_el_reingreso_OBSERVADO_sin_latencia_no_se_declara_no_observado() -> None:
    """`lag_s` nulo son DOS ausencias y compartían una sola frase.

    El Lambda cierra el análisis sin la hora del dictamen —nunca la recibe—, así
    que `reentry_lag_s` sale nulo aunque el reingreso SÍ se haya observado y su
    hora esté en la misma fila. El papel decía «no se observó el inicio del
    reingreso» con ese instante escrito al lado.
    """
    from datetime import UTC, datetime

    from takab_api.cctv import veredicto_reingreso

    _, frase = veredicto_reingreso(None, datetime(2026, 8, 3, 10, 12, tzinfo=UTC))
    assert "no se observó" not in frase, "niega una observación que consta"
    assert "SIN LATENCIA CALCULADA" in frase


def test_sin_observar_el_reingreso_se_sigue_diciendo_que_NO_se_observo() -> None:
    """La otra mitad: cuando de verdad no se vio, la frase de siempre."""
    from takab_api.cctv import veredicto_reingreso

    _, frase = veredicto_reingreso(None, None)
    assert frase == "SIN DATO · no se observó el inicio del reingreso"


def test_la_frase_NO_se_pronuncia_sobre_si_hay_dictamen_firmado() -> None:
    """El analizador no sabe eso: nunca recibió la hora de la firma. Lo único que
    puede declarar es que falta el término calculado."""
    from datetime import UTC, datetime

    from takab_api.cctv import veredicto_reingreso

    _, frase = veredicto_reingreso(None, datetime(2026, 8, 3, 10, 12, tzinfo=UTC))
    assert "NO CONSTA dictamen" not in frase
    assert "sin dictamen" not in frase.lower()


def test_con_latencia_la_frase_no_cambia() -> None:
    """Control: el camino que sí tiene el dato sigue igual, y el hallazgo también."""
    from takab_api.cctv import veredicto_reingreso

    assert veredicto_reingreso(-412.0)[0] is True
    assert "después del dictamen firmado" in veredicto_reingreso(120.0)[1]
