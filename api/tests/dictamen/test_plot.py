"""T-2.41 · Escalado de trazas del PDF. Paridad con ``web/.../svgScale.test.ts``.

Los mismos casos que la consola, porque el operador compara con lo que vio en pantalla.
El caso que más importa: un hueco NO se interpola. Una recta que cruza el silencio se
lee como "aquí todo estuvo bien" justo donde no hubo dato.
"""

from __future__ import annotations

from takab_api.dictamen.plot import MIN_SCALE, Box, clipping_marks, nice_ticks, scale_of, segments

BOX = Box(x=10.0, y=20.0, w=100.0, h=20.0)


def test_la_escala_es_el_maximo_absoluto() -> None:
    assert scale_of([0.1, -0.4, 0.2]) == 0.4


def test_hay_un_piso_de_escala() -> None:
    """Sin piso, una traza de puro ruido se amplifica hasta parecer un sismo."""
    assert scale_of([0.001, -0.002]) == MIN_SCALE
    assert scale_of([]) == MIN_SCALE


def test_una_serie_continua_es_un_solo_trazo() -> None:
    assert len(segments([0.1, 0.2, 0.3, 0.2], BOX, 0.3)) == 1


def test_un_hueco_PARTE_la_serie_en_lugar_de_interpolarla() -> None:
    segs = segments([0.1, 0.2, None, 0.3, 0.2], BOX, 0.3)
    assert len(segs) == 2
    assert all(len(s) >= 2 for s in segs)


def test_un_punto_suelto_entre_huecos_no_dibuja_nada() -> None:
    assert segments([None, 0.2, None], BOX, 0.3) == []


def test_menos_de_dos_puntos_no_dibuja_nada() -> None:
    assert segments([0.5], BOX, 0.5) == []


def test_los_puntos_caen_dentro_del_recuadro() -> None:
    """Un pico que sature no puede pintarse fuera del marco y solapar la traza vecina."""
    segs = segments([5.0, -5.0, 5.0], BOX, 0.1)
    for seg in segs:
        for _, y in seg:
            assert BOX.y <= y <= BOX.y + BOX.h


def test_la_linea_base_centrada_pone_el_cero_a_media_altura() -> None:
    [(x0, y0)], *_ = [segments([0.0, 0.0], BOX, 1.0, baseline=True)[0][:1]]
    assert x0 == BOX.x
    assert y0 == BOX.y + BOX.h / 2


def test_sin_linea_base_el_cero_queda_abajo() -> None:
    seg = segments([0.0, 0.0], BOX, 1.0)[0]
    assert seg[0][1] == BOX.y + BOX.h


def test_las_marcas_de_recorte_caen_donde_saturo() -> None:
    xs = clipping_marks([False, True, False, True], BOX)
    assert len(xs) == 2
    assert xs[0] == BOX.x + BOX.w / 3


def test_sin_recorte_no_hay_marcas() -> None:
    assert clipping_marks([False, False], BOX) == []


def test_los_ticks_incluyen_los_extremos() -> None:
    ticks = nice_ticks(100, 4)
    assert ticks[0] == 0
    assert ticks[-1] == 99
    assert len(ticks) == 4


def test_una_serie_de_un_punto_no_revienta_los_ticks() -> None:
    assert nice_ticks(1) == [0]
    assert nice_ticks(0) == []
