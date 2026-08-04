// [T-2.46] Enlace con la estación — lógica PURA (sin React, sin MapLibre).
//
// El mapa coloreaba cada punto por la sacudida que ESE edificio midió (`felt`) y
// no decía nada sobre si su gabinete sigue vivo. Un punto verde podía significar
// "todo bien" o "llevo seis horas sin datos y este color es un recuerdo" — que es
// exactamente lo que prohíbe la regla de oro 7.
//
// Dos decisiones de diseño que este módulo materializa:
//
//  1. **El enlace NO usa el canal de color.** Ese canal ya lo ocupa `felt`, y son
//     dos hechos ortogonales (uno mide el suelo, otro la red). El enlace se dice
//     con OPACIDAD + NÚCLEO HUECO + un GLIFO propio. Un punto con el enlace caído
//     tiene que verse como lo que es: un color que ya no es una lectura viva.
//  2. **`SIN GABINETE` no se colapsa con `SIN ENLACE`.** "No hay hardware" y "el
//     hardware calló" mandan a sitios distintos a personas distintas.
//
// El ESTADO lo deriva el servidor (`derive_fleet_state`, verdad única). Aquí solo
// se decide cómo se pinta y cómo se lee.

import type { MapSiteState } from "@takab/sdk";

export const LINK_OPERATIVO = "OPERATIVO";
export const LINK_DEGRADADO = "DEGRADADO";
export const LINK_SIN_ENLACE = "SIN ENLACE";
export const LINK_SIN_GABINETE = "SIN GABINETE";

export type LinkState =
  | typeof LINK_OPERATIVO
  | typeof LINK_DEGRADADO
  | typeof LINK_SIN_ENLACE
  | typeof LINK_SIN_GABINETE;

const KNOWN: readonly string[] = [
  LINK_OPERATIVO,
  LINK_DEGRADADO,
  LINK_SIN_ENLACE,
  LINK_SIN_GABINETE,
];

/**
 * Estado de enlace de la estación tal como lo declaró el servidor.
 *
 * El default es `SIN GABINETE` a propósito: un snapshot que no trae el campo (o
 * que trae un valor que esta versión de la consola no conoce) NO autoriza a
 * afirmar un enlace vivo. Degradar hacia "no sé" es honesto; degradar hacia
 * "OPERATIVO" sería inventar salud.
 */
export function siteLink(site: Pick<MapSiteState, "link_state">): LinkState {
  const raw = site.link_state;
  return raw !== undefined && KNOWN.includes(raw) ? (raw as LinkState) : LINK_SIN_GABINETE;
}

/** ¿El punto sigue reportando? DEGRADADO sí: reporta, aunque con una métrica fea. */
export function isLinkLive(state: LinkState): boolean {
  return state === LINK_OPERATIVO || state === LINK_DEGRADADO;
}

/** Enlace caído: el color de sacudida ya no es una lectura viva, es un recuerdo. */
export function isLinkDown(state: LinkState): boolean {
  return !isLinkLive(state);
}

/** Glifo del enlace. El sano no lleva ninguno: el ruido visual se reserva al problema. */
export const LINK_GLYPH: Record<LinkState, string> = {
  [LINK_OPERATIVO]: "",
  [LINK_DEGRADADO]: "▲",
  [LINK_SIN_ENLACE]: "⊘",
  [LINK_SIN_GABINETE]: "○",
};

/** Rótulo largo del estado, para leyendas y tarjetas. */
export const LINK_LABEL: Record<LinkState, string> = {
  [LINK_OPERATIVO]: "ENLACE VIVO",
  [LINK_DEGRADADO]: "ENLACE DEGRADADO",
  [LINK_SIN_ENLACE]: "SIN ENLACE · DATO NO VIVO",
  [LINK_SIN_GABINETE]: "SIN GABINETE INSTALADO",
};

// Opacidades: MapLibre valida 0..1 estrictamente y rechaza cualquier cosa fuera
// de rango (mismo defecto que cazó el pulso en T-1.50). Son constantes, no
// cálculos, para que no haya forma de salirse.
const CORE_OPACITY: Record<LinkState, number> = {
  [LINK_OPERATIVO]: 1,
  [LINK_DEGRADADO]: 0.8,
  [LINK_SIN_ENLACE]: 0.4,
  [LINK_SIN_GABINETE]: 0.35,
};

/** Opacidad del núcleo del punto: cuanto más muerto el enlace, más apagado. */
export function coreOpacity(state: LinkState): number {
  return CORE_OPACITY[state];
}

/** Opacidad del halo. Siempre por debajo del núcleo — si no, deja de ser halo. */
export function haloOpacity(state: LinkState): number {
  return CORE_OPACITY[state] * 0.18;
}

/** Mapeo al `kind` de `LinkPill` (que solo tiene ok|crit, a propósito: los
 * umbrales finos viven en el servidor). Solo OPERATIVO es "ok". */
export function linkPillKind(state: LinkState): "ok" | "crit" {
  return state === LINK_OPERATIVO ? "ok" : "crit";
}

export interface HeartbeatAge {
  /** Texto listo para pantalla, en el idioma del wall. */
  text: string;
  /** Segundos transcurridos, o `null` si no hay latido del que medir edad. */
  seconds: number | null;
}

/**
 * EDAD del último latido, no su timestamp.
 *
 * "12:03:41 UTC" obliga al operador a restar mentalmente para saber si eso fue
 * hace un segundo o hace seis horas; "HACE 6 h" no. Un timestamp futuro (reloj
 * a la deriva) se clampa a 0 en vez de imprimir una edad negativa, y una fecha
 * ilegible se declara ausente en vez de convertirse en `NaN` por la pantalla.
 */
export function heartbeatAge(iso: string | null | undefined, nowMs: number): HeartbeatAge {
  const ausente: HeartbeatAge = { text: "SIN LATIDO REGISTRADO", seconds: null };
  if (iso === null || iso === undefined) return ausente;
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return ausente;
  const seconds = Math.max(0, Math.floor((nowMs - ts) / 1000));
  if (seconds < 90) return { text: `HACE ${seconds} s`, seconds };
  if (seconds < 5400) return { text: `HACE ${Math.floor(seconds / 60)} min`, seconds };
  return { text: `HACE ${Math.floor(seconds / 3600)} h`, seconds };
}
