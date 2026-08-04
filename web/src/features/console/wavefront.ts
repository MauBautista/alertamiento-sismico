// [T-2.47] Frente de onda del mapa — PURO: ni React, ni MapLibre, ni DOM.
//
// Todo lo que el mapa anima sale de aquí, y se prueba sin mapa. Cuatro reglas que
// este módulo existe para hacer cumplir:
//
//  1. **`V_S` se DERIVA de `V_P`**, no se escribe a mano. Si mañana el quórum
//     cambia `quorum_v_p_km_s`, la onda S lo sigue sola. Una constante suelta
//     sería una segunda fuente de verdad, y las dos divergirían en silencio.
//  2. **Los radios son FÍSICOS (km)**, y se convierten a píxeles con la escala
//     del zoom actual. Aquí vivía el pecado que se documentó en `MapPanel.tsx`:
//     dos anillos en `circle-radius` (PÍXELES DE PANTALLA) rotulados como
//     intensidad, que afirmaban ~22 km a zoom 8.5 y ~1 km a zoom 13. La rueda del
//     ratón cambiaba el significado del dibujo.
//  3. **Coste O(1) por frame**: la geometría de las líneas se calcula cuando
//     cambian los datos y NUNCA por frame; lo que se anima es el `line-dasharray`,
//     conmutado entre arrays precomputados. 3 líneas o 300 cuestan lo mismo.
//  4. **Ninguna animación anima un dato que cambia.** El frente es una ESTIMACIÓN
//     geométrica de un modelo de una capa a partir de un origen fijo (`detected_at`
//     y el epicentro). No representa ninguna medición viva, y el mapa lo rotula.
//
// Y lo que este módulo NO hace, por prohibición explícita de `CLAUDE.md §8`:
// **no hay cuenta regresiva T-MINUS ni magnitud preliminar**. Animación sí,
// cuenta regresiva no.

import type { MapEpicenter, MapSiteState } from "@takab/sdk";

import { bearing16, haversineKm } from "../fleet/geo";
import { V_P_KM_S } from "./attenuation";

/**
 * Velocidad de la onda S (km/s), DERIVADA de la P por la razón de Poisson
 * (ν = 0.25 ⇒ V_P/V_S = √3). Con `V_P_KM_S = 6.5` da ≈ 3.753 km/s.
 *
 * Es una expresión, no un literal, precisamente para que no pueda quedarse atrás.
 */
export const V_S_KM_S = V_P_KM_S / Math.sqrt(3);

/**
 * Un frente más viejo que esto ya no describe nada que esté cruzando la red.
 *
 * Es la condición que impide los "anillos fantasma" al recargar la consola: el
 * incidente sigue abierto (por eso el epicentro llega en el snapshot), pero el
 * sismo pasó hace media hora y animarlo afirmaría que está pasando ahora.
 */
export const WAVE_MAX_AGE_S = 180;

/** Estaciones mínimas para considerar LOCALIZADO un evento de quórum (blueprint §4.5). */
export const QUORUM_MIN_NODES = 3;

/** Circunferencia ecuatorial (m) y tile de MapLibre (512 px, no 256). */
const EARTH_CIRCUMFERENCE_M = 40075016.686;
const TILE_SIZE_PX = 512;

/**
 * Metros de terreno por píxel de pantalla a esa latitud y ese zoom.
 *
 * MapLibre define el zoom sobre tiles de **512 px** (el mundo mide 512·2^z px),
 * no sobre los 256 del Web Mercator clásico: usar 256 daría el doble de radio en
 * cada anillo. `Math.abs` sobre el coseno evita un signo negativo absurdo si
 * alguien pasa una latitud fuera de rango.
 */
export function metersPerPixel(lat: number, zoom: number): number {
  const cos = Math.abs(Math.cos((lat * Math.PI) / 180));
  return (EARTH_CIRCUMFERENCE_M * cos) / (TILE_SIZE_PX * 2 ** zoom);
}

/** Radio de pantalla (px) de una distancia FÍSICA. Se recomputa en `zoomend`. */
export function kmToPixels(km: number, lat: number, zoom: number): number {
  return (km * 1000) / metersPerPixel(lat, zoom);
}

export interface WaveRadii {
  pKm: number;
  sKm: number;
}

/**
 * Radios de los frentes P y S a `elapsedS` del origen (modelo de UNA CAPA).
 *
 * El elapsed se clampa a 0: un `detected_at` en el futuro (reloj del edge a la
 * deriva, o del navegador) produciría radios negativos, y MapLibre no acepta un
 * `circle-radius` negativo.
 */
export function waveRadiiKm(elapsedS: number): WaveRadii {
  const t = elapsedS > 0 ? elapsedS : 0;
  return { pKm: V_P_KM_S * t, sKm: V_S_KM_S * t };
}

/**
 * ¿Este epicentro está LOCALIZADO de verdad?
 *
 * SASMEX es el canal autoritativo; el quórum localiza con ≥3 estaciones. Un punto
 * de catálogo (SSN/USGS) o una reubicación manual describen dónde ocurrió algo,
 * no un frente que esté cruzando la red ahora mismo: no arrancan la animación.
 */
export function isLocalized(epicenter: MapEpicenter): boolean {
  if (epicenter.source === "sasmex") return true;
  return (epicenter.node_count ?? 0) >= QUORUM_MIN_NODES;
}

/** Segundos desde el origen, o `null` si la fecha no es legible. */
export function elapsedSince(epicenter: MapEpicenter, nowMs: number): number | null {
  const ts = Date.parse(epicenter.detected_at);
  if (Number.isNaN(ts)) return null;
  return (nowMs - ts) / 1000;
}

/** Epicentros que describen un frente VIVO: localizados y dentro de la ventana. */
export function animatableEpicenters(epicenters: MapEpicenter[], nowMs: number): MapEpicenter[] {
  return epicenters.filter((e) => {
    if (!isLocalized(e)) return false;
    const elapsed = elapsedSince(e, nowMs);
    return elapsed !== null && elapsed < WAVE_MAX_AGE_S;
  });
}

export interface AnimationGate {
  epicenters: MapEpicenter[];
  nowMs: number;
  /** `prefers-reduced-motion: reduce` del sistema operativo del operador. */
  reducedMotion: boolean;
}

/**
 * ¿Debe correr la animación? Se apaga por TRES condiciones independientes:
 *
 *  1. no hay ningún epicentro LOCALIZADO (sasmex o quórum ≥3),
 *  2. el evento ya envejeció más de `WAVE_MAX_AGE_S`,
 *  3. el operador pidió `prefers-reduced-motion`.
 *
 * La 2 es la que evita el fantasma clásico: recargar la consola con un incidente
 * abierto de hace media hora NO debe pintar un frente en marcha.
 */
export function isAnimatable({ epicenters, nowMs, reducedMotion }: AnimationGate): boolean {
  if (reducedMotion) return false;
  return animatableEpicenters(epicenters, nowMs).length > 0;
}

// --- Líneas epicentro → estación ---------------------------------------------

interface LineFeature {
  type: "Feature";
  geometry: { type: "LineString"; coordinates: [number, number][] };
  properties: {
    event_id: string;
    site_id: string;
    km: number;
    bearing: string;
    label: string;
  };
}

export interface LineCollection {
  type: "FeatureCollection";
  features: LineFeature[];
}

/**
 * Una línea por par (epicentro, estación), con la distancia y el rumbo MEDIDOS.
 *
 * Se calcula solo cuando cambian los datos. Lo que se anima después es el
 * `line-dasharray` de la capa entera — un `setPaintProperty` por frame,
 * independientemente de cuántas líneas haya.
 */
export function epicenterLinks(epicenters: MapEpicenter[], sites: MapSiteState[]): LineCollection {
  const features: LineFeature[] = [];
  for (const e of epicenters) {
    for (const s of sites) {
      const km = haversineKm({ lon: e.lon, lat: e.lat }, { lon: s.lon, lat: s.lat });
      const bearing = bearing16({ lon: e.lon, lat: e.lat }, { lon: s.lon, lat: s.lat });
      features.push({
        type: "Feature",
        geometry: {
          type: "LineString",
          coordinates: [
            [e.lon, e.lat],
            [s.lon, s.lat],
          ],
        },
        properties: {
          event_id: e.event_id,
          site_id: s.site_id,
          km,
          bearing,
          label: `${km.toFixed(0)} km · ${bearing}`,
        },
      });
    }
  }
  return { type: "FeatureCollection", features };
}

// --- Dash conmutado -----------------------------------------------------------

/** Milisegundos entre conmutaciones del dash (≈8 pasos/s: se lee, no parpadea). */
export const DASH_STEP_MS = 125;

/**
 * Secuencia PREcomputada de `line-dasharray` que produce la marcha del guion.
 *
 * Es la única forma barata de animar una línea en MapLibre: la alternativa
 * (re-escribir la geometría con un offset por frame) cuesta O(nº de líneas) por
 * frame y obliga a un `setData` completo. Aquí se conmuta una propiedad de pintura
 * de la CAPA: O(1) haya 3 líneas o 300.
 */
export const DASH_FRAMES: readonly (readonly number[])[] = [
  [0, 4, 3],
  [0.5, 4, 2.5],
  [1, 4, 2],
  [1.5, 4, 1.5],
  [2, 4, 1],
  [2.5, 4, 0.5],
  [3, 4, 0],
  [0, 0.5, 3, 3.5],
  [0, 1, 3, 3],
  [0, 1.5, 3, 2.5],
  [0, 2, 3, 2],
  [0, 2.5, 3, 1.5],
  [0, 3, 3, 1],
  [0, 3.5, 3, 0.5],
];

/** Fotograma del dash. Delta negativo (vsync previo al `start`) se clampa a 0. */
export function dashFrameIndex(elapsedMs: number): number {
  const ms = elapsedMs > 0 ? elapsedMs : 0;
  return Math.floor(ms / DASH_STEP_MS) % DASH_FRAMES.length;
}

// --- Modo accesible: anillos quietos ------------------------------------------

/** Marcas de tiempo de los anillos estáticos (s desde el origen). */
export const STATIC_RING_MARKS_S: readonly number[] = [5, 10, 20];

export interface StaticRing {
  seconds: number;
  phase: "P" | "S";
  km: number;
  label: string;
}

/**
 * Anillos QUIETOS para `prefers-reduced-motion`: el interruptor apaga el
 * movimiento, no la información.
 *
 * Los radios son EXACTAMENTE los que tendría la animación en esos instantes
 * (`waveRadiiKm`): si difirieran, la versión accesible estaría contando otra
 * historia que la animada, y una de las dos sería falsa.
 */
export function staticRings(): StaticRing[] {
  const rings: StaticRing[] = [];
  for (const seconds of STATIC_RING_MARKS_S) {
    const { pKm, sKm } = waveRadiiKm(seconds);
    rings.push({ seconds, phase: "P", km: pKm, label: `P +${seconds}s` });
    rings.push({ seconds, phase: "S", km: sKm, label: `S +${seconds}s` });
  }
  return rings;
}
