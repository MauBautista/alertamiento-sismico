// Historial de simulacros (T-2.48): keyset real sobre `GET /drills`.
//
// Es el registro de cumplimiento que se le enseña a Protección Civil, así que
// pagina de verdad (`next_cursor`) en vez de quedarse con los 50 más recientes:
// un tenant con simulacros trimestrales por edificio los agota en un año.

import { useInfiniteQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { listDrillsDrillsGet } from "@takab/sdk";
import type { DrillList, DrillOut } from "@takab/sdk";

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
