// [T-7.17] Cómo lo detectó cada estación: lo medido junto a lo esperado.
//
// Una consulta por incidente, sin poll: la tabla describe un evento que ya
// ocurrió y sus filas no cambian mientras se mira. Poner un `refetchInterval`
// aquí sería pedirle a la nube cada pocos segundos que recalcule una ventana de
// tres minutos para devolver exactamente lo mismo.
//
// El `staleTime` es cero a propósito: al volver a abrir un incidente sí conviene
// releer, porque entre medias pueden haber llegado features atrasadas del spool
// de un gabinete que estuvo sin red.

import { useQuery } from "@tanstack/react-query";

import { incidentEstacionesIncidentsIncidentIdEstacionesGet } from "@takab/sdk";
import type { EstacionesOut } from "@takab/sdk";

export const ESTACIONES_KEY = (id: string) => ["estaciones", id] as const;

export interface EstacionesData {
  data: EstacionesOut | null;
  loading: boolean;
  error: boolean;
  updatedAt: number;
  refetch: () => void;
}

export function useEstaciones(incidentId: string | null): EstacionesData {
  const q = useQuery({
    queryKey: ESTACIONES_KEY(incidentId ?? ""),
    enabled: incidentId !== null,
    queryFn: async () => {
      const r = await incidentEstacionesIncidentsIncidentIdEstacionesGet({
        path: { incident_id: incidentId as string },
      });
      if (r.error !== undefined) throw new Error("estaciones");
      return r.data as EstacionesOut;
    },
  });
  return {
    data: q.data ?? null,
    loading: q.isLoading,
    error: q.isError,
    updatedAt: q.dataUpdatedAt,
    refetch: () => void q.refetch(),
  };
}
