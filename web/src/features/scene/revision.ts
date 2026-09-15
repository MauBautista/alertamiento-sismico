// [T-7.20] LAS PALABRAS DE LA REVISIÓN, en un solo sitio.
//
// Vivían dentro de `ReviewLine.tsx`, que es la línea de la franja — y la franja
// NO se pinta en el muro (`SceneStrip`: `{!wall && …}`, porque allí la alerta ya
// tiene su tarjeta anclada al escenario). El resultado, medido en la corrida
// real de `web/e2e/vida_del_sismo.spec.ts`: en las otras cinco rutas la consola
// decía «SISMO CONCLUIDO · ANALIZANDO», y en el videowall —la pantalla que
// alguien mira de pie— seguía diciendo «ALERTA SÍSMICA · PROTÉJASE» con el sismo
// ya terminado. Sólo se paraba el halo.
//
// Es la regla de oro 7 en la superficie más visible del producto: pintar como
// vigente lo que el servidor ya no sostiene. Así que las palabras salen de aquí
// y las usan las DOS superficies; separarlas otra vez sería garantizar que
// vuelvan a divergir.

/**
 * Pasado esto sin que nadie clasifique, se habla EN PASADO.
 *
 * No cierra nada ni cambia ningún estado —eso es del servidor, siempre
 * (`incident_review_ttl_s`)—: cambia las PALABRAS. Un «ANALIZANDO» en presente
 * doce horas después del sismo dice que hay alguien mirando ahora mismo, y no lo
 * hay; con el TTL del servidor en su valor normal este caso ni se alcanza,
 * porque el registro ya estaría cerrado. Se alcanza justo cuando alguien puso el
 * TTL a cero para exigir cierre humano, que es cuando más importa no mentir.
 */
export const REVIEW_PASADO_MS = 6 * 3600_000;

/** `mm:ss` mientras cabe; `h:mm` en cuanto pasa de una hora. Sin decimales. */
export function transcurrido(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h > 0) return `${h}:${String(m).padStart(2, "0")} h`;
  return `${String(m).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

/** Edad del incidente en ms, o `null` si no se puede saber. Nunca se inventa. */
export function edadDelSismo(openedAt: string, now: number): number | null {
  const desde = Date.parse(openedAt);
  return Number.isNaN(desde) ? null : now - desde;
}

/** El titular de la revisión. Es la única frase, y la dicen las dos superficies. */
export function tituloRevision(edadMs: number | null): string {
  return edadMs !== null && edadMs > REVIEW_PASADO_MS
    ? "SISMO CONCLUIDO · SIN CLASIFICAR"
    : "SISMO CONCLUIDO · ANALIZANDO";
}
