"""[T-9.51 · D-44] La superficie estimada como PNG: una celda, un píxel.

Módulo puro (Pillow, que ya llega con fpdf2: sin dependencias nuevas). Lo sirve la API
para la capa `image` de MapLibre y lo embebe el PDF.

* **El color es la banda del dictamen** (`D-43`), con los umbrales que se le pasan
  —los mismos que resuelve `dictamen/rules.py`—: el mapa no puede pintar ROJO donde el
  dictamen del mismo sitio dice VERDE.
* **La opacidad es la zona**: la AJUSTADA a sensores calibrados se ve más que la solo
  MODELADA por la ley. Es la mitad del rótulo «ESTIMADO» que sí puede decir la imagen.
* **Bajo `PISO_VISIBLE_G` la celda es transparente**: 0.01 g es una MMI estimada de III
  (Wald 1999), apenas perceptible, y teñir de verde todo lo que queda por debajo
  afirmaría una sacudida donde la ley ya no dice nada útil.
* **Lo MODELADO sólo se pinta a menos de ``escala_km`` (L) de la zona AJUSTADA.** Más
  allá, transparente. Visto en la consola el 2026-09-28: con la malla entera teñida,
  un rectángulo verde de bordes rectos cubría de Cuernavaca a Tlaxcala, y su borde —que
  es sólo el margen de la malla— se leía como un límite de la sacudida. Así la mancha
  termina en redondo alrededor de lo medido, y sin zona ajustada no se pinta nada.

Fila 0 = norte, que es el orden de la malla y el de la imagen: nada se voltea.
"""

from __future__ import annotations

import io
import math

import numpy as np
from PIL import Image

from takab_api.shakemap.superficie import Superficie

BANDA_VERDE = "verde"
BANDA_AMARILLO = "amarillo"
BANDA_ROJO = "rojo"

#: RGB por banda. Legibles sobre el mapa claro y sobre el papel.
COLOR: dict[str, tuple[int, int, int]] = {
    BANDA_VERDE: (46, 160, 67),
    BANDA_AMARILLO: (232, 176, 0),
    BANDA_ROJO: (208, 40, 40),
}

#: Opacidad (0–255) por zona.
ALFA_AJUSTADA = 150
ALFA_MODELADA = 60

#: Por debajo de esto, transparente (ver el encabezado).
PISO_VISIBLE_G = 0.01


def banda(pga_g: float, verde_max_g: float, rojo_min_g: float) -> str:
    """El mismo corte que `evaluate_v2`: ``< verde_max`` verde, ``≥ rojo_min`` rojo."""
    if pga_g >= rojo_min_g:
        return BANDA_ROJO
    if pga_g >= verde_max_g:
        return BANDA_AMARILLO
    return BANDA_VERDE


def _cerca_de_lo_ajustado(sup: Superficie) -> np.ndarray:
    """Máscara de las celdas a menos de L (km) de una celda AJUSTADA (ésas incluidas).

    Distancia entre centros de celda en km locales (la longitud escalada con el coseno de
    la latitud media): a la escala de la malla, la equirrectangular basta.
    """
    ajustada = np.array(sup.ajustada, dtype=bool)
    if not ajustada.any():
        return ajustada
    lat_media = math.radians((sup.norte + sup.sur) / 2)
    km_x = (sup.este - sup.oeste) / sup.ancho * 111.195 * math.cos(lat_media)
    km_y = (sup.norte - sup.sur) / sup.alto * 111.195
    filas, columnas = np.nonzero(ajustada)
    ii, jj = np.indices(ajustada.shape)
    cerca = np.zeros(ajustada.shape, dtype=bool)
    for i, j in zip(filas, columnas, strict=True):
        cerca |= ((ii - i) * km_y) ** 2 + ((jj - j) * km_x) ** 2 <= sup.escala_km**2
    return cerca


def png(sup: Superficie, *, verde_max_g: float, rojo_min_g: float) -> bytes:
    """El PNG RGBA de la superficie (ancho × alto píxeles)."""
    cerca = _cerca_de_lo_ajustado(sup)
    pixeles: list[tuple[int, int, int, int]] = []
    for i, (fila_pga, fila_ajustada) in enumerate(zip(sup.pga_g, sup.ajustada, strict=True)):
        for j, (pga, ajustada) in enumerate(zip(fila_pga, fila_ajustada, strict=True)):
            if pga < PISO_VISIBLE_G or not cerca[i, j]:
                pixeles.append((0, 0, 0, 0))
                continue
            r, g, b = COLOR[banda(pga, verde_max_g, rojo_min_g)]
            pixeles.append((r, g, b, ALFA_AJUSTADA if ajustada else ALFA_MODELADA))
    img = Image.new("RGBA", (sup.ancho, sup.alto))
    img.putdata(pixeles)
    salida = io.BytesIO()
    img.save(salida, format="PNG")
    return salida.getvalue()
