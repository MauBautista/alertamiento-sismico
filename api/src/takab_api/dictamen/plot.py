"""Escalado de trazas para el PDF (T-2.41): espejo Python de ``web/.../svgScale.ts``.

Mismos casos, mismos números y la misma decisión que más importa: **un hueco NO se
interpola**. Una serie con lagunas dibujada de un solo trazo cruza el silencio con una
recta que se lee como "aquí todo estuvo bien" — justo donde no hubo dato.

Escala independiente por traza, igual que en la consola: los canales de un RS4D difieren
en órdenes de magnitud (velocidad del geófono vs. aceleración del acelerómetro) y una
escala común aplastaría tres de ellos hasta la línea recta.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Piso de escala. Sin él, una traza plana de ruido se amplificaría a pantalla completa
#: y parecería un sismo. Mismo valor que ``svgScale.ts::MIN_SCALE``.
MIN_SCALE = 0.05


def scale_of(values: list[float | None]) -> float:
    """Máximo absoluto de la serie, con piso. Nunca 0 (evita división por cero)."""
    known = [abs(v) for v in values if v is not None]
    return max(max(known, default=0.0), MIN_SCALE)


@dataclass(frozen=True, slots=True)
class Box:
    """Rectángulo de dibujo en milímetros de página."""

    x: float
    y: float
    w: float
    h: float


def segments(
    values: list[float | None], box: Box, scale: float, *, baseline: bool = False
) -> list[list[tuple[float, float]]]:
    """Polilíneas contiguas en coordenadas de página. Los ``None`` parten la serie.

    ``baseline=True`` centra en la mitad del alto (señal con signo); en falso el 0
    queda abajo (magnitudes positivas como PGA).
    """
    if len(values) < 2 or scale <= 0:
        return []
    step = box.w / (len(values) - 1)
    zero_y = box.y + box.h / 2 if baseline else box.y + box.h
    amp = (box.h / 2) if baseline else box.h

    out: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    for i, v in enumerate(values):
        if v is None:
            if len(current) > 1:
                out.append(current)
            current = []
            continue
        y = zero_y - (v / scale) * amp
        # Recorte al box: un pico que sature no debe pintarse fuera del marco y
        # solaparse con la traza de arriba.
        y = min(max(y, box.y), box.y + box.h)
        current.append((box.x + i * step, y))
    if len(current) > 1:
        out.append(current)
    return out


def clipping_marks(flags: list[bool | None], box: Box) -> list[float]:
    """Coordenada X de cada muestra con recorte del ADC.

    Se marcan aparte porque un canal saturado NO midió el pico: midió el techo del
    conversor. Sin la marca, el operador leería ese valor como la aceleración real.
    """
    if len(flags) < 2:
        return []
    step = box.w / (len(flags) - 1)
    return [box.x + i * step for i, flag in enumerate(flags) if flag]


def nice_ticks(count: int, ticks: int = 4) -> list[int]:
    """Índices repartidos para el eje temporal (incluye extremos)."""
    if count <= 1:
        return [0] if count == 1 else []
    ticks = max(2, min(ticks, count))
    return [round(i * (count - 1) / (ticks - 1)) for i in range(ticks)]
