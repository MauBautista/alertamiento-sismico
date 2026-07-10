// Relés del gabinete del sitio enfocado (T-1.50), para la card "RELÉS DEL
// GABINETE" del detalle de la consola. Reutiliza las MISMAS queryKeys que
// useFleet (["fleet","gateways"], ["sites"], ["rule-sets"]) ⇒ caché compartida:
// abrir el detalle no dispara fetches nuevos si la flota ya se miró.

import { useMemo } from "react";

import { useFleet, type FleetRelay } from "../fleet/useFleet";

export interface SiteRelaysData {
  /** null = config de relés no visible (sin rule_set, sin gateway o error). */
  relays: FleetRelay[] | null;
  loading: boolean;
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
  return { relays, loading: fleet.loading };
}
