// Reintentos de la cola offline (spec §4.2): exponencial con jitter ±50%.
// El jitter evita que una flota entera reconectando martillee al servidor
// en el mismo instante tras un apagón de red.

export const BASE_DELAY_MS = 5_000;
// Techo corto a propósito: en crisis las ventanas de red son breves y un
// backoff de horas dejaría check-ins de vida varados.
export const MAX_DELAY_MS = 300_000;

export function retryDelayMs(attempts: number, rng: () => number = Math.random): number {
  const exponential = BASE_DELAY_MS * 2 ** Math.max(0, attempts - 1);
  const capped = Math.min(MAX_DELAY_MS, exponential);
  const factor = 0.5 + rng(); // 0.5x–1.5x
  return Math.round(Math.min(MAX_DELAY_MS, capped * factor));
}
