// Historial de simulacros (T-2.48): keyset real sobre `GET /drills`.
//
// Es el registro de cumplimiento que se le enseña a Protección Civil, así que
// pagina de verdad (`next_cursor`) en vez de quedarse con los 50 más recientes:
// un tenant con simulacros trimestrales por edificio los agota en un año.

import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";

import { drillReportDrillsDrillIdReportPost, listDrillsDrillsGet } from "@takab/sdk";
import type { DrillList, DrillOut } from "@takab/sdk";

import type { PendingDownload } from "../../lib/download";
import { DRILL_LIST_KEY } from "./useActiveDrill";

export const DRILL_PAGE_SIZE = 25;

export type DrillKind = "all" | "executed" | "scheduled";

export interface DrillHistoryData {
  items: DrillOut[];
  loading: boolean;
  error: string | null;
  /** Epoch ms del último snapshot bueno: rotula el historial RETENIDO. */
  updatedAt: number;
  hasMore: boolean;
  loadingMore: boolean;
  loadMore: () => void;
  refetch: () => void;
}

async function fetchPage(kind: DrillKind, cursor: string | null): Promise<DrillList> {
  const { data, response } = await listDrillsDrillsGet({
    query: {
      kind,
      limit: DRILL_PAGE_SIZE,
      ...(cursor === null ? {} : { cursor }),
    },
  });
  if (data === undefined) {
    throw new Error(`GET /drills falló (${response.status})`);
  }
  return data;
}

export function useDrills(kind: DrillKind = "all"): DrillHistoryData {
  const query = useInfiniteQuery({
    queryKey: [...DRILL_LIST_KEY, kind],
    queryFn: ({ pageParam }) => fetchPage(kind, pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor ?? null,
  });

  const items = useMemo(() => query.data?.pages.flatMap((p) => p.items) ?? [], [query.data]);

  return {
    items,
    loading: query.isPending,
    // `data` y `error` conviven al fallar un refetch: mientras haya páginas
    // cargadas se muestran, y el error se rotula sin borrar el historial.
    error: query.error ? query.error.message : null,
    updatedAt: query.dataUpdatedAt,
    hasMore: query.hasNextPage,
    loadingMore: query.isFetchingNextPage,
    loadMore: () => {
      void query.fetchNextPage();
    },
    refetch: () => {
      void query.refetch();
    },
  };
}

// ── [T-5.14] Generar el reporte del simulacro ───────────────────────────────
//
// Mismo patrón que el dictamen PDF (`useIncidentDetail`), y por el mismo motivo
// medido: la URL presignada no existe hasta que el servidor renderiza, hashea y
// sube el documento, así que la pestaña se RESERVA dentro del gesto del usuario
// y se navega cuando llega la URL. Abrirla en el `onSuccess` la bloquea el
// navegador en silencio pasados ~5 s de activación transitoria.

export interface DrillReportData {
  /** Pide el reporte del simulacro y navega la pestaña ya reservada. */
  exportar: (drillId: string, pending: PendingDownload) => void;
  /** `drill_id` en vuelo, o `null`: el botón de ESE simulacro se deshabilita. */
  pendingId: string | null;
  error: string | null;
}

export function useDrillReport(): DrillReportData {
  const qc = useQueryClient();
  const mutation = useMutation({
    mutationFn: async (vars: { drillId: string; pending: PendingDownload }) => {
      try {
        const { data, response } = await drillReportDrillsDrillIdReportPost({
          path: { drill_id: vars.drillId },
        });
        if (data === undefined) {
          throw new Error(`POST /drills/${vars.drillId}/report falló (${response.status})`);
        }
        return data;
      } catch (err) {
        // Sin esto el operador se queda un `about:blank` huérfano delante y
        // ningún mensaje: parecería que la exportación salió bien.
        vars.pending.cancel();
        throw err;
      }
    },
    onSuccess: (data, vars) => {
      vars.pending.resolve(data.url);
      // El reporte queda inscrito como evidencia inmutable del tenant.
      void qc.invalidateQueries({ queryKey: ["evidence"] });
    },
  });

  return {
    exportar: (drillId, pending) => mutation.mutate({ drillId, pending }),
    pendingId: mutation.isPending ? mutation.variables.drillId : null,
    error: mutation.error ? mutation.error.message : null,
  };
}
