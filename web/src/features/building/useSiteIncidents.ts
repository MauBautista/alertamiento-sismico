// Incidentes de UN sitio (T-1.35), para el dashboard de edificio.
//
// A diferencia de `useLiveIncidents` (cola global del wall), aquí el filtro `site_id`
// lo aplica el servidor y se incluyen los cerrados: en un edificio importa la historia
// reciente, no solo lo que está abierto ahora mismo.

import { useQuery } from "@tanstack/react-query";

import { listIncidentsIncidentsGet } from "@takab/sdk";
import type { IncidentOut } from "@takab/sdk";

export const SITE_INCIDENTS_REFETCH_MS = 30_000;
export const SITE_INCIDENTS_STALE_MS = 90_000;

export interface SiteIncidentsData {
  incidents: IncidentOut[];
  loading: boolean;
  error: string | null;
  dataUpdatedAt: number;
  refetch: () => void;
}

export function useSiteIncidents(siteId: string | null): SiteIncidentsData {
  const query = useQuery({
    queryKey: ["siteIncidents", siteId],
    queryFn: async () => {
      const { data, response } = await listIncidentsIncidentsGet({
        query: { site_id: siteId as string, limit: 20 },
      });
      if (data === undefined) {
        throw new Error(`GET /incidents?site_id=${siteId} falló (${response.status})`);
      }
      return data;
    },
    enabled: siteId !== null,
    refetchInterval: SITE_INCIDENTS_REFETCH_MS,
  });

  return {
    incidents: query.data?.items ?? [],
    loading: siteId !== null && query.isPending,
    error: query.data === undefined && query.error ? query.error.message : null,
    dataUpdatedAt: query.dataUpdatedAt,
    refetch: () => {
      void query.refetch();
    },
  };
}
