// Simulacro institucional (T-1.60): el banner NO-real de la consola.
//
// Poll de 10 s a /drills/active — el drill dura minutos y NO es telemetría de
// vida (el push por WS queda anotado como mejora). Iniciar/parar reutiliza el
// gate de matriz `drill_start`; solo superadmin/tenant_admin lo tienen.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  activeDrillDrillsActiveGet,
  startDrillDrillsPost,
  stopDrillDrillsDrillIdStopPost,
} from "@takab/sdk";
import type { DrillOut } from "@takab/sdk";

export const DRILL_POLL_MS = 10_000;
export const ACTIVE_DRILL_KEY = ["drills", "active"] as const;

export interface ActiveDrillData {
  drill: DrillOut | null;
  loading: boolean;
  /** POST /drills a TODOS los sitios comandables del tenant. */
  start: (durationS: number, note?: string) => void;
  stop: (drillId: string) => void;
  pending: boolean;
  error: string | null;
}

export function useActiveDrill(enabled: boolean = true): ActiveDrillData {
  const queryClient = useQueryClient();

  const active = useQuery({
    queryKey: ACTIVE_DRILL_KEY,
    queryFn: async () => {
      const { data, response } = await activeDrillDrillsActiveGet();
      if (data === undefined) {
        throw new Error(`GET /drills/active falló (${response.status})`);
      }
      return data;
    },
    enabled,
    refetchInterval: DRILL_POLL_MS,
    staleTime: DRILL_POLL_MS / 2,
  });

  const start = useMutation({
    mutationFn: async (input: { durationS: number; note?: string }) => {
      const { data, response } = await startDrillDrillsPost({
        body: { duration_s: input.durationS, note: input.note ?? null },
      });
      if (data === undefined) {
        throw new Error(`el simulacro no arrancó (HTTP ${response.status})`);
      }
      return data;
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ACTIVE_DRILL_KEY });
      await queryClient.invalidateQueries({ queryKey: ["drills", "list"] });
    },
  });

  const stop = useMutation({
    mutationFn: async (drillId: string) => {
      const { data, response } = await stopDrillDrillsDrillIdStopPost({
        path: { drill_id: drillId },
      });
      if (data === undefined) {
        throw new Error(`el simulacro no se detuvo (HTTP ${response.status})`);
      }
      return data;
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ACTIVE_DRILL_KEY });
    },
  });

  return {
    drill: active.data?.drill ?? null,
    loading: active.isPending,
    start: (durationS, note) => start.mutate({ durationS, note }),
    stop: (drillId) => stop.mutate(drillId),
    pending: start.isPending || stop.isPending,
    error: start.error?.message ?? stop.error?.message ?? null,
  };
}
