// Escalado puro para las trazas SVG (T-1.34). Sin dependencias: ni React ni DOM.
//
// Todo el dibujo de series del SOC se hace a mano con SVG (no hay librería de gráficas).
// Estas funciones son la parte que puede fallar en silencio, así que viven aparte y se
// prueban solas.

/** Piso del eje vertical: sin él, un micro-tremor se pinta como un terremoto. */
export const MIN_SCALE = 0.05;

export interface Box {
  width: number;
  height: number;
  top: number;
  bottom: number;
}

/** Máximo de la serie con piso `MIN_SCALE`. Ignora huecos (`null`). */
export function scaleOf(values: readonly (number | null)[], floor = MIN_SCALE): number {
  let max = floor;
  for (const v of values) {
    if (v !== null && v > max) max = v;
  }
  return max;
}

/** Y de un valor dentro de la caja: `null` (hueco) se ancla a la base, no a cero-arriba. */
export function yOf(value: number | null, scale: number, box: Box): number {
  const v = value ?? 0;
  const clamped = Math.min(Math.max(v / scale, 0), 1);
  return box.bottom - clamped * (box.bottom - box.top);
}

/**
 * Path SVG de una serie uniformemente espaciada.
 *
 * Devuelve `""` con menos de dos puntos: un `M` suelto no dibuja nada y ensucia el DOM.
 */
export function pathOf(values: readonly (number | null)[], scale: number, box: Box): string {
  if (values.length < 2) return "";
  const step = box.width / (values.length - 1);
  return values
    .map(
      (v, i) => `${i === 0 ? "M" : "L"} ${(i * step).toFixed(1)} ${yOf(v, scale, box).toFixed(1)}`,
    )
    .join(" ");
}

/** X (px) de cada índice marcado como clipping. */
export function clippingXs(flags: readonly boolean[], width: number): number[] {
  if (flags.length < 2) return [];
  const step = width / (flags.length - 1);
  return flags.flatMap((on, i) => (on ? [i * step] : []));
}

/**
 * Marcas del eje temporal: hasta `count` instantes repartidos por el rango.
 *
 * Devuelve epoch ms + su X. Con un solo punto no hay eje que dibujar.
 */
export function timeTicks(
  timestamps: readonly number[],
  width: number,
  count = 5,
): { ts: number; x: number }[] {
  if (timestamps.length < 2) return [];
  const last = timestamps.length - 1;
  const every = Math.max(1, Math.floor(last / Math.max(1, count - 1)));
  const ticks: { ts: number; x: number }[] = [];
  for (let i = 0; i <= last; i += every) {
    ticks.push({ ts: timestamps[i], x: (i / last) * width });
  }
  // El último instante siempre se rotula: es el "ahora" de la traza.
  if (ticks[ticks.length - 1].ts !== timestamps[last]) {
    ticks.push({ ts: timestamps[last], x: width });
  }
  return ticks;
}
