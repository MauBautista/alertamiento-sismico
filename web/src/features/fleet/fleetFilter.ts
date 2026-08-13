// Búsqueda, orden y filtros de la Flota Edge (T-2.38), como funciones puras.
//
// Van aparte del componente para poder probarlas sin DOM y, sobre todo, para que el
// invariante que importa quede explícito y testeado: **filtrar NO cambia los KPI**.
// Un contador que se moviera con el filtro convertiría "3 SIN ENLACE" en una cifra
// distinta según lo que el operador tuviera tecleado, que es la clase de dato falso
// que prohíbe la regla de oro 7. Los KPI cuentan el total; la reja muestra el
// subconjunto y la leyenda dice cuántos de cuántos.

import type { FleetCabinet } from "./useFleet";
import { DEGRADADO, OPERATIVO, SIN_ENLACE } from "./estadoGlosario";

export const SORT_KEYS = ["estado", "nombre", "latido", "serial"] as const;
export type SortKey = (typeof SORT_KEYS)[number];

export const SORT_LABEL: Record<SortKey, string> = {
  estado: "ESTADO (PEOR PRIMERO)",
  nombre: "NOMBRE DE ESTACIÓN",
  latido: "ÚLTIMO LATIDO",
  serial: "SERIAL",
};

/** Peor primero: el operador abre la pantalla para ver qué está roto. */
const STATE_RANK: Record<string, number> = {
  [SIN_ENLACE]: 0,
  [DEGRADADO]: 1,
  [OPERATIVO]: 2,
};

export interface FleetFilters {
  query: string;
  sort: SortKey;
  hideOffline: boolean;
}

export const DEFAULT_FILTERS: FleetFilters = {
  query: "",
  sort: "estado",
  hideOffline: false,
};

/** Casa por nombre, código, serial e iot_thing: los cuatro identificadores que un
 *  técnico puede tener a mano (una orden de trabajo, una etiqueta, la consola AWS). */
export function matchesQuery(cabinet: FleetCabinet, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (q === "") return true;
  const gw = cabinet.gateway;
  return [cabinet.siteName, cabinet.siteCode, gw.serial, gw.iot_thing ?? ""]
    .join(" ")
    .toLowerCase()
    .includes(q);
}

export function applyFilters(cabinets: FleetCabinet[], f: FleetFilters): FleetCabinet[] {
  const filtered = cabinets
    .filter((c) => matchesQuery(c, f.query))
    .filter((c) => !f.hideOffline || c.gateway.derived_state !== SIN_ENLACE);

  const sorted = [...filtered];
  sorted.sort((a, b) => {
    switch (f.sort) {
      case "nombre":
        return (
          a.siteName.localeCompare(b.siteName) || a.gateway.serial.localeCompare(b.gateway.serial)
        );
      case "serial":
        return a.gateway.serial.localeCompare(b.gateway.serial);
      case "latido": {
        // Sin latido va PRIMERO: es el caso que exige atención, no el que se esconde
        // al final de la lista.
        const ta = a.gateway.last_heartbeat_ts ? Date.parse(a.gateway.last_heartbeat_ts) : -1;
        const tb = b.gateway.last_heartbeat_ts ? Date.parse(b.gateway.last_heartbeat_ts) : -1;
        return ta - tb;
      }
      case "estado":
      default: {
        // Un `derived_state` desconocido NO se cuela entre los sanos: va al frente
        // junto a lo que no se entiende (mismo criterio que DERIVED_STATE_PILL).
        const ra = STATE_RANK[a.gateway.derived_state] ?? -1;
        const rb = STATE_RANK[b.gateway.derived_state] ?? -1;
        return ra - rb || a.siteName.localeCompare(b.siteName);
      }
    }
  });
  return sorted;
}

export function isFiltering(f: FleetFilters): boolean {
  return f.query.trim() !== "" || f.hideOffline;
}
