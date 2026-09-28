"""[T-9.51 · D-44] El PNG de la superficie: color de BANDA, opacidad de ZONA.

* El color es la banda del dictamen (`D-43`): verde, amarillo, rojo, con los MISMOS
  umbrales que recibe; el mapa no puede pintar rojo donde el dictamen dice verde.
* La zona AJUSTADA es más opaca que la MODELADA: lo que no se midió se ve menos.
* Bajo el piso visible la celda es transparente: no se tiñe medio país de verde.
* Mismo dato ⇒ mismos bytes (el PDF lo embebe y su huella no puede bailar).
"""

from __future__ import annotations

import io

from PIL import Image

from takab_api.shakemap import raster as R
from takab_api.shakemap.superficie import Superficie

VERDE_MAX, ROJO_MIN = 0.04, 0.10


def _sup(valores: list[list[float]], ajustada: list[list[bool]] | None = None) -> Superficie:
    alto, ancho = len(valores), len(valores[0])
    ajustada = ajustada or [[True] * ancho for _ in range(alto)]
    return Superficie(
        oeste=-99.0,
        sur=19.0,
        este=-98.0,
        norte=20.0,
        ancho=ancho,
        alto=alto,
        pga_g=tuple(tuple(f) for f in valores),
        ajustada=tuple(tuple(f) for f in ajustada),
        n_sensores=1,
        n_calibrados=1,
        escala_km=15.0,
    )


def _pixeles(png: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(png))
    assert img.mode == "RGBA"
    return img


def test_el_color_es_la_banda_del_dictamen() -> None:
    img = _pixeles(R.png(_sup([[0.02, 0.07, 0.2]]), verde_max_g=VERDE_MAX, rojo_min_g=ROJO_MIN))
    assert img.getpixel((0, 0))[:3] == R.COLOR[R.BANDA_VERDE]
    assert img.getpixel((1, 0))[:3] == R.COLOR[R.BANDA_AMARILLO]
    assert img.getpixel((2, 0))[:3] == R.COLOR[R.BANDA_ROJO]


def test_los_bordes_de_banda_son_los_del_dictamen() -> None:
    """`< verde_max` es verde; `≥ rojo_min` es rojo (mismo corte que `evaluate_v2`)."""
    assert R.banda(0.0399, VERDE_MAX, ROJO_MIN) == R.BANDA_VERDE
    assert R.banda(0.04, VERDE_MAX, ROJO_MIN) == R.BANDA_AMARILLO
    assert R.banda(0.0999, VERDE_MAX, ROJO_MIN) == R.BANDA_AMARILLO
    assert R.banda(0.10, VERDE_MAX, ROJO_MIN) == R.BANDA_ROJO


def test_lo_MODELADO_se_ve_menos_que_lo_AJUSTADO() -> None:
    # 10 columnas de ≈10.5 km: la segunda está a una celda de la ajustada (< L).
    sup = _sup([[0.07] * 10], [[True] + [False] * 9])
    img = _pixeles(R.png(sup, verde_max_g=VERDE_MAX, rojo_min_g=ROJO_MIN))
    assert img.getpixel((0, 0))[3] > img.getpixel((1, 0))[3] > 0


def test_bajo_el_piso_es_transparente() -> None:
    img = _pixeles(
        R.png(_sup([[R.PISO_VISIBLE_G / 2]]), verde_max_g=VERDE_MAX, rojo_min_g=ROJO_MIN)
    )
    assert img.getpixel((0, 0))[3] == 0


def test_la_fila_cero_es_la_de_arriba() -> None:
    img = _pixeles(R.png(_sup([[0.2], [0.02]]), verde_max_g=VERDE_MAX, rojo_min_g=ROJO_MIN))
    assert img.size == (1, 2)
    assert img.getpixel((0, 0))[:3] == R.COLOR[R.BANDA_ROJO]


def test_mismo_dato_mismos_bytes() -> None:
    sup = _sup([[0.02, 0.07], [0.2, 0.001]], [[True, False], [True, True]])
    a = R.png(sup, verde_max_g=VERDE_MAX, rojo_min_g=ROJO_MIN)
    b = R.png(sup, verde_max_g=VERDE_MAX, rojo_min_g=ROJO_MIN)
    assert a == b and a.startswith(b"\x89PNG")


def test_lo_MODELADO_solo_se_pinta_cerca_de_lo_AJUSTADO() -> None:
    """Más allá de L de la zona ajustada, transparente: el borde de la malla no es un
    límite físico, y teñir hasta él pintaba una sacudida donde nadie midió.

    La malla de `_sup` va de -99 a -98 (≈105 km a 19.5°N) en 10 columnas: celdas de
    ≈10.5 km. Con L = 15 km, la columna 1 (a una celda de la ajustada) se pinta y la
    columna 3 (a tres celdas, ≈31 km) ya no.
    """
    fila = [0.07] * 10
    mascara = [True] + [False] * 9
    img = _pixeles(R.png(_sup([fila], [mascara]), verde_max_g=VERDE_MAX, rojo_min_g=ROJO_MIN))
    assert img.getpixel((1, 0))[3] == R.ALFA_MODELADA
    assert img.getpixel((3, 0))[3] == 0
    assert img.getpixel((9, 0))[3] == 0


def test_sin_zona_AJUSTADA_no_se_pinta_nada() -> None:
    img = _pixeles(
        R.png(_sup([[0.07, 0.2]], [[False, False]]), verde_max_g=VERDE_MAX, rojo_min_g=ROJO_MIN)
    )
    assert img.getpixel((0, 0))[3] == 0 and img.getpixel((1, 0))[3] == 0
