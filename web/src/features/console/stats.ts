// [T-2.50] Estadísticas de MONITOREO — PURO (sin React, sin MapLibre).
//
// CERO endpoints nuevos: todo sale de lo que la pantalla ya pide (`/telemetry/
// map/state` + `/incidents`). Si un número exigiera una consulta nueva, no está
// aquí: está en la lista de diferidos del plan.
//
// Dos invariantes que este módulo hace cumplir, y por las que hay tests:
//
//  · **Los contadores del viewport DECLARAN su recorte** (`MOSTRANDO n DE N`). Un
//    "12 ESTACIONES" que en realidad son las 12 que caben en pantalla —de 40 que
//    tiene el cliente— es un dato falso presentado como total.
//  · **Ausencia ≠ cero.** Sin ninguna latencia reportada el KPI vale `null` y la
//    UI pinta `S/D`. "0 ms" se lee como un enlace perfecto (regla de oro 7).

import type { MapEpicenter, MapSiteState } from "@takab/sdk";

import { haversineKm } from "../fleet/geo";
import {
  LINK_DEGRADADO,
  LINK_OPERATIVO,
  LINK_SIN_ENLACE,
  LINK_SIN_GABINETE,
  siteLink,
} from "./link";
import type { LiveIncident } from "./useLiveIncidents";

/** Caja del viewport tal como la da `map.getBounds()`, ya desestructurada. */
export interface ViewBounds {
  west: number;
  south: number;
  east: number;
  north: number;
}

/**
 * Estaciones dentro del viewport. `null` (mapa aún sin montar) devuelve TODO:
 * inventar un recorte que el operador no ha hecho sería peor que no recortar.
 *
 * El caso del ANTIMERIDIANO no es teórico: al arrastrar el mapa hacia el este,
 * MapLibre devuelve `west > east`, y un `lon >= west && lon <= east` ingenuo
 * dejaría cero estaciones y el wall se vaciaría sin motivo.
 */
export function sitesInBounds(sites: MapSiteState[], bounds: ViewBounds | null): MapSiteState[] {
  if (bounds === null) return sites;
  const { west, south, east, north } = bounds;
  const inLon = (lon: number): boolean =>
    west <= east ? lon >= west && lon <= east : lon >= west || lon <= east;
  return sites.filter((s) => s.lat >= south && s.lat <= north && inLon(s.lon));
}

/** Leyenda honesta del recorte del viewport. */
export function showingLabel(shown: number, total: number): string {
  return `MOSTRANDO ${shown} DE ${total}`;
}

export interface ConsoleKpis {
  stations: number;
  operativo: number;
  degradado: number;
  sinEnlace: number;
  sinGabinete: number;
  trip: number;
  watch: number;
  normal: number;
  feltDesconocido: number;
  /** `null` = nadie reportó latencia. NUNCA 0 (se leería como enlace perfecto). */
  rttP50Ms: number | null;
  rttMaxMs: number | null;
  lagMaxS: number | null;
  incidentesAbiertos: number;
  incidentesCriticos: number;
}

function median(values: number[]): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 1 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

/**
 * KPIs del strip tipo semáforo. Se calculan sobre las estaciones que se le pasen
 * — la pantalla decide si son las del viewport o las del tenant entero, y lo
 * rotula con `showingLabel`.
 */
export function consoleKpis(sites: MapSiteState[], incidents: LiveIncident[]): ConsoleKpis {
  const kpis: ConsoleKpis = {
    stations: sites.length,
    operativo: 0,
    degradado: 0,
    sinEnlace: 0,
    sinGabinete: 0,
    trip: 0,
    watch: 0,
    normal: 0,
    feltDesconocido: 0,
    rttP50Ms: null,
    rttMaxMs: null,
    lagMaxS: null,
    incidentesAbiertos: incidents.length,
    incidentesCriticos: incidents.filter((i) => i.severity === "critical").length,
  };
  const rtts: number[] = [];
  const lags: number[] = [];
  for (const s of sites) {
    switch (siteLink(s)) {
      case LINK_OPERATIVO:
        kpis.operativo += 1;
        break;
      case LINK_DEGRADADO:
        kpis.degradado += 1;
        break;
      case LINK_SIN_ENLACE:
        kpis.sinEnlace += 1;
        break;
      case LINK_SIN_GABINETE:
        kpis.sinGabinete += 1;
        break;
    }
    switch (s.felt) {
      case "trip":
        kpis.trip += 1;
        break;
      case "watch":
        kpis.watch += 1;
        break;
      case "normal":
        kpis.normal += 1;
        break;
      default:
        kpis.feltDesconocido += 1;
    }
    if (s.mqtt_rtt_ms !== null && s.mqtt_rtt_ms !== undefined) rtts.push(s.mqtt_rtt_ms);
    if (s.seedlink_lag_s !== null && s.seedlink_lag_s !== undefined) lags.push(s.seedlink_lag_s);
  }
  kpis.rttP50Ms = median(rtts);
  kpis.rttMaxMs = rtts.length > 0 ? Math.max(...rtts) : null;
  kpis.lagMaxS = lags.length > 0 ? Math.max(...lags) : null;
  return kpis;
}

// --- Orden de la cola de incidentes -------------------------------------------

export type IncidentOrderKey = "severity" | "recent" | "pga" | "age" | "distance";

export interface IncidentOrder {
  key: IncidentOrderKey;
  label: string;
}

export const INCIDENT_ORDERS: readonly IncidentOrder[] = [
  { key: "severity", label: "SEVERIDAD" },
  { key: "recent", label: "MÁS RECIENTE" },
  { key: "pga", label: "PGA MEDIDO" },
  { key: "age", label: "EDAD" },
  { key: "distance", label: "DISTANCIA AL EPICENTRO" },
];

/** Peso de severidad: mayor = más arriba. Un valor desconocido no se cuela al tope. */
const SEVERITY_RANK: Record<string, number> = {
  critical: 4,
  warning: 3,
  watch: 2,
  info: 1,
};

export interface OrderContext {
  /** Epicentro de referencia para el orden por distancia (null = no hay). */
  epicenter?: MapEpicenter | null;
  siteById?: Map<string, MapSiteState>;
}

function bySeverity(a: LiveIncident, b: LiveIncident): number {
  const rank = (i: LiveIncident): number => SEVERITY_RANK[i.severity] ?? 0;
  return rank(b) - rank(a) || Date.parse(b.opened_at) - Date.parse(a.opened_at);
}

/**
 * Ordena la cola. **No muta** el array de entrada: viene de la caché de
 * react-query y mutarlo cambiaría lo que ven otros consumidores.
 *
 * `pga` manda al FINAL a los que no tienen pico medido, en vez de tratarlos como
 * `0`: "no sabemos qué sintió" no es "no se movió" (mismo criterio que el mapa).
 *
 * `distance` sin epicentro conocido degrada a `severity` en vez de barajar las
 * filas fingiendo una distancia que nadie midió; la UI lo declara.
 */
export function orderIncidents(
  incidents: LiveIncident[],
  key: IncidentOrderKey,
  ctx: OrderContext,
): LiveIncident[] {
  const rows = [...incidents];
  switch (key) {
    case "recent":
      return rows.sort((a, b) => Date.parse(b.opened_at) - Date.parse(a.opened_at));
    case "age":
      return rows.sort((a, b) => Date.parse(a.opened_at) - Date.parse(b.opened_at));
    case "pga":
      return rows.sort((a, b) => {
        const pa = a.max_pga_g;
        const pb = b.max_pga_g;
        if (pa === null && pb === null) return bySeverity(a, b);
        if (pa === null) return 1;
        if (pb === null) return -1;
        return pb - pa || bySeverity(a, b);
      });
    case "distance": {
      const epicenter = ctx.epicenter ?? null;
      const siteById = ctx.siteById;
      if (epicenter === null || siteById === undefined) return rows.sort(bySeverity);
      const km = (i: LiveIncident): number | null => {
        const s = siteById.get(i.site_id);
        return s === undefined
          ? null
          : haversineKm({ lon: epicenter.lon, lat: epicenter.lat }, { lon: s.lon, lat: s.lat });
      };
      return rows.sort((a, b) => {
        const da = km(a);
        const db = km(b);
        if (da === null && db === null) return bySeverity(a, b);
        if (da === null) return 1;
        if (db === null) return -1;
        return da - db || bySeverity(a, b);
      });
    }
    default:
      return rows.sort(bySeverity);
  }
}
