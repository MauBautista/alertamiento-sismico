// CCTV del incidente (T-3.12.c): el MISMO objeto que consume la sección del dictamen PDF.
//
// Cadencia larga y sin poll, por la misma razón que `useForensics`: es un incidente
// pasado. La única cifra que puede cambiar es el conteo cuando el análisis termine, y eso
// ocurre una vez, no cada pocos segundos.

import { useQuery } from "@tanstack/react-query";

import { incidentCctvIncidentsIncidentIdCctvGet } from "@takab/sdk";
import type { CctvOut } from "@takab/sdk";

import { useNow } from "../../lib/useNow";
import { SIGNING_STALE_MS, staleSinceOf } from "./staleness";

export interface CctvState {
  data: CctvOut | undefined;
  loading: boolean;
  error: string | null;
  refetch: () => void;
  dataUpdatedAt: number;
  /**
   * Epoch ms del último dato bueno CUANDO ya se considera viejo; null = fresco.
   *
   * Sale del mismo reloj y el mismo umbral que el resto de la pantalla. Un panel que se
   * fabrique su propio veredicto de frescura es el primer paso para que se fabrique
   * también su propia precedencia entre `empty` y `stale`.
   */
  staleSince: number | null;
}

export function useCctv(incidentId: string | null): CctvState {
  const query = useQuery({
    queryKey: ["cctv", incidentId],
    queryFn: async () => {
      const { data, response } = await incidentCctvIncidentsIncidentIdCctvGet({
        path: { incident_id: incidentId as string },
      });
      if (data === undefined) {
        throw new Error(`GET /incidents/{id}/cctv falló (${response.status})`);
      }
      return data;
    },
    enabled: incidentId !== null,
    staleTime: 300_000,
  });
  const now = useNow(30_000);

  const dataUpdatedAt = query.dataUpdatedAt;
  const staleSince = staleSinceOf(dataUpdatedAt, now, SIGNING_STALE_MS);

  return {
    data: query.data,
    // `enabled:false` deja la query en `isPending` para siempre: sin este guard un panel
    // sin incidente seleccionado mostraría un spinner eterno.
    loading: incidentId !== null && query.isPending,
    error: query.error ? query.error.message : null,
    refetch: () => void query.refetch(),
    dataUpdatedAt,
    staleSince,
  };
}
