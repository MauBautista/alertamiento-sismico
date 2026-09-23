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

import type { MapEpicenter } from "@takab/sdk";

import type { LiveIncident } from "../console/useLiveIncidents";
import { QUORUM_MIN_NODES } from "../console/wavefront";

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
 * [T-8.10 · A-063] LA MISMA REGLA QUE EL TELÉFONO, escrita una vez.
 *
 * Espejo de `api/src/takab_api/incident/autoridad.py::autoriza_evacuacion`, que
 * es la que `mobile_state` aplica para decidir si el teléfono dice «EVACÚE»:
 * autoriza el WR-1 de SASMEX, el trigger `quorum`, **o** un incidente cuyo
 * evento enlazado lleve `node_count ≥ quorum_min_nodes`. Esa tercera rama es la
 * que faltaba aquí. El motor de correlación NO reescribe `trigger` —solo enlaza
 * `event_id` y escribe `meta.node_count`—, así que un incidente que nace
 * `local_threshold` y la red corrobora seguía siendo un aviso para la consola:
 * panel del gabinete rojo, teléfono «EVACÚE», muro ámbar «SIN ACTUACIÓN».
 *
 * `minNodes` es el `quorum_min_nodes` del servidor (Settings, por defecto 3).
 * La consola no lo lee de ninguna parte: usa el mismo espejo que el mapa
 * (`QUORUM_MIN_NODES`, blueprint §4.5). Si un despliegue lo sube, el defecto
 * que produce es el prudente —la consola llama aviso a lo que el teléfono ya
 * trata como alerta—, no el contrario.
 *
 * Default-deny: un origen desconocido sin corroboración no autoriza nada.
 */
export function autorizaEvacuacion(
  trigger: string | null | undefined,
  nodeCount: number | null,
  minNodes: number = QUORUM_MIN_NODES,
): boolean {
  if (trigger === "sasmex" || trigger === "quorum") return true;
  return nodeCount !== null && nodeCount >= minNodes;
}

/**
 * Lo que la consola sabe de la corroboración de un evento: su id y cuántas
 * estaciones lo formaron. Viaja en el epicentro del snapshot del mapa
 * (`GET /telemetry/map/state`, `(e.meta->>'node_count')::int`), que sale de la
 * MISMA columna que lee `mobile_state` (`queries/mobile.py::OPEN_INCIDENT`).
 */
export type Corroboracion = Pick<MapEpicenter, "event_id" | "node_count">;

/**
 * Las estaciones que corroboraron el evento de ESTE incidente, o `null` si no
 * se sabe: sin evento enlazado, sin ese evento en el snapshot, o un evento que
 * no es de cuórum. `null` y no `0`: una cuenta ausente no es una cuenta de cero.
 */
export function nodosQueCorroboran(
  incident: Pick<LiveIncident, "event_id">,
  epicentros: readonly Corroboracion[],
): number | null {
  if (incident.event_id === null) return null;
  const epicentro = epicentros.find((e) => e.event_id === incident.event_id);
  return epicentro?.node_count ?? null;
}

/**
 * ¿Este incidente AUTORIZA actuar? SASMEX (contacto seco del WR-1), el cuórum de
 * la red, o un aviso que la red corroboró. Una estación sola sólo avisa
 * (T-2.32), una activación manual es una persona, y un origen no reconocido no
 * autoriza nada (default-deny).
 *
 * `epicentros` es OBLIGATORIO a propósito: con un `= []` por defecto, el
 * llamador que no supiera de la tercera rama se llevaba la regla vieja sin que
 * nada se pusiera rojo — que es exactamente como se abrió A-063.
 */
export function authorizes(
  incident: Pick<LiveIncident, "trigger" | "event_id">,
  epicentros: readonly Corroboracion[],
): boolean {
  return autorizaEvacuacion(incident.trigger, nodosQueCorroboran(incident, epicentros));
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

/** Las tres formas de estar en pantalla un incidente crítico abierto. */
export type AlertKind = "alert" | "notice" | "review";

/**
 * De qué clase es este incidente: `alert` si autoriza, `notice` si no, y
 * `review` en cuanto el SERVIDOR lo pasa a `in_review` — nunca por un cronómetro
 * del cliente (`D-33`, T-7.13).
 *
 * La revisión GANA a la autoridad de la fuente, y no al revés: un incidente que
 * el servidor ya movió a revisión es un sismo que CONCLUYÓ, y seguir pintándolo
 * rojo como «PROTÉJASE» es pintar como vigente lo que el servidor ya no sostiene
 * (regla de oro 7). Que lo abriera el WR-1 no lo devuelve a la alerta.
 */
export function alertKind(
  incident: LiveIncident | null,
  epicentros: readonly Corroboracion[],
): AlertKind | null {
  if (incident === null) return null;
  if (incident.state === "in_review") return "review";
  return authorizes(incident, epicentros) ? "alert" : "notice";
}

/**
 * En qué CASILLA de `SCENE_PRECEDENCE` cae cada clase. La tabla no cambia
 * (T-7.16): lo que cambia es de dónde se entra a ella.
 *
 * `review` entra por `notice`, y es la casilla correcta por lo que `notice`
 * significa aquí: «se declara con su titular honesto, pero no degrada nada». Una
 * revisión ya no autoriza actuar —la sacudida terminó, nadie tiene que
 * evacuar—, así que tampoco puede tapar al simulacro que el equipo retomó ni
 * robarle la franja al mantenimiento. Meterla en `alert` mantendría degradado el
 * banner ámbar del simulacro después de que el sismo acabara, que es justo el
 * ruido que `DEGRADES_UNDER_ALERT` existe para quitar en el peor momento y no
 * después.
 */
export function sceneSlot(kind: AlertKind | null): { alert: boolean; notice: boolean } {
  return { alert: kind === "alert", notice: kind === "notice" || kind === "review" };
}
