// [T-9.70 · D-50] Qué trae ESTA compilación en `res/raw/alerta_oficial`: el sonido
// oficial del SASMEX («oficial»), el tono propio («propio», sin el oficial al compilar)
// o nada (`null`: compilación sin el plugin, jest, Expo Go). Lo escribe `app.config.js`
// a partir del recurso empaquetado, no de lo que se pidió.
import Constants from "expo-constants";

export type TonoDeLaCompilacion = "oficial" | "propio" | null;

/** El recurso `res/raw` que suenan el canal `alerta_oficial_v1` y el bucle de la alerta.
 *  El plugin (`plugins/tonoOficial.js`, `RECURSO`) escribe este mismo nombre. */
export const RECURSO_OFICIAL = "alerta_oficial.wav";

export function tonoOficialDeLaCompilacion(): TonoDeLaCompilacion {
  const valor: unknown = Constants.expoConfig?.extra?.tonoOficial;
  return valor === "oficial" || valor === "propio" ? valor : null;
}
