// [T-5.02 · D-27] Modo demostración — lectura y control desde la consola.
//
// Poll de 10 s, igual que el simulacro y por la misma razón: el modo dura horas
// y no es telemetría de vida. Lo consulta CUALQUIERA que tenga sesión —quien no
// puede encenderlo tiene más derecho aún a saber que está encendido: es quien se
// va a preguntar por qué no le llegó un aviso—, y encender/apagar lo gatea la
// matriz de roles, no esta capa.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  apagarDemoModeDemoModeDelete,
  encenderDemoModeDemoModePost,
  getDemoModeDemoModeGet,
} from "@takab/sdk";
import type { DemoModeOut } from "@takab/sdk";

export const DEMO_MODE_POLL_MS = 10_000;
export const DEMO_MODE_KEY = ["demo-mode"] as const;

export interface DemoModeData {
  demo: DemoModeOut | null;
  loading: boolean;
  readError: boolean;
  updatedAt: number;
  refetch: () => void;
  encender: (input: { durationS?: number; note?: string }) => void;
  apagar: () => void;
  pending: boolean;
}

export function useDemoMode(): DemoModeData {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: DEMO_MODE_KEY,
    queryFn: async () => {
      const r = await getDemoModeDemoModeGet();
      if (r.error !== undefined) throw new Error("demo-mode");
      return r.data as DemoModeOut;
    },
    refetchInterval: DEMO_MODE_POLL_MS,
  });

  const invalidar = () => void qc.invalidateQueries({ queryKey: DEMO_MODE_KEY });

  const on = useMutation({
    mutationFn: async (input: { durationS?: number; note?: string }) => {
      const r = await encenderDemoModeDemoModePost({
        body: { duration_s: input.durationS, note: input.note ?? "" },
      });
      if (r.error !== undefined) throw new Error("demo-mode-on");
      return r.data;
    },
    onSuccess: invalidar,
  });

  const off = useMutation({
    mutationFn: async () => {
      const r = await apagarDemoModeDemoModeDelete();
      if (r.error !== undefined) throw new Error("demo-mode-off");
      return r.data;
    },
    onSuccess: invalidar,
  });

  return {
    demo: q.data ?? null,
    loading: q.isLoading,
    readError: q.isError,
    updatedAt: q.dataUpdatedAt,
    refetch: () => void q.refetch(),
    encender: (input) => on.mutate(input),
    apagar: () => off.mutate(),
    pending: on.isPending || off.isPending,
  };
}
