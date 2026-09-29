// [T-9.80 · D-48] Contactos de emergencia del titular, con TanStack Query como
// los vecinos. El SDK se importa AQUÍ, en `features/`, nunca en `src/app`
// (expo-router barre esa carpeta). Estático como en `useSismos`: bajo el jest
// de móvil un `import()` dinámico RECHAZA y el mock no llega.
//
// La edad del dato sale del RELOJ (`useStaleSince`, T-5.21). Sin poll: la lista
// sólo cambia cuando la persona la edita, pero el AVISO lo puede cambiar el
// servidor (versión nueva), y eso es lo que invalida el consentimiento.
import {
  deleteEmergencyContactsMeEmergencyContactsDelete,
  getEmergencyContactsMeEmergencyContactsGet,
  putEmergencyContactsMeEmergencyContactsPut,
  type ContactosIn,
  type ContactosOut,
} from "@takab/sdk";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";

import { useStaleSince } from "@/ui/useStaleSince";

import { erroresDelServidor, type ErroresPorCampo } from "./validacion";

export const CONTACTOS_QUERY_KEY = ["me-emergency-contacts"] as const;

/** Cuánto se sigue afirmando que la lista y el aviso son los vigentes. */
export const CONTACTOS_STALE_MS = 300_000;

const SIN_CONEXION = "No se pudieron consultar sus contactos de emergencia.";
const NO_SE_GUARDO = "No se pudo guardar la lista. Nada ha cambiado en el servidor: inténtelo de nuevo.";
const NO_SE_BORRO = "No se pudieron borrar los contactos. Siguen guardados: inténtelo de nuevo.";

export type Desenlace =
  | { tipo: "ok" }
  | { tipo: "consentimiento" }
  | { tipo: "validacion"; campos: ErroresPorCampo; general: string | null }
  | { tipo: "fallo"; mensaje: string };

async function leerContactos(): Promise<ContactosOut> {
  const res = await getEmergencyContactsMeEmergencyContactsGet({});
  if (!res.data) {
    throw new Error(`contactos no disponibles (${res.response?.status ?? 0})`);
  }
  return res.data;
}

function useContactosQuery() {
  return useQuery({ queryKey: CONTACTOS_QUERY_KEY, queryFn: leerContactos });
}

/** Para la fila de CUENTA: «N de 3», o `null` si todavía no se sabe. */
export function useConteoContactos(): number | null {
  const q = useContactosQuery();
  return q.data ? q.data.contactos.length : null;
}

export function useEmergencyContacts(): {
  data: ContactosOut | null;
  loading: boolean;
  error: string | null;
  staleSinceMs: number | null;
  refetch: () => void;
  guardar: (body: ContactosIn) => Promise<Desenlace>;
  borrarTodos: () => Promise<Desenlace>;
} {
  const qc = useQueryClient();
  const q = useContactosQuery();
  const staleSinceMs = useStaleSince(q.dataUpdatedAt, CONTACTOS_STALE_MS / 3);
  const refetch = q.refetch;

  const guardar = useCallback(
    async (body: ContactosIn): Promise<Desenlace> => {
      try {
              const res = await putEmergencyContactsMeEmergencyContactsPut({ body });
        if (res.data) {
          qc.setQueryData(CONTACTOS_QUERY_KEY, res.data);
          return { tipo: "ok" };
        }
        const status = res.response?.status ?? 0;
        if (status === 409) {
          // El aviso cambió de versión: se recarga para que la persona lea el
          // texto NUEVO antes de volver a aceptar.
          await refetch();
          return { tipo: "consentimiento" };
        }
        if (status === 422) {
          const detail = (res.error as { detail?: unknown } | undefined)?.detail;
          return { tipo: "validacion", ...erroresDelServidor(detail) };
        }
        return { tipo: "fallo", mensaje: NO_SE_GUARDO };
      } catch {
        return { tipo: "fallo", mensaje: NO_SE_GUARDO };
      }
    },
    [qc, refetch],
  );

  const borrarTodos = useCallback(async (): Promise<Desenlace> => {
    try {
          const res = await deleteEmergencyContactsMeEmergencyContactsDelete({});
      const status = res.response?.status ?? 0;
      if (status < 200 || status >= 300) {
        return { tipo: "fallo", mensaje: NO_SE_BORRO };
      }
      qc.setQueryData<ContactosOut>(CONTACTOS_QUERY_KEY, (prev) =>
        prev ? { ...prev, contactos: [] } : prev,
      );
      return { tipo: "ok" };
    } catch {
      return { tipo: "fallo", mensaje: NO_SE_BORRO };
    }
  }, [qc]);

  const data = q.data ?? null;
  return {
    data,
    loading: q.isLoading && data === null,
    error: q.isError && data === null ? SIN_CONEXION : null,
    staleSinceMs,
    refetch: () => {
      void refetch();
    },
    guardar,
    borrarTodos,
  };
}
