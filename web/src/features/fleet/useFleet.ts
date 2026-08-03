import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import {
  listGatewaysFleetGatewaysGet,
  listRuleSetsRuleSetsGet,
  listSitesSitesGet,
} from "@takab/sdk";
import type { GatewayOut, RuleSetOut, SiteOut } from "@takab/sdk";

import { useSessionStore } from "../../auth/session.store";

/** Cadencia del inventario; los heartbeats de device_health son por transición
 * + latido periódico, no hay nada que ganar refrescando más rápido. */
export const FLEET_REFETCH_MS = 30_000;

/** Sin dato nuevo tras este umbral el panel pasa a DATOS RETENIDOS. */
export const FLEET_STALE_MS = 90_000;

export interface FleetRelay {
  key: string;
  label: string;
  /** Cableado declarado en rule_sets.config.relays (NO/NC/fail_close…). */
  wiring: string;
  /** true = armado (enlace vivo); null = S/D (SIN ENLACE). Nunca se inventa. */
  armed: boolean | null;
}

export interface FleetCabinet {
  gateway: GatewayOut;
  siteName: string;
  siteCode: string | null;
  /** null = config de relays no visible (sin rule_set o /rule-sets falló). */
  relays: FleetRelay[] | null;
}

export interface FleetData {
  cabinets: FleetCabinet[];
  loading: boolean;
  /** Solo cuando el inventario nunca cargó; con datos viejos habla el stale. */
  error: string | null;
  dataUpdatedAt: number;
  refetch: () => void;
}

class FleetRequestError extends Error {
  constructor(resource: string, status: number) {
    super(`GET ${resource} falló (${status})`);
    this.name = "FleetRequestError";
  }
}

async function fetchGateways(): Promise<GatewayOut[]> {
  const { data, response } = await listGatewaysFleetGatewaysGet();
  if (data === undefined) {
    throw new FleetRequestError("/fleet/gateways", response.status);
  }
  return data;
}

async function fetchSites(): Promise<SiteOut[]> {
  const { data, response } = await listSitesSitesGet();
  if (data === undefined) {
    throw new FleetRequestError("/sites", response.status);
  }
  return data;
}

async function fetchRuleSets(): Promise<RuleSetOut[]> {
  const { data, response } = await listRuleSetsRuleSetsGet();
  if (data === undefined) {
    throw new FleetRequestError("/rule-sets", response.status);
  }
  return data.items;
}

const RELAY_LABEL: Record<string, string> = {
  siren: "SIRENA",
  strobe: "ESTROBO",
  gas: "GAS",
  gas_valve: "GAS",
  elevator: "ASCENSORES",
  doors: "PUERTAS",
  door_retainer: "PUERTAS",
};

/** [T-2.31] Alias históricos del rule_set → canal canónico del equipamiento. */
const EQUIPMENT_KEY: Record<string, string> = {
  gas: "gas_valve",
  doors: "door_retainer",
};

/**
 * Relays del gabinete desde la config ACTIVA (site-scope primero, tenant después).
 * El estado por relay se DERIVA del enlace: el supervisor edge trata actuadores
 * como módulo crítico fail-fast, así que proceso vivo ⇒ reglas armadas; sin
 * enlace no hay dato (null), jamás se inventa un estado.
 *
 * [T-2.31] `gateways.equipment` manda sobre la lista: un canal NO instalado se
 * oculta aunque el rule_set declare su cableado (mostrar gas en un sitio sin
 * gas es un dato falso), y un canal instalado sin cableado declarado aparece
 * con wiring "S/D". Sin `equipment` (SDK/flota vieja) la conducta no cambia.
 */
function relaysFor(gw: GatewayOut, ruleSets: RuleSetOut[] | undefined): FleetRelay[] | null {
  if (!ruleSets) {
    return null;
  }
  const active = ruleSets.filter((r) => r.is_active);
  const ruleSet =
    active.find((r) => r.scope_type === "site" && r.scope_id === gw.site_id) ??
    active.find((r) => r.scope_type === "tenant");
  const relays = ruleSet?.config["relays"];
  if (!relays || typeof relays !== "object" || Array.isArray(relays)) {
    return null;
  }
  const equipment = (gw.equipment ?? null) as Record<string, unknown> | null;
  const installed = (key: string): boolean => {
    if (!equipment) {
      return true;
    }
    const flag = equipment[EQUIPMENT_KEY[key] ?? key];
    return typeof flag === "boolean" ? flag : true;
  };
  const linked = gw.derived_state !== "SIN ENLACE";
  const declared = Object.entries(relays as Record<string, unknown>)
    .filter((entry): entry is [string, string] => typeof entry[1] === "string")
    .filter(([key]) => installed(key))
    .map(([key, wiring]) => ({
      key,
      label: RELAY_LABEL[key] ?? key.toUpperCase(),
      wiring,
      armed: linked ? true : null,
    }));
  if (!equipment) {
    return declared;
  }
  const declaredChannels = new Set(declared.map((r) => EQUIPMENT_KEY[r.key] ?? r.key));
  const undeclared = Object.entries(equipment)
    .filter(([key, flag]) => flag === true && !declaredChannels.has(key))
    .map(([key]) => ({
      key,
      label: RELAY_LABEL[key] ?? key.toUpperCase(),
      wiring: "S/D",
      armed: linked ? true : null,
    }));
  return [...declared, ...undeclared];
}

/** View-model puro (exportado para tests sin DOM). */
export function buildCabinets(
  gateways: GatewayOut[] | undefined,
  sites: SiteOut[] | undefined,
  ruleSets: RuleSetOut[] | undefined,
): FleetCabinet[] {
  if (!gateways) {
    return [];
  }
  const byId = new Map((sites ?? []).map((s) => [s.site_id, s]));
  return gateways.map((gw) => {
    const site = byId.get(gw.site_id);
    return {
      gateway: gw,
      siteName: site?.name ?? `SITIO ${gw.site_id.slice(0, 8)}`,
      siteCode: site?.code ?? null,
      relays: relaysFor(gw, ruleSets),
    };
  });
}

/**
 * Inventario de la flota: /fleet/gateways (estado YA derivado server-side —
 * la UI solo pinta) enriquecido con /sites y /rule-sets, que degradan sin
 * tumbar la página si fallan.
 */
export function useFleet(): FleetData {
  // /fleet/gateways exige permiso de flota. FleetPage ya vive detrás del
  // RouteGuard, pero useSiteRelays monta este hook en la CONSOLA, donde
  // inspector y building_admin sí entran y no pueden leer la flota: sin este
  // gate cada carga de /console les disparaba un 403 (la misma matriz del
  // server que guarda la ruta decide aquí, cero matriz local).
  const canReadFleet = useSessionStore((s) => s.me?.allowed_routes.includes("/fleet") ?? false);

  const gateways = useQuery({
    queryKey: ["fleet", "gateways"],
    queryFn: fetchGateways,
    refetchInterval: FLEET_REFETCH_MS,
    enabled: canReadFleet,
  });
  const sites = useQuery({
    queryKey: ["sites"],
    queryFn: fetchSites,
    staleTime: 300_000,
  });
  const ruleSets = useQuery({
    queryKey: ["rule-sets"],
    queryFn: fetchRuleSets,
    staleTime: 300_000,
  });

  const cabinets = useMemo(
    () => buildCabinets(gateways.data, sites.data, ruleSets.data),
    [gateways.data, sites.data, ruleSets.data],
  );

  return {
    cabinets,
    // Con `enabled:false` la query se queda en `isPending` para siempre (nunca
    // corre): sin este guard el rol sin permiso vería un spinner eterno en vez
    // de la card de relés "no visible".
    loading: canReadFleet && gateways.isPending,
    error: gateways.data === undefined && gateways.error ? gateways.error.message : null,
    dataUpdatedAt: gateways.dataUpdatedAt,
    refetch: () => {
      void gateways.refetch();
    },
  };
}
