// Relés del gabinete del sitio enfocado (T-1.50), para la card "RELÉS DEL
// GABINETE" del detalle de la consola. Reutiliza las MISMAS queryKeys que
// useFleet (["fleet","gateways"], ["sites"], ["rule-sets"]) ⇒ caché compartida:
// abrir el detalle no dispara fetches nuevos si la flota ya se miró.
//
// M-6 (T-1.58): propaga error/dataUpdatedAt/refetch de useFleet — un 500 de
// /fleet/gateways NO es "config no visible" (empty); son estados distintos.
// OJO: un rol SIN /fleet (useFleet ni dispara la query) queda con error=null y
// relays=null ⇒ empty honesto, no error.

import { useMemo } from "react";

import { useFleet, type FleetRelay } from "../fleet/useFleet";

/** Frescura de la config de flota que alimenta la card (post-evento, no live). */
export const RELAYS_STALE_MS = 120_000;

export interface SiteRelaysData {
  /** null = config de relés no visible (sin rule_set, sin gateway o sin /fleet). */
  relays: FleetRelay[] | null;
  loading: boolean;
  /** Fallo REAL de /fleet/gateways (distinto de "no visible"). */
  error: string | null;
  dataUpdatedAt: number;
  refetch: () => void;
}

export function useSiteRelays(siteId: string | null): SiteRelaysData {
  const fleet = useFleet();
  const relays = useMemo(() => {
    if (siteId === null) {
      return null;
    }
    const cabinet = fleet.cabinets.find((c) => c.gateway.site_id === siteId) ?? null;
    return cabinet?.relays ?? null;
  }, [fleet.cabinets, siteId]);
  return {
    relays,
    loading: fleet.loading,
    error: fleet.error,
    dataUpdatedAt: fleet.dataUpdatedAt,
    refetch: fleet.refetch,
  };
}
