// T-2.71 · Lectura de las ventanas de mantenimiento ACTIVAS.
//
// Poll, no WebSocket, por la misma razón que `useActiveDrill`: una ventana dura
// minutos u horas y no es telemetría de vida.
//
// Lo que SÍ es distinto de un poll cualquiera, y por eso `readError` va separado
// de `items`: **el fallo de lectura no puede hacer desaparecer el banner**. Con
// las alarmas mudas, una pantalla que dice "no hay ventana" es el peor fallo
// posible de esta función — es exactamente la clase de silencio verde que esta
// fase encontró quince veces. Con último dato conocido se conserva y se rotula
// RETENIDO; sin ninguno, el fallo ES el estado y se ofrece REINTENTAR.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  closeWindowMaintenanceWindowsWindowIdClosePost,
  listWindowsMaintenanceWindowsGet,
} from "@takab/sdk";
import type { MaintenanceWindowOut } from "@takab/sdk";

export const MAINTENANCE_POLL_MS = 30_000;
export const MAINTENANCE_KEY = ["maintenance-windows", "active"] as const;

export interface MaintenanceData {
  items: MaintenanceWindowOut[];
  loading: boolean;
  /** Fallo de LECTURA — nunca vacía el banner (ver cabecera). */
  readError: string | null;
  /** Epoch ms del último snapshot bueno (0 = ninguno). */
  updatedAt: number;
  refetch: () => void;
  close: (windowId: string) => void;
  pending: boolean;
  /** Error de la última MUTACIÓN (cerrar). */
  error: string | null;
}

export function useMaintenanceWindows(enabled: boolean = true): MaintenanceData {
  const queryClient = useQueryClient();

  const active = useQuery({
    queryKey: MAINTENANCE_KEY,
    queryFn: async () => {
      const { data, response } = await listWindowsMaintenanceWindowsGet({
        query: { active: true },
      });
      if (data === undefined) {
        throw new Error(`GET /maintenance-windows falló (${response.status})`);
      }
      return data;
    },
    enabled,
    refetchInterval: MAINTENANCE_POLL_MS,
    staleTime: MAINTENANCE_POLL_MS / 2,
  });

  const close = useMutation({
    mutationFn: async (windowId: string) => {
      const { data, response } = await closeWindowMaintenanceWindowsWindowIdClosePost({
        path: { window_id: windowId },
      });
      if (data === undefined) {
        throw new Error(`la ventana no se cerró (HTTP ${response.status})`);
      }
      return data;
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: MAINTENANCE_KEY });
    },
  });

  return {
    items: active.data?.items ?? [],
    loading: enabled && active.isPending,
    // Se reporta AUNQUE haya datos en caché: en react-query `data` y `error`
    // conviven cuando falla un refetch de fondo.
    readError: active.error?.message ?? null,
    updatedAt: active.dataUpdatedAt,
    refetch: () => void active.refetch(),
    close: (windowId) => close.mutate(windowId),
    pending: close.isPending,
    error: close.error?.message ?? null,
  };
}
