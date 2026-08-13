import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { listGatewaysFleetGatewaysGet, listRuleSetsRuleSetsGet } from "@takab/sdk";
import type { GatewayOut, RuleSetOut } from "@takab/sdk";

import { useSessionStore } from "../../auth/session.store";
import { SD, SIN_ENLACE } from "./estadoGlosario";

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
  /**
   * true = ARMADO; null = S/D. Nunca se inventa.
   *
   * [T-2.70.a·B1] Armar exige DOS cosas: enlace vivo Y que el gabinete haya
   * podido publicar el censo de sus relés. Antes bastaba el enlace, y por eso un
   * gabinete sin dueño de pines —que late igual de bien— mostraba sus cinco
   * actuadores en ARMADO sin que nadie gobernara ninguno.
   */
  armed: boolean | null;
}

export interface FleetCabinet {
  gateway: GatewayOut;
  /** [T-2.35] Del SERVIDOR. Ver `buildCabinets` para por qué ya no se deriva aquí. */
  siteName: string;
  siteCode: string;
  /** 'active' | 'retired' — un gabinete vivo en un sitio retirado se rotula. */
  siteStatus: string;
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

async function fetchGateways(includeRetired: boolean): Promise<GatewayOut[]> {
  const { data, response } = await listGatewaysFleetGatewaysGet(
    includeRetired ? { query: { include_retired: true } } : undefined,
  );
  if (data === undefined) {
    throw new FleetRequestError("/fleet/gateways", response.status);
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
 *
 * [T-2.70.a·B1] «Proceso vivo ⇒ reglas armadas» DEJÓ DE SER CIERTO cuando D3 sacó
 * al dueño de los pines a su propio proceso. Con `gpio_owner=gpio` y `takab-gpio`
 * caído, `takab-edge` late cada 60 s —el enlace está vivo, `derived_state` no es
 * SIN ENLACE— y NADIE gobierna la sirena, el gas, los ascensores ni los
 * retenedores. Esta función pintaba los cinco actuadores en ARMADO justo ahí.
 *
 * Ahora `armed` sale del censo que el gabinete publica en su latido
 * (`relays_state`): sólo `reported` arma. `unreadable` (no pudo preguntar),
 * `stopped` (preguntó y no hay filas) y `null` (firmware que no opina) son S/D.
 * Regla de oro 7: un dato que no se pudo obtener no se pinta como bueno.
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
  const linked = gw.derived_state !== SIN_ENLACE;
  // El censo VIAJA en el latido; `null` = flota/SDK anterior a 1.10.0, que no
  // opina — y ahí se conserva la conducta previa (el enlace es lo único que se
  // sabe). Un `null` NO se lee como avería: sería marcar S/D a toda la flota
  // vieja por un campo que su firmware no sabe emitir.
  const censo = gw.relays_state ?? null;
  const armed: boolean | null = linked && (censo === null || censo === "reported") ? true : null;
  const declared = Object.entries(relays as Record<string, unknown>)
    .filter((entry): entry is [string, string] => typeof entry[1] === "string")
    .filter(([key]) => installed(key))
    .map(([key, wiring]) => ({
      key,
      label: RELAY_LABEL[key] ?? key.toUpperCase(),
      wiring,
      armed,
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
      wiring: SD,
      armed,
    }));
  return [...declared, ...undeclared];
}

/**
 * View-model puro (exportado para tests sin DOM).
 *
 * [T-2.35] El nombre del sitio VIENE DEL SERVIDOR; aquí ya no se hace join ni se
 * fabrica nada. Antes se cruzaba contra `/sites`, que oculta los retirados: un
 * gabinete cuyo sitio se había retirado perdía su nombre y esta función lo
 * rebautizaba `SITIO <8 hex>`. Como además el inventario devolvía a esos huérfanos y
 * la UI no tenía forma de borrarlos, el operador veía varias "estaciones fantasma"
 * con el mismo rótulo. Sin fallback que inventar, la clase de bug desaparece.
 */
export function buildCabinets(
  gateways: GatewayOut[] | undefined,
  ruleSets: RuleSetOut[] | undefined,
): FleetCabinet[] {
  if (!gateways) {
    return [];
  }
  return gateways.map((gw) => ({
    gateway: gw,
    siteName: gw.site_name,
    siteCode: gw.site_code,
    siteStatus: gw.site_status,
    relays: relaysFor(gw, ruleSets),
  }));
}

export interface UseFleetOptions {
  /** [T-2.35] Incluye gabinetes retirados (y los de sitios retirados) para restaurarlos. */
  includeRetired?: boolean;
}

/**
 * Inventario de la flota: /fleet/gateways (estado y nombre de sitio YA derivados
 * server-side — la UI solo pinta) enriquecido con /rule-sets, que degrada sin
 * tumbar la página si falla.
 */
export function useFleet({ includeRetired = false }: UseFleetOptions = {}): FleetData {
  // /fleet/gateways exige permiso de flota. FleetPage ya vive detrás del
  // RouteGuard, pero useSiteRelays monta este hook en la CONSOLA, donde
  // inspector y building_admin sí entran y no pueden leer la flota: sin este
  // gate cada carga de /console les disparaba un 403 (la misma matriz del
  // server que guarda la ruta decide aquí, cero matriz local).
  const canReadFleet = useSessionStore((s) => s.me?.allowed_routes.includes("/fleet") ?? false);

  const gateways = useQuery({
    // `includeRetired` va en la clave: si no, el toggle mostraría la caché del otro
    // modo y el operador creería que no hay retirados que restaurar.
    queryKey: ["fleet", "gateways", includeRetired],
    queryFn: () => fetchGateways(includeRetired),
    refetchInterval: FLEET_REFETCH_MS,
    enabled: canReadFleet,
  });
  const ruleSets = useQuery({
    queryKey: ["rule-sets"],
    queryFn: fetchRuleSets,
    staleTime: 300_000,
  });

  const cabinets = useMemo(
    () => buildCabinets(gateways.data, ruleSets.data),
    [gateways.data, ruleSets.data],
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
