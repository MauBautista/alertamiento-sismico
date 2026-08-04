// Simulacro institucional (T-1.60 · T-2.48): el banner NO-real de la consola.
//
// Poll de 10 s a /drills/active — el drill dura minutos y NO es telemetría de
// vida (el push por WS queda anotado como mejora). Iniciar/parar/cancelar
// reutiliza el gate de matriz `drill_start`; solo superadmin/tenant_admin lo
// tienen.
//
// [T-2.48] Se añade la AGENDA (`GET /drills?kind=scheduled`), que alimenta el
// banner de simulacro ARMADO. Aquí no hay temporizador que dispare nada: el
// disparo sigue siendo un clic humano sobre `start({ fromScheduled })` con
// sesión viva (regla de oro 8). Un ejecutor automático de actuadores desde un
// reloj del navegador sería precisamente lo que esa regla prohíbe.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  activeDrillDrillsActiveGet,
  cancelDrillDrillsDrillIdCancelPost,
  listDrillsDrillsGet,
  startDrillDrillsPost,
  stopDrillDrillsDrillIdStopPost,
} from "@takab/sdk";
import type { DrillOut } from "@takab/sdk";

export const DRILL_POLL_MS = 10_000;
export const ACTIVE_DRILL_KEY = ["drills", "active"] as const;
export const SCHEDULED_DRILL_KEY = ["drills", "scheduled"] as const;
export const DRILL_LIST_KEY = ["drills", "list"] as const;

/** Cuántas agendas se traen para derivar el banner armado. */
const SCHEDULED_PAGE = 20;

export interface StartDrillInput {
  /** Duración de la ventana; ausente hereda la de la agenda al ejecutar. */
  durationS?: number;
  note?: string | null;
  /** ``null``/ausente = todos los sitios comandables del tenant. */
  siteIds?: string[] | null;
  /** ISO UTC: crea una AGENDA en vez de disparar el simulacro. */
  scheduledAt?: string | null;
  /** Ejecuta AHORA la agenda indicada y la consume. */
  fromScheduled?: string | null;
}

export interface ActiveDrillData {
  drill: DrillOut | null;
  /** Agendas pendientes del tenant (el banner armado elige la más próxima). */
  scheduled: DrillOut[];
  loading: boolean;
  /**
   * Fallo de LECTURA. Se expone aparte del error de mutación porque el banner
   * NO puede desaparecer por esto: un simulacro en curso que deja de anunciarse
   * es indistinguible de una alerta real para quien está en el edificio.
   */
  readError: string | null;
  /** Epoch ms del último snapshot bueno de /drills/active (0 = ninguno). */
  updatedAt: number;
  refetch: () => void;
  start: (input?: StartDrillInput) => void;
  stop: (drillId: string) => void;
  cancel: (drillId: string) => void;
  pending: boolean;
  /** Error de la última MUTACIÓN (iniciar/terminar/cancelar). */
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

  const scheduled = useQuery({
    queryKey: SCHEDULED_DRILL_KEY,
    queryFn: async () => {
      const { data, response } = await listDrillsDrillsGet({
        query: { kind: "scheduled", limit: SCHEDULED_PAGE },
      });
      if (data === undefined) {
        throw new Error(`GET /drills?kind=scheduled falló (${response.status})`);
      }
      return data;
    },
    enabled,
    refetchInterval: DRILL_POLL_MS * 3,
    staleTime: DRILL_POLL_MS,
  });

  const invalidateAll = async () => {
    await queryClient.invalidateQueries({ queryKey: ACTIVE_DRILL_KEY });
    await queryClient.invalidateQueries({ queryKey: SCHEDULED_DRILL_KEY });
    await queryClient.invalidateQueries({ queryKey: DRILL_LIST_KEY });
  };

  const start = useMutation({
    mutationFn: async (input: StartDrillInput) => {
      const { data, response } = await startDrillDrillsPost({
        body: {
          ...(input.durationS === undefined ? {} : { duration_s: input.durationS }),
          note: input.note ?? null,
          site_ids: input.siteIds ?? null,
          scheduled_at: input.scheduledAt ?? null,
          from_scheduled: input.fromScheduled ?? null,
        },
      });
      if (data === undefined) {
        throw new Error(`el simulacro no arrancó (HTTP ${response.status})`);
      }
      return data;
    },
    onSuccess: invalidateAll,
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
    onSuccess: invalidateAll,
  });

  const cancel = useMutation({
    mutationFn: async (drillId: string) => {
      const { data, response } = await cancelDrillDrillsDrillIdCancelPost({
        path: { drill_id: drillId },
      });
      if (data === undefined) {
        throw new Error(`el simulacro no se canceló (HTTP ${response.status})`);
      }
      return data;
    },
    onSuccess: invalidateAll,
  });

  // Se reporta AUNQUE haya datos en caché: en react-query `data` y `error`
  // conviven cuando falla un refetch de fondo. Quien pinta decide qué hacer —
  // con último dato conocido lo conserva y lo rotula RETENIDO; sin dato alguno
  // muestra el error. Lo que NUNCA puede pasar es callar.
  const readError = active.error?.message ?? scheduled.error?.message ?? null;

  return {
    drill: active.data?.drill ?? null,
    scheduled: scheduled.data?.items ?? [],
    loading: enabled && active.isPending,
    readError,
    updatedAt: active.dataUpdatedAt,
    refetch: () => {
      void active.refetch();
      void scheduled.refetch();
    },
    start: (input) => start.mutate(input ?? {}),
    stop: (drillId) => stop.mutate(drillId),
    cancel: (drillId) => cancel.mutate(drillId),
    pending: start.isPending || stop.isPending || cancel.isPending,
    error: start.error?.message ?? stop.error?.message ?? cancel.error?.message ?? null,
  };
}
