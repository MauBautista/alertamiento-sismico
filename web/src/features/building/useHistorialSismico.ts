// [T-9.66 · D-46] El historial sísmico DEL INMUEBLE, para el dashboard de edificio.
//
// Una sola lista del servidor, por fecha: lo que MIDIÓ el gabinete (incidentes)
// y los sismos del catálogo que ahí se habrían sentido (MMI ESTIMADA ≥ III).
// Las dos cosas no se parecen y la tarjeta no las confunde: una es medición,
// la otra estimación.

import { useQuery } from "@tanstack/react-query";

import { historialSismicoSitesSiteIdHistorialSismicoGet } from "@takab/sdk";
import type { HistorialSismicoOut } from "@takab/sdk";

/** La ventana del historial: un año, el defecto del servidor, dicho aquí para rotularlo. */
export const HISTORIAL_DIAS = 365;
/** El catálogo lo sincroniza un worker cada pocos minutos: se relee a ese ritmo. */
export const HISTORIAL_REFETCH_MS = 300_000;
export const HISTORIAL_STALE_MS = 900_000;

export type EventoHistorial = HistorialSismicoOut["eventos"][number];

export interface HistorialSismicoData {
  eventos: EventoHistorial[];
  atribucion: string | null;
  loading: boolean;
  error: string | null;
  dataUpdatedAt: number;
  refetch: () => void;
}

export function useHistorialSismico(siteId: string): HistorialSismicoData {
  const query = useQuery({
    queryKey: ["historialSismico", siteId, HISTORIAL_DIAS],
    queryFn: async () => {
      const { data, response } = await historialSismicoSitesSiteIdHistorialSismicoGet({
        path: { site_id: siteId },
        query: { dias: HISTORIAL_DIAS },
      });
      if (data === undefined) {
        throw new Error(`GET /sites/${siteId}/historial-sismico falló (${response.status})`);
      }
      return data;
    },
    refetchInterval: HISTORIAL_REFETCH_MS,
  });

  return {
    eventos: query.data?.eventos ?? [],
    atribucion: query.data?.atribucion ?? null,
    loading: query.isPending,
    error: query.data === undefined && query.error ? query.error.message : null,
    dataUpdatedAt: query.dataUpdatedAt,
    refetch: () => {
      void query.refetch();
    },
  };
}
