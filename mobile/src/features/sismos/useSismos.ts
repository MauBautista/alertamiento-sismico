// [T-9.62 · T-9.66 · D-46] Los datos de la pestaña SISMOS, con TanStack Query como
// el resto de los hooks de la app. El SDK se importa AQUÍ, nunca en `src/app`.
//
// La edad del dato sale del RELOJ (`useStaleSince`, T-5.21), nunca de que la
// consulta falle. `error` sólo cuando no hay NADA que mostrar: con un dato
// anterior en mano, habla el «DATOS RETENIDOS» del marco.
import {
  historialSismicoSitesSiteIdHistorialSismicoGet,
  sismosDelSitioSitesSiteIdSismosGet,
  type HistorialSismicoOut,
  type SismosDelSitioOut,
} from "@takab/sdk";
import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";

import { useStaleSince } from "@/ui/useStaleSince";

/** La ventana y el umbral que rotula el encabezado de la pestaña. */
export const SISMOS_DIAS = 90;
export const SISMOS_MIN_MAG = 4;
/** El historial del inmueble mira un año atrás (el default de la nube). */
export const HISTORIAL_DIAS = 365;

/** El catálogo se sincroniza en la nube cada pocos minutos; aquí basta con
 *  cinco. Tres pollos perdidos (15 min) y el dato del teléfono se declara viejo. */
export const SISMOS_POLL_MS = 5 * 60_000;

const SIN_CONEXION = "No se pudo consultar el catálogo de sismos. Compruebe la conexión.";
const SIN_HISTORIAL = "No se pudo consultar el historial del inmueble.";

export type LecturaSismica<T> = {
  data: T | null;
  loading: boolean;
  error: string | null;
  staleSinceMs: number | null;
  refetch: () => void;
};

export function useSismos(siteId: string | null): LecturaSismica<SismosDelSitioOut> & {
  refrescando: boolean;
  refrescar: () => Promise<void>;
} {
  const q = useQuery({
    queryKey: ["sismos-del-sitio", siteId],
    enabled: siteId != null,
    refetchInterval: SISMOS_POLL_MS,
    queryFn: async (): Promise<SismosDelSitioOut> => {
      const res = await sismosDelSitioSitesSiteIdSismosGet({
        path: { site_id: siteId as string },
        query: { dias: SISMOS_DIAS, min_mag: SISMOS_MIN_MAG },
      });
      if (!res.data) {
        throw new Error(`sismos no disponibles (${res.response?.status ?? 0})`);
      }
      return res.data;
    },
  });
  const staleSinceMs = useStaleSince(q.dataUpdatedAt, SISMOS_POLL_MS);

  // El giro del «tirar para refrescar» es SÓLO el que pidió la persona: el
  // sondeo de fondo no debe hacer aparecer el indicador cada cinco minutos.
  const [refrescando, setRefrescando] = useState(false);
  const refetch = q.refetch;
  const refrescar = useCallback(async () => {
    setRefrescando(true);
    try {
      await refetch();
    } finally {
      setRefrescando(false);
    }
  }, [refetch]);

  const data = q.data ?? null;
  return {
    data,
    loading: siteId != null && q.isLoading && data === null,
    error: q.isError && data === null ? SIN_CONEXION : null,
    staleSinceMs,
    refetch: () => {
      void refetch();
    },
    refrescando,
    refrescar,
  };
}

export function useHistorialSismico(siteId: string | null): LecturaSismica<HistorialSismicoOut> {
  const q = useQuery({
    queryKey: ["historial-sismico", siteId],
    enabled: siteId != null,
    refetchInterval: SISMOS_POLL_MS,
    queryFn: async (): Promise<HistorialSismicoOut> => {
      const res = await historialSismicoSitesSiteIdHistorialSismicoGet({
        path: { site_id: siteId as string },
        query: { dias: HISTORIAL_DIAS },
      });
      if (!res.data) {
        throw new Error(`historial no disponible (${res.response?.status ?? 0})`);
      }
      return res.data;
    },
  });
  const staleSinceMs = useStaleSince(q.dataUpdatedAt, SISMOS_POLL_MS);
  const data = q.data ?? null;
  return {
    data,
    loading: siteId != null && q.isLoading && data === null,
    error: q.isError && data === null ? SIN_HISTORIAL : null,
    staleSinceMs,
    refetch: () => {
      void q.refetch();
    },
  };
}

/** Reloj de la pestaña: la franja del catálogo sin actualizar tiene que
 *  aparecer sola cuando pasa la media hora, aunque nada más provoque un render. */
export function useAhora(ticMs = 30_000): number {
  const [ahora, setAhora] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setAhora(Date.now()), ticMs);
    return () => clearInterval(t);
  }, [ticMs]);
  return ahora;
}
