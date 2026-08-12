// [T-2.82.a] UN SOLO RELOJ PARA LA PANTALLA DONDE SE FIRMA UN DICTAMEN.
//
// Ocho marcos, cuatro consultas y tres hooks distintos alimentan esa pantalla, y
// cada uno podría fabricarse su propio veredicto de frescura. No se hace, por la
// misma razón por la que `STATE_PRECEDENCE` decide para toda la consola quién
// gana entre `empty` y `stale` (T-2.79.d): un panel que se escribe su propio
// deslinde es el primer paso para que se escriba también su propia precedencia,
// y este repo ya pagó esa deriva una vez.

/**
 * Cuándo se declara viejo el dato que el inspector lee antes de firmar.
 *
 * MEDIDO, y es lo que fija el número: en esta consola NADA refresca sola esa
 * pantalla. `lib/queryClient.ts` desactiva `refetchOnWindowFocus` (es un
 * videowall, no un escritorio) y ninguna de las consultas del triage lleva
 * `refetchInterval`; la única vía de refresco es montar la pantalla o pulsar
 * REINTENTAR. Es decir: los ocho marcos envejecen A LA MISMA VELOCIDAD desde
 * que se abrió el detalle.
 *
 * De ahí las dos decisiones:
 *
 *  · UN SOLO UMBRAL para las consultas del detalle. Con relojes distintos, esos
 *    paneles se irían encendiendo escalonadamente y el inspector leería que unos
 *    siguen vigentes mientras otros no — cuando la verdad es que a nadie se le
 *    ha vuelto a preguntar. La franja sale de golpe porque el detalle entero
 *    dejó de confirmarse de golpe.
 *
 *    UNA EXCEPCIÓN, Y ES LO CONTRARIO DE UNA DERIVA: la FILA del incidente no
 *    sale de aquí sino de `/incidents`, que tiene su propio `staleTime`
 *    (`TRIAGE_STALE_MS`) y a la que `TriagePage` ya le calcula la edad para
 *    fechar el HISTORIAL. El panel del quórum, cuando el incidente no referencia
 *    evento, habla de esa fila — así que hereda ESA edad. Un dato, un veredicto:
 *    darle el reloj del detalle sería fechar el mismo dato de dos maneras
 *    distintas en la misma pantalla, que es peor que tener dos umbrales.
 *  · QUINCE MINUTOS, no dos. Es MAYOR que el `staleTime` más largo de la
 *    pantalla (`useForensics`, 300 000 ms): si el rótulo saltara antes de que
 *    la propia consulta se considere refrescable, acusaría de congelado a un
 *    dato que está dentro de su ventana normal. Un aviso permanentemente
 *    encendido se deja de leer, y con él el día que sí importa.
 */
export const SIGNING_STALE_MS = 900_000;

/**
 * El veredicto de frescura, escrito UNA vez: epoch ms de la última respuesta
 * buena cuando ya se considera vieja, `null` mientras siga fresca.
 *
 * El guard de `dataUpdatedAt <= 0` no es cosmético: react-query deja ese campo
 * en 0 mientras no ha llegado NADA (consulta en vuelo, o `enabled:false`), y
 * restar contra el epoch daría «viejo desde 1970» en un panel que ni siquiera
 * tiene dato del que hablar. Inventar una edad es la misma clase de mentira que
 * ocultarla.
 */
export function staleSinceOf(
  dataUpdatedAt: number,
  now: number,
  thresholdMs: number = SIGNING_STALE_MS,
): number | null {
  if (dataUpdatedAt <= 0) {
    return null;
  }
  return now - dataUpdatedAt > thresholdMs ? dataUpdatedAt : null;
}
