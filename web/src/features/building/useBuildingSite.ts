// La identidad del edificio (nombre, código, coordenadas) para la cabecera de
// /building/:siteId.
//
// [A-112 · T-8.09] Vivía inline en `BuildingPage` como una consulta SIN cadencia:
// se pedía una vez y nunca más, y a los 5 minutos el marco rotulaba «DATOS
// RETENIDOS» con el sistema sano. Umbral y cadencia viven juntos aquí para que
// nadie pueda mover uno sin ver el otro — la misma pareja que `useSiteMetrics`.

import { useQuery } from "@tanstack/react-query";

import { getSiteSitesSiteIdGet } from "@takab/sdk";

/**
 * [T-6.06] El sitio casi no cambia, y su edad importa sólo para no afirmar
 * identidad sobre una lectura vieja.
 */
export const SITE_STALE_MS = 300_000;

/** Relectura: dos oportunidades antes del umbral, así un fallo suelto no rotula. */
export const SITE_REFRESH_MS = 120_000;

export function useBuildingSite(siteId: string) {
  return useQuery({
    queryKey: ["site", siteId],
    queryFn: async () => {
      const { data, response } = await getSiteSitesSiteIdGet({ path: { site_id: siteId } });
      if (data === undefined) throw new Error(`GET /sites/${siteId} falló (${response.status})`);
      return data;
    },
    refetchInterval: SITE_REFRESH_MS,
  });
}
