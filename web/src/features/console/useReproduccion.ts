// [T-7.20] La reproducción del incidente en foco: qué sismo se está enseñando.
//
// Una consulta, sin poll: el plan de arribos y la procedencia del catálogo no
// cambian mientras se mira. `enabled` solo con incidente: sin él no se pregunta
// nada, y el marco se queda vacío en vez de pedir una URL con `null` dentro.

import { useQuery } from "@tanstack/react-query";

import { incidentReproduccionIncidentsIncidentIdReproduccionGet } from "@takab/sdk";
import type { ReproduccionOut } from "@takab/sdk";

export const REPRODUCCION_KEY = (id: string) => ["reproduccion", id] as const;

export interface ReproduccionData {
  data: ReproduccionOut | null;
  loading: boolean;
  /** `true` solo si la lectura FALLÓ. Un 404 no es un fallo: es «no es una
   *  reproducción», que es la respuesta normal de casi todos los incidentes. */
  error: boolean;
  refetch: () => void;
}

export function useReproduccion(incidentId: string | null): ReproduccionData {
  const q = useQuery({
    queryKey: REPRODUCCION_KEY(incidentId ?? ""),
    enabled: incidentId !== null,
    retry: false,
    queryFn: async () => {
      const r = await incidentReproduccionIncidentsIncidentIdReproduccionGet({
        path: { incident_id: incidentId as string },
      });
      // El 404 es la respuesta ESPERADA de un incidente real: se traduce a
      // «no hay reproducción» y no a un error, porque pintar un fallo de
      // lectura ahí diría que algo se rompió cuando no pasó nada.
      if (r.error !== undefined) return null;
      return (r.data ?? null) as ReproduccionOut | null;
    },
  });
  return {
    data: q.data ?? null,
    loading: q.isLoading,
    error: q.isError,
    refetch: () => void q.refetch(),
  };
}
