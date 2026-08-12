// Hechos medidos del incidente (T-2.40): el MISMO objeto que consume el dictamen PDF.
//
// Cadencia larga y sin poll: son hechos de un incidente pasado, no telemetría viva.
// Refrescarlos cada pocos segundos gastaría red para reconfirmar números que ya no
// cambian.

import { useQuery } from "@tanstack/react-query";

import { incidentForensicsIncidentsIncidentIdForensicsGet } from "@takab/sdk";
import type { ForensicsOut } from "@takab/sdk";

import { useNow } from "../../lib/useNow";
import { SIGNING_STALE_MS, staleSinceOf } from "./staleness";

export interface ForensicsState {
  data: ForensicsOut | undefined;
  loading: boolean;
  error: string | null;
  refetch: () => void;
  /** Epoch ms de la última respuesta buena; 0 si todavía no ha llegado ninguna. */
  dataUpdatedAt: number;
  /**
   * Epoch ms de esa respuesta CUANDO ya se considera vieja; null = fresca.
   *
   * Se calcula UNA vez —en `staleness.ts`, con el reloj de toda la pantalla— y
   * viaja a todos los paneles en vez de que cada uno lo re-derive: la
   * precedencia entre `empty` y `stale` la decide `STATE_PRECEDENCE` para toda
   * la consola (T-2.79.d), y un panel que se fabrique su propio veredicto de
   * frescura es el primer paso para que se fabrique también su propia
   * precedencia.
   */
  staleSince: number | null;
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
    // El `staleTime` MÁS LARGO de la pantalla, y el que fija el suelo de
    // `SIGNING_STALE_MS`: son hechos de un incidente pasado, no telemetría.
    staleTime: 300_000,
  });
  const now = useNow(30_000);

  const dataUpdatedAt = query.dataUpdatedAt;
  const staleSince = staleSinceOf(dataUpdatedAt, now, SIGNING_STALE_MS);

  return {
    data: query.data,
    // `enabled:false` deja la query en `isPending` para siempre: sin este guard, un
    // panel sin incidente seleccionado mostraría un spinner eterno.
    loading: incidentId !== null && query.isPending,
    error: query.error ? query.error.message : null,
    refetch: () => void query.refetch(),
    dataUpdatedAt,
    staleSince,
  };
}
