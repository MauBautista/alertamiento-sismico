/**
 * [T-2.134] CUÁNTO ESPERAR ANTES DE VOLVER A PREGUNTAR POR `/me`.
 *
 * `T-2.123` dejó la consola arrancando en degradado con la base caída, y con un
 * botón REINTENTAR. El botón exige que alguien esté mirando: en un incidente
 * —que es cuando esto ocurre— puede que nadie mire la pantalla en media hora, y
 * la consola se quedaría degradada con la base ya de vuelta.
 *
 * Reintentar solo es fácil; reintentar solo SIN empeorar la caída es la ficha:
 *
 *  · **Suelo.** El primer reintento no es inmediato. Una base que está
 *    arrancando, recuperando WAL o reeligiendo primario es exactamente a la que
 *    no se le añade un cliente en bucle.
 *  · **Crecimiento exponencial.** Si sigue caída a los 40 s, no hay motivo para
 *    preguntar tan seguido como al segundo 5.
 *  · **Techo.** Sin él, una caída de 40 min dejaría el siguiente reintento a 20
 *    min de distancia: la base de vuelta y el operador mirando una pantalla
 *    degradada. El techo es lo que acota cuánto puede tardar la consola en
 *    darse cuenta de que ya se puede trabajar.
 *  · **Jitter, que es el que casi se olvida.** El fallo no es de un navegador:
 *    todas las consolas de todos los tenants pierden `/me` en el MISMO instante,
 *    así que un backoff determinista las sincroniza en un tropel que golpea a la
 *    vez. El jitter las dispersa.
 *
 * Lo que este módulo NO hace, y es deliberado: no desmonta nada. El reintento
 * pasa por `refreshMe`, que desde `degraded` NO vuelve a `booting` (T-2.123), así
 * que la pantalla que está declarando el problema sigue montada y el operador no
 * ve un parpadeo por intento.
 */

/** Retardo nominal del PRIMER reintento. */
export const BASE_MS = 5_000;

/** Techo del retardo nominal: cuánto puede tardar como mucho en volver a mirar. */
export const TOPE_MS = 60_000;

/**
 * Retardo (ms) antes del reintento número `intentosFallidos + 1`.
 *
 * `aleatorio` se inyecta para poder fijar el reparto en el test: en producción
 * es `Math.random`.
 */
export function retryDelayMs(
  intentosFallidos: number,
  aleatorio: () => number = Math.random,
): number {
  const n = Math.max(0, Math.floor(intentosFallidos));
  // `2 ** n` con n grande se va a Infinity; el `min` lo corta antes de que el
  // producto llegue a importar.
  const nominal = Math.min(BASE_MS * 2 ** Math.min(n, 32), TOPE_MS);
  const mitad = nominal / 2;
  return mitad + aleatorio() * mitad;
}
