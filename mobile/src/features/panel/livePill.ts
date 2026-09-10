// [T-6.25 · U-22] QUÉ DICE —Y SI LATE— EL PILL DEL PANEL TÁCTICO.
//
// El pill salía sólo del estado del WEBSOCKET: `ready` ⇒ «LIVE», en verde,
// para siempre. Pero un canal abierto por el que no llega nada no es un canal
// vivo, y la propia pantalla ya lo sabía —imprime «Frame recibido hace X» dos
// tarjetas más abajo— sin que el pill se enterara. Dos afirmaciones sobre el
// mismo hecho, y la grande era la optimista (regla de oro 7).
//
// Puro y con el reloj por parámetro: lo que decide es la EDAD del último frame,
// y eso se prueba sin esperar.

/** Estado del canal live, tal y como lo reporta el socket. */
export type LivePill = "ready" | "connecting" | "closed";

/**
 * Cuánto puede tener el último frame para que el pill siga afirmando LIVE.
 *
 * Las features llegan a 1 s (`features 1 s, sin forma de onda`), así que cinco
 * segundos son cinco frames perdidos: lo bastante para no parpadear con el
 * jitter de una red móvil y lo bastante poco para que «LIVE» siga queriendo
 * decir algo.
 */
export const FRAME_FRESCO_MS = 5_000;

export interface EstadoPill {
  /** Rótulo que se pinta. */
  label: string;
  /** Tono: el pill es el PORTADOR, y el color solo acompaña. */
  tone: "ok" | "warn" | "crit";
  /** Si el punto late. Latir es afirmar «esto está llegando ahora». */
  late: boolean;
}

/**
 * `featuresAtMs === null` = jamás llegó un frame. No es lo mismo que uno viejo
 * y no se pinta igual: «SIN FRAMES» describe una ausencia, no un retraso.
 */
export function estadoPill(
  live: LivePill,
  featuresAtMs: number | null,
  nowMs: number,
): EstadoPill {
  if (live === "closed") {
    return { label: "SIN CANAL LIVE", tone: "crit", late: false };
  }
  if (live === "connecting") {
    return { label: "RECONECTANDO…", tone: "warn", late: false };
  }
  if (featuresAtMs === null) {
    return { label: "CANAL ABIERTO · SIN FRAMES", tone: "warn", late: false };
  }
  if (nowMs - featuresAtMs > FRAME_FRESCO_MS) {
    // El canal sigue abierto y eso NO es mentira; lo que no se puede afirmar es
    // que el dato de la pantalla esté llegando ahora.
    return { label: "LIVE · SIN FRAMES RECIENTES", tone: "warn", late: false };
  }
  return { label: "LIVE", tone: "ok", late: true };
}
