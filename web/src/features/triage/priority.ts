// Prioridad SUGERIDA de inspección (T-2.40), inspirada en el Facility Assessment de
// USGS ShakeCast: tras un sismo, un responsable de cartera necesita saber POR DÓNDE
// EMPEZAR, no leer veinte fichas.
//
// La diferencia con ShakeCast es que aquí no hay ShakeMap interpolado: cada sitio
// tiene su propio acelerómetro, así que la sacudida es MEDIDA, no estimada. Eso hace
// la señal mejor y el alcance menor (solo sitios instrumentados).
//
// ESTO NO ES UN DICTAMEN. El dictamen es una fila append-only, versionada y firmada
// por un inspector (`dictamens`). Esto es un orden de atención derivado de dos hechos
// —cuánto se sacudió y qué tan crítico es el inmueble— y la pantalla lo dice con esas
// palabras. Confundirlos sería exactamente el error que la regla de oro 1 evita.

import { feltLabelOf, PGA_TRIP_G, PGA_WATCH_G } from "./model";
import type { TriageRow } from "./model";

export type PriorityLevel = "rojo" | "naranja" | "amarillo" | "verde" | "gris";

export interface PriorityView {
  level: PriorityLevel;
  label: string;
  /** Qué combinación produjo este nivel: el operador no tiene que adivinarlo. */
  why: string;
}

export const PRIORITY_LABEL: Record<PriorityLevel, string> = {
  rojo: "INSPECCIÓN INMEDIATA",
  naranja: "INSPECCIÓN PRIORITARIA",
  amarillo: "REVISIÓN PROGRAMADA",
  verde: "SIN PRIORIDAD",
  gris: "SIN MEDICIÓN",
};

/** Orden de atención: lo urgente primero, y lo desconocido ANTES que lo sano. */
export const PRIORITY_RANK: Record<PriorityLevel, number> = {
  rojo: 0,
  naranja: 1,
  gris: 2,
  amarillo: 3,
  verde: 4,
};

const HIGH_CRITICALITY = new Set(["critical", "high"]);

/**
 * Sacudida medida × criticidad del inmueble.
 *
 * Sin PGA el nivel es **gris**, jamás verde: "no midió" y "no se sacudió" son cosas
 * distintas, y pintar de verde un hospital cuyo sensor estaba mudo es exactamente la
 * clase de dato falso que prohíbe la regla de oro 7.
 */
export function inspectionPriority(
  maxPgaG: number | null | undefined,
  criticality: string | null | undefined,
): PriorityView {
  const critical = HIGH_CRITICALITY.has((criticality ?? "").toLowerCase());

  if (maxPgaG === null || maxPgaG === undefined) {
    return {
      level: "gris",
      label: PRIORITY_LABEL.gris,
      why: "El sitio no reportó aceleración en la ventana del evento.",
    };
  }
  if (maxPgaG >= PGA_TRIP_G) {
    return critical
      ? {
          level: "rojo",
          label: PRIORITY_LABEL.rojo,
          why: `Sacudida fuerte (${maxPgaG.toFixed(3)} g) en inmueble de criticidad alta.`,
        }
      : {
          level: "naranja",
          label: PRIORITY_LABEL.naranja,
          why: `Sacudida fuerte (${maxPgaG.toFixed(3)} g).`,
        };
  }
  if (maxPgaG >= PGA_WATCH_G) {
    return critical
      ? {
          level: "naranja",
          label: PRIORITY_LABEL.naranja,
          why: `Sacudida moderada (${maxPgaG.toFixed(3)} g) en inmueble de criticidad alta.`,
        }
      : {
          level: "amarillo",
          label: PRIORITY_LABEL.amarillo,
          why: `Sacudida moderada (${maxPgaG.toFixed(3)} g).`,
        };
  }
  return {
    level: "verde",
    label: PRIORITY_LABEL.verde,
    why: `Sacudida leve (${maxPgaG.toFixed(3)} g).`,
  };
}

export interface PriorityRow {
  incidentId: string;
  siteName: string;
  maxPgaG: number | null;
  feltLabel: string;
  priority: PriorityView;
}

/**
 * Sitios afectados por el MISMO evento, ordenados por prioridad.
 *
 * Se derivan de las filas ya cargadas en la pantalla: son incidentes del propio
 * tenant y ya pasaron por la RLS. No hace falta un endpoint nuevo, y cualquiera que
 * se añadiera podría discrepar de lo que la tabla está mostrando.
 */
export function inspectionMatrix(
  rows: TriageRow[],
  eventId: string | null,
  criticalityOf: (siteId: string) => string | null,
): PriorityRow[] {
  if (!eventId) {
    return [];
  }
  return rows
    .filter((r) => r.incident.event_id === eventId)
    .map((r) => ({
      incidentId: r.incident.incident_id,
      siteName: r.siteName,
      maxPgaG: r.incident.max_pga_g,
      feltLabel: feltLabelOf(r.incident.max_pga_g),
      priority: inspectionPriority(r.incident.max_pga_g, criticalityOf(r.incident.site_id)),
    }))
    .sort(
      (a, b) =>
        PRIORITY_RANK[a.priority.level] - PRIORITY_RANK[b.priority.level] ||
        (b.maxPgaG ?? -1) - (a.maxPgaG ?? -1) ||
        a.siteName.localeCompare(b.siteName),
    );
}
