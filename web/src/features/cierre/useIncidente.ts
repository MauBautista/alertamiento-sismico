// [T-9.41] La FILA del incidente, leída por su id.
//
// El asistente se abre por URL (`/triage/:incidentId/cierre`), así que no puede
// fiarse de la fila que el historial tuviera cargada: la pide. Es el dato que
// decide ACUSADO y CERRADO, los dos «hechos» más autoritativos de la pantalla.

import { useQuery } from "@tanstack/react-query";

import { getIncidentIncidentsIncidentIdGet, listSitesSitesGet } from "@takab/sdk";
import type { IncidentOut, SiteOut } from "@takab/sdk";

import { useNow } from "../../lib/useNow";
import { staleSinceOf } from "../triage/staleness";
import { leer } from "./respuesta";

/** Ni `["incident", id, "actions"]` (el wall) ni `["incidents", …]` (las listas). */
export const INCIDENTE_KEY = (id: string) => ["incident", id, "fila"] as const;

export function useIncidente(incidentId: string) {
  const now = useNow(30_000);
  const q = useQuery({
    queryKey: INCIDENTE_KEY(incidentId),
    queryFn: async (): Promise<IncidentOut> => {
      const r = leer(
        await getIncidentIncidentsIncidentIdGet({ path: { incident_id: incidentId } }),
      );
      if (!r.ok) {
        throw new Error(
          r.status === 404
            ? "EL INCIDENTE NO EXISTE O NO ESTÁ EN TU ALCANCE"
            : `GET /incidents/{id} falló (${r.status ?? "sin respuesta"})`,
        );
      }
      return r.data;
    },
  });
  return {
    incidente: q.data,
    loading: q.isPending,
    error: q.error ? q.error.message : null,
    staleSince: staleSinceOf(q.dataUpdatedAt, now),
    refetch: () => void q.refetch(),
  };
}

/** El nombre del inmueble: misma clave y misma forma que `useTriage` (`["sites"]`). */
export function useSitio(siteId: string | null): SiteOut | null {
  const q = useQuery({
    queryKey: ["sites"],
    queryFn: async (): Promise<SiteOut[]> => {
      const { data, response } = await listSitesSitesGet();
      if (data === undefined) throw new Error(`GET /sites falló (${response.status})`);
      return data;
    },
    staleTime: 300_000,
  });
  return siteId === null ? null : (q.data?.find((s) => s.site_id === siteId) ?? null);
}
