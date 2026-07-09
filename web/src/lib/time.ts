/** Utilidades de tiempo del SOC (los relojes de tablas y banners van en UTC). */

/** HH:MM:SS UTC de un instante epoch-ms. */
export function utcClock(epochMs: number): string {
  return new Date(epochMs).toISOString().slice(11, 19);
}

/** `YYYY-MM-DD · HH:MM` UTC — sello del historial, donde el día importa. */
export function utcStamp(epochMs: number): string {
  const iso = new Date(epochMs).toISOString();
  return `${iso.slice(0, 10)} · ${iso.slice(11, 16)}`;
}

/** Segundos enteros transcurridos entre un instante y "ahora" (nunca negativo). */
export function secondsSince(epochMs: number, nowMs: number): number {
  return Math.max(0, Math.floor((nowMs - epochMs) / 1000));
}
