/** Utilidades de tiempo del SOC (los relojes de tablas y banners van en UTC). */

/** HH:MM:SS UTC de un instante epoch-ms. */
export function utcClock(epochMs: number): string {
  return new Date(epochMs).toISOString().slice(11, 19);
}

/** Segundos enteros transcurridos entre un instante y "ahora" (nunca negativo). */
export function secondsSince(epochMs: number, nowMs: number): number {
  return Math.max(0, Math.floor((nowMs - epochMs) / 1000));
}
