// [T-9.65 · D-44] El mapa de calor del último sismo sentido en el inmueble.
// Mismo patrón que `features/sismos/useSismos.ts`: el SDK se importa AQUÍ, nunca
// en `src/app`, y la edad del dato sale del reloj (`useStaleSince`).
import { mapaDeCalorSitesSiteIdMapaDeCalorGet, type MapaDeCalorMovilOut } from "@takab/sdk";
import { useQuery } from "@tanstack/react-query";

import type { LecturaSismica } from "@/features/sismos/useSismos";
import { SISMOS_POLL_MS } from "@/features/sismos/useSismos";
import { useStaleSince } from "@/ui/useStaleSince";

const SIN_MAPA = "No se pudo consultar el mapa de calor del inmueble.";

export function useMapaDeCalor(siteId: string | null): LecturaSismica<MapaDeCalorMovilOut> {
  const q = useQuery({
    queryKey: ["mapa-de-calor", siteId],
    enabled: siteId != null,
    refetchInterval: SISMOS_POLL_MS,
    queryFn: async (): Promise<MapaDeCalorMovilOut> => {
      const res = await mapaDeCalorSitesSiteIdMapaDeCalorGet({ path: { site_id: siteId as string } });
      if (!res.data) {
        throw new Error(`mapa de calor no disponible (${res.response?.status ?? 0})`);
      }
      return res.data;
    },
  });
  const staleSinceMs = useStaleSince(q.dataUpdatedAt, SISMOS_POLL_MS);
  const data = q.data ?? null;
  return {
    data,
    loading: siteId != null && q.isLoading && data === null,
    error: q.isError && data === null ? SIN_MAPA : null,
    staleSinceMs,
    refetch: () => {
      void q.refetch();
    },
  };
}
