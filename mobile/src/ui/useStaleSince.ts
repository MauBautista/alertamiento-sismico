// La edad de un dato sale del RELOJ, no de que algo haya fallado (T-5.21).
//
// EL DEFECTO QUE ESTO CIERRA, y era más grande de lo que su ficha decía: en la
// app, `stale` significaba «la consulta está fallando». `useAlertState` lo
// calculaba como `isError && data !== undefined` y **siete pantallas lo
// heredaban**; `lista.tsx` y `dictamen.tsx` hacían lo propio con
// `failureCount > 0`. Con red sana y un `mobile_state` de hace diez minutos,
// todas esas señales valen `false` y la pantalla **afirma frescura**.
//
// Es la misma familia que `T-2.59` en la consola —«● LIVE» con el SOC mudo— y
// justo lo que la regla de oro 7 existe para impedir: un dato congelado pintado
// como vivo es peor que no tener dato.
//
// POR QUÉ EL UMBRAL SALE DEL INTERVALO DE POLL Y NO ES UN NÚMERO
// ---------------------------------------------------------------
// «Viejo» no es una cantidad de segundos: es **«ya deberíamos haber refrescado y
// no lo hicimos»**. Una pantalla que consulta cada 5 s y otra cada 30 envejecen
// a ritmos distintos, y un umbral fijo mentiría en una de las dos. Tres pollos
// perdidos es la regla: uno es jitter, tres son un patrón.

import { useEffect, useState } from "react";

/** Pollos perdidos que hacen viejo un dato. Uno es jitter; tres, un patrón. */
export const FACTOR_DE_VEJEZ = 3;

/** Cada cuánto se re-evalúa la edad. Basta para «hace X min». */
const TIC_MS = 30_000;

/**
 * Epoch ms del dato si ya es viejo, o `null` si es fresco.
 *
 * `dataUpdatedAt` en 0 devuelve `null` y **no es «fresquísimo»**: es que nunca
 * se consultó, y de eso hablan `loading` y `error`, no la frescura. Afirmar
 * vejez sobre un dato que no existe sería inventar una medición.
 */
export function staleSinceOf(
  dataUpdatedAt: number,
  nowMs: number,
  pollMs: number,
): number | null {
  if (!dataUpdatedAt) {
    return null;
  }
  // Una edad NEGATIVA sale «fresca», y es correcto aquí: `dataUpdatedAt` lo pone
  // react-query con el reloj DEL PROPIO DISPOSITIVO, el mismo que da `nowMs`, así
  // que en campo no puede haber desfase entre los dos. Un valor futuro solo
  // aparece en un test que fija un epoch a mano — y por eso los fixtures de esta
  // app cuentan el tiempo relativo a `Date.now()` y no desde un epoch clavado.
  return nowMs - dataUpdatedAt > pollMs * FACTOR_DE_VEJEZ ? dataUpdatedAt : null;
}

/**
 * La misma cuenta, con reloj propio: la pantalla se vuelve a pintar mientras el
 * dato envejece.
 *
 * Sin el tic, un dato que estaba fresco al montar seguiría pintándose fresco
 * para siempre si nada más provoca un render — que es exactamente la mitad del
 * defecto: no basta con calcular bien una vez.
 */
export function useStaleSince(
  dataUpdatedAt: number,
  pollMs: number,
  nowMsOverride?: number,
): number | null {
  const [nowMs, setNowMs] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNowMs(Date.now()), TIC_MS);
    return () => clearInterval(t);
  }, []);
  return staleSinceOf(dataUpdatedAt, nowMsOverride ?? nowMs, pollMs);
}
