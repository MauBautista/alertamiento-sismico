"""Croquis vectorial del incidente (T-2.41): sitio, epicentro y estaciones del quórum.

**Sin cartografía base, a propósito.** Traer tiles de un servicio externo haría que la
generación de un dictamen —evidencia de compliance— dependiera de que el servidor tenga
internet y de que un tercero siga sirviendo mapas. Un dictamen que a veces sale sin
mapa, y a veces no sale, no es evidencia.

Lo que sí puede afirmarse con la geometría propia es dónde están las cosas, a qué
distancia y en qué rumbo. Eso es un croquis, y se rotula como tal.

Proyección equirectangular local con corrección ``cos(lat)``: a estas escalas (decenas
a cientos de km) las distorsiones son irrelevantes, y el croquis lleva barra de escala
y flecha de norte para que nadie mida sobre él como si fuera una carta.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from takab_api.geo import haversine_km


@dataclass(frozen=True, slots=True)
class Point:
    """Punto rotulado del croquis."""

    lat: float
    lon: float
    label: str
    #: ``site`` = el inmueble del dictamen · ``epicenter`` · ``peer`` = estación del quórum
    kind: str


@dataclass(frozen=True, slots=True)
class Projected:
    x: float
    y: float
    label: str
    kind: str


@dataclass(frozen=True, slots=True)
class Sketch:
    points: list[Projected]
    #: Longitud de la barra de escala, en mm de página y en km reales.
    scale_bar_mm: float
    scale_bar_km: float


# Valores "redondos" para la barra de escala: nadie mide con una barra de 37 km.
_NICE_KM = (1, 2, 5, 10, 20, 50, 100, 200, 500, 1000)


def _nice_km(span_km: float) -> float:
    target = span_km / 3.0
    for value in _NICE_KM:
        if value >= target:
            return float(value)
    return float(_NICE_KM[-1])


def project(
    points: list[Point], width_mm: float, height_mm: float, pad_mm: float = 8.0
) -> Sketch | None:
    """Proyecta los puntos al recuadro. ``None`` si no hay geometría que dibujar.

    Devolver ``None`` es parte del contrato: sin coordenadas, el dictamen declara que
    no hay croquis en vez de imprimir un marco vacío que parece un fallo de impresión.
    """
    usable = [p for p in points if p.lat is not None and p.lon is not None]
    if not usable:
        return None

    lats = [p.lat for p in usable]
    lat0 = sum(lats) / len(lats)
    # Corrección de meridiano: a 19°N un grado de longitud mide ~0.95 de uno de
    # latitud. Sin ella, el croquis estira el eje E-O y los rumbos mienten.
    kx = math.cos(math.radians(lat0))

    xs = [p.lon * kx for p in usable]
    ys = [p.lat for p in usable]
    span_x = max(xs) - min(xs)
    span_y = max(ys) - min(ys)
    # Un solo punto (o todos coincidentes): se centra con un margen arbitrario pero
    # con escala real, para que la barra siga significando algo.
    span = max(span_x, span_y, 1e-4)

    inner_w = width_mm - 2 * pad_mm
    inner_h = height_mm - 2 * pad_mm
    scale = min(inner_w, inner_h) / span

    cx = (max(xs) + min(xs)) / 2
    cy = (max(ys) + min(ys)) / 2

    projected = [
        Projected(
            x=width_mm / 2 + (p.lon * kx - cx) * scale,
            # Y invertida: en página crece hacia abajo, en latitud hacia arriba.
            y=height_mm / 2 - (p.lat - cy) * scale,
            label=p.label,
            kind=p.kind,
        )
        for p in usable
    ]

    # Barra de escala: se calcula sobre una distancia REAL medida con haversine, no
    # sobre la proyección — así el número que se imprime es kilómetros de verdad.
    span_km = haversine_km(cy, (cx / kx) if kx else 0.0, cy + span, (cx / kx) if kx else 0.0)
    # [T-7.39] La MISMA escala con la que se proyectan los puntos —`min(inner_w,
    # inner_h)`—, no `inner_h` a secas. En el formato real del dictamen coinciden
    # porque el alto es el lado corto (62.0 mm frente a 169.9); en un croquis más
    # estrecho que alto no, y la
    # barra salía con una escala distinta de la del dibujo que pretende medir.
    mm_per_km = (min(inner_w, inner_h) / span_km) if span_km > 0 else 0.0
    # [T-7.39] La barra se RECORTABA a la mitad del ancho y el rótulo conservaba los
    # kilómetros sin recortar: quien midiera sobre el papel medía mal, y el croquis
    # existe justo para que se pueda medir. Ahora se elige el valor redondo MÁS
    # GRANDE que quepa entero; si ni el más pequeño cabe, se dibuja lo que mide de
    # verdad y el rótulo dice ese mismo número.
    # [T-7.39] El `min(...)` de antes RECORTABA la barra y dejaba el rótulo con los
    # kilómetros sin recortar: quien midiera sobre el papel mediría mal. Verificado
    # el 2026-09-14: con el formato real (180 × 78 mm en A4) el tope nunca llegaba a
    # morder —la barra no pasaba de 62 mm sobre un tope de 82—, así que la
    # contradicción NO estaba viva. RE-DERIVADO para Carta el 2026-09-16 (`T-7.21`):
    # la caja pasa a 185.9 × 78 mm ⇒ interior 169.9 × 62.0, la escala la sigue
    # mandando el lado corto (62.0 mm) y el tope sube a 85.0. Sigue sin morder, y
    # con MÁS margen que antes. Queda como mentira LATENTE: un croquis más estrecho o más alto la
    # activa sin que nada avise. Se baja al valor redondo que quepa entero en vez de
    # cortar, y el rótulo dice siempre lo que la barra mide.
    tope_mm = inner_w * 0.5
    bar_km = _nice_km(max(span_km, 0.5))
    if mm_per_km > 0 and bar_km * mm_per_km > tope_mm:
        for valor in reversed(_NICE_KM):
            if valor < bar_km and valor * mm_per_km <= tope_mm:
                bar_km = float(valor)
                break
        else:
            bar_km = tope_mm / mm_per_km
    return Sketch(
        points=projected,
        scale_bar_mm=min(bar_km * mm_per_km, tope_mm),
        scale_bar_km=bar_km,
    )
