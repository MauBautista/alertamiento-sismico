// Hechos medidos del incidente (T-2.40): el MISMO objeto que consume el dictamen PDF.
//
// Cadencia larga y sin poll: son hechos de un incidente pasado, no telemetría viva.
// Refrescarlos cada pocos segundos gastaría red para reconfirmar números que ya no
// cambian.

import { useQuery } from "@tanstack/react-query";

import { incidentForensicsIncidentsIncidentIdForensicsGet } from "@takab/sdk";
import type { ForensicsOut } from "@takab/sdk";

export interface ForensicsState {
  data: ForensicsOut | undefined;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useForensics(incidentId: string | null): ForensicsState {
  const query = useQuery({
    queryKey: ["forensics", incidentId],
    queryFn: async () => {
      const { data, response } = await incidentForensicsIncidentsIncidentIdForensicsGet({
        path: { incident_id: incidentId as string },
      });
      if (data === undefined) {
        throw new Error(`GET /incidents/{id}/forensics falló (${response.status})`);
      }
      return data;
    },
    enabled: incidentId !== null,
    staleTime: 300_000,
  });

  return {
    data: query.data,
    // `enabled:false` deja la query en `isPending` para siempre: sin este guard, un
    // panel sin incidente seleccionado mostraría un spinner eterno.
    loading: incidentId !== null && query.isPending,
    error: query.error ? query.error.message : null,
    refetch: () => void query.refetch(),
  };
}
