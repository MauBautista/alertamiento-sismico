// [T-6.01] LA ESCENA: qué está pasando en el tenant, decidido en UN solo sitio.
//
// Hasta esta ficha los cuatro banners —alerta real, simulacro, ventana de
// mantenimiento y modo demostración— eran hijos de `ConsolePage` con dos
// booleanos a mano (`hasLiveIncident={critical !== null}`), y el shell sólo
// montaba el aviso de privacidad. En `/fleet`, `/triage`, `/tenants`, `/audit` y
// `/building` no había rastro de que la nube no avisa a nadie, de que el edificio
// vocea, ni de que hay una alerta (U-04). Y el badge «LA ALERTA REAL DOMINA» se
// pintaba con CUALQUIER incidente crítico, incluido un aviso instrumental que por
// política ratificada (T-2.32) no manda sobre nada (U-28).
//
// Misma doctrina que `STATE_PRECEDENCE` (`components/StateFrame.tsx`): una
// TABLA, un único `resolveScene`, y un censo (`src/sceneCensus.test.ts`) que
// impide que una pantalla decida la escena por su cuenta. La franja que la pinta
// vive en el shell (`SceneStrip.tsx`), encima de las seis rutas.
//
// NORMAL NO ESTÁ EN LA TABLA A PROPÓSITO: es la ausencia de escena, y se pinta
// como ausencia de franja (U-45). Una consola que dedica dos franjas permanentes
// a decir «SIN SIMULACRO» y «SIN VENTANA» enseña al operador a no leerlas.

import type { LiveIncident } from "../console/useLiveIncidents";

/**
 * LA PRECEDENCIA, como tabla y no como cadena de `if`. De mayor a menor:
 *
 *   alert        — incidente crítico de una fuente que AUTORIZA actuar
 *                  (SASMEX o cuórum de la red). Lo real domina.
 *   notice       — incidente crítico que NO autoriza: aviso instrumental de una
 *                  sola estación, activación manual, origen no reconocido. Se
 *                  declara con su titular honesto, pero no degrada nada.
 *   drill        — simulacro EN CURSO (acusado por algún gabinete o no: el
 *                  banner dice cuál).
 *   maintenance  — ventana de mantenimiento viva: hay alarmas mudas.
 *   demo         — modo demostración: la nube no avisa a nadie ni acciona.
 */
export const SCENE_PRECEDENCE = ["alert", "notice", "drill", "maintenance", "demo"] as const;

export type SceneKind = (typeof SCENE_PRECEDENCE)[number];
export type Scene = SceneKind | "normal";

export type SceneInputs = Record<SceneKind, boolean>;

/**
 * El ÚNICO sitio donde se decide qué escena manda. Recorre `SCENE_PRECEDENCE`
 * en orden: cambiar la tabla cambia la conducta de la franja en las seis rutas.
 */
export function resolveScene(inputs: SceneInputs): Scene {
  for (const scene of SCENE_PRECEDENCE) {
    if (inputs[scene]) return scene;
  }
  return "normal";
}

/**
 * LA EXCEPCIÓN ESCRITA: qué se degrada cuando manda la alerta real y qué no.
 *
 * El simulacro sí: con lo real vivo, el banner ámbar pasa a un badge discreto
 * («LA ALERTA REAL DOMINA») porque un simulacro que compite visualmente con la
 * alerta es ruido en el peor momento. El mantenimiento NO: el instante en que
 * más falta hace saber que una alarma no va a sonar es justo el sismo
 * (precedente literal: el `banner-wr1` violeta del panel LAN, T-1.69). El modo
 * demostración tampoco: quien no lo encendió es quien se pregunta por qué no le
 * llegó el aviso, y eso pasa DURANTE la alerta. Y un aviso que no autoriza no
 * puede quedar tapado por lo que sí autoriza: es otra estación diciendo algo.
 */
export const DEGRADES_UNDER_ALERT: Readonly<Record<Exclude<SceneKind, "alert">, boolean>> = {
  notice: false,
  drill: true,
  maintenance: false,
  demo: false,
};

/**
 * LA RUTA DEL WALL. La línea de alerta de la franja es el ECO de la tarjeta
 * detallada del wall (`AlertBanner`: titular, sitio, EVENT_ID, PGA) para las
 * cinco rutas que no la tienen. En el wall no hay eco: la tarjeta ya está
 * anclada al escenario, y cada píxel de alto que la franja tomara ahí se lo
 * quitaría al mapa — que es lo que T-1.62, T-2.57 y [D3] cerraron tres veces
 * (medido a 1280×800: 42 px de línea dejaban el escenario en su piso y los
 * sobrepuestos del mapa se pisaban). El simulacro, el mantenimiento y la demo
 * SÍ van también en el wall: allí no tienen otra voz.
 */
export const WALL_ROUTE = "/console";

/**
 * ¿Esta fuente AUTORIZA actuar? Sólo SASMEX (contacto seco del WR-1) y el
 * cuórum de la red (comando firmado). Una estación sola sólo avisa (T-2.32), una
 * activación manual es una persona, y un origen no reconocido no autoriza nada
 * (default-deny). Espejo de `mobile/src/features/alert/source.ts`.
 */
export function authorizes(trigger: string | null | undefined): boolean {
  return trigger === "sasmex" || trigger === "quorum";
}

/**
 * El incidente que DEFINE la escena de alerta: el crítico más relevante de la
 * cola (que `mergeIncidents` ya ordena por severidad y frescura). Es la misma
 * elección que hacía `ConsolePage` a mano; ahora la hace la tabla y la consola
 * la consume para su tarjeta detallada.
 */
export function sceneAlert(incidents: readonly LiveIncident[]): LiveIncident | null {
  return incidents.find((i) => i.severity === "critical") ?? null;
}

/** De qué escena es este incidente: `alert` si autoriza, `notice` si no. */
export function alertKind(incident: LiveIncident | null): "alert" | "notice" | null {
  if (incident === null) return null;
  return authorizes(incident.trigger) ? "alert" : "notice";
}
