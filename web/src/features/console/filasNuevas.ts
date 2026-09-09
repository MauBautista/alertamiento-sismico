/**
 * [T-6.10 · W13] Qué filas de la cola LLEGARON mientras se estaba mirando.
 *
 * Puro y con el reloj por parámetro para que la caducidad se pueda comprobar
 * sin esperar: el rótulo `NUEVO` vive por TIEMPO, no por número de pinturas.
 * Si caducara al siguiente render, un refresco del WebSocket a los 200 ms lo
 * borraría antes de que nadie lo leyera.
 */

/**
 * Cuánto se anuncia una fila recién llegada.
 *
 * Diez segundos: lo bastante para que quien apartó la vista al mapa vuelva y lo
 * vea, y no tanto como para que dos incidentes seguidos dejen media cola
 * rotulada —momento en el que el rótulo deja de señalar nada.
 */
export const NUEVO_MS = 10_000;

/** id de la fila → instante en que apareció; `null` = ya estaba al empezar. */
export type CensoFilas = Map<string, number | null>;

/**
 * Avanza el censo y devuelve qué filas hay que anunciar ahora.
 *
 * `previo === null` es la PRIMERA pintura, y no marca nada: abrir la consola no
 * es que hayan llegado doce incidentes de golpe.
 */
export function actualizarCenso(
  previo: CensoFilas | null,
  ids: readonly string[],
  nowMs: number,
): { censo: CensoFilas; nuevas: Set<string> } {
  const censo: CensoFilas = new Map();
  const nuevas = new Set<string>();
  for (const id of ids) {
    if (previo === null) {
      censo.set(id, null);
      continue;
    }
    // Ojo con `?? nowMs`: `null` es un valor legítimo («estaba desde el
    // principio») y no una ausencia. `has` es lo que distingue las dos cosas.
    const visto = previo.has(id) ? (previo.get(id) as number | null) : nowMs;
    censo.set(id, visto);
    if (visto !== null && nowMs - visto <= NUEVO_MS) nuevas.add(id);
  }
  return { censo, nuevas };
}
