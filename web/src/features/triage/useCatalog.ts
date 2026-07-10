// Catálogo de referencia SSN/USGS (T-1.52) — GET /catalog/earthquakes (T-1.48).
// Datos históricos OFICIALES (13 sismos ratificados en T-1.46), globales y de
// solo lectura: staleTime largo, no cambian entre sesiones.

import { useQuery } from "@tanstack/react-query";

import { listReferenceEarthquakesCatalogEarthquakesGet } from "@takab/sdk";
import type { CatalogEarthquakeOut } from "@takab/sdk";

export interface CatalogData {
  items: CatalogEarthquakeOut[];
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useCatalog(): CatalogData {
  const query = useQuery({
    queryKey: ["catalog", "earthquakes"],
    staleTime: 86_400_000, // 24 h: catálogo histórico, no telemetría
    queryFn: async () => {
      const { data, response } = await listReferenceEarthquakesCatalogEarthquakesGet();
      if (data === undefined) {
        throw new Error(`GET /catalog/earthquakes falló (${response.status})`);
      }
      return data.items;
    },
  });
  return {
    items: query.data ?? [],
    loading: query.isPending,
    error: query.data === undefined && query.error ? query.error.message : null,
    refetch: () => {
      void query.refetch();
    },
  };
}
