import { useInfiniteQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { listAuditAuditGet } from "@takab/sdk";
import type { AuditRowOut } from "@takab/sdk";

/** El audit trail es append-only: nada cambia hacia atrás, solo se añade al frente. */
export const AUDIT_REFETCH_MS = 60_000;

/** Sin dato nuevo tras este umbral el panel pasa a DATOS RETENIDOS. */
export const AUDIT_STALE_MS = 180_000;

export interface AuditFilters {
  actor: string;
  verb: string;
  /** Prefijo del objeto (`incident:`, `gateway:`…), no coincidencia exacta. */
  object: string;
  /** RFC3339 o `datetime-local`; vacío = sin límite por ese lado. */
  from: string;
  to: string;
}

export const EMPTY_FILTERS: AuditFilters = { actor: "", verb: "", object: "", from: "", to: "" };

export function isFiltering(f: AuditFilters): boolean {
  return Object.values(f).some((v) => v.trim() !== "");
}

class AuditRequestError extends Error {
  constructor(status: number) {
    super(
      status === 403
        ? "SIN PERMISO · tu rol no supervisa la bitácora."
        : `GET /audit falló (${status})`,
    );
    this.name = "AuditRequestError";
  }
}

/**
 * `datetime-local` entrega `2026-08-04T10:30` (sin zona). El servidor parsea
 * RFC3339 y asume UTC cuando falta el offset (`routers/_common.parse_ts`), así que
 * se manda explícito: dejar que el navegador decida haría que dos operadores en
 * husos distintos vieran ventanas distintas con el mismo formulario.
 */
function toRfc3339(value: string): string | undefined {
  const raw = value.trim();
  if (raw === "") {
    return undefined;
  }
  if (/(Z|[+-]\d{2}:\d{2})$/.test(raw)) {
    return raw;
  }
  return /T\d{2}:\d{2}$/.test(raw) ? `${raw}:00Z` : `${raw}Z`;
}

function queryFor(filters: AuditFilters, cursor: string | null) {
  const query: Record<string, string> = {};
  if (filters.actor.trim()) query.actor = filters.actor.trim();
  if (filters.verb.trim()) query.verb = filters.verb.trim();
  if (filters.object.trim()) query.object = filters.object.trim();
  const from = toRfc3339(filters.from);
  const to = toRfc3339(filters.to);
  if (from) query.from = from;
  if (to) query.to = to;
  if (cursor) query.cursor = cursor;
  return query;
}

export interface AuditData {
  rows: AuditRowOut[];
  loading: boolean;
  error: string | null;
  dataUpdatedAt: number;
  hasMore: boolean;
  loadingMore: boolean;
  loadMore: () => void;
  refetch: () => void;
}

/**
 * Bitácora paginada por keyset. Deliberadamente NO filtra en el cliente: la RLS
 * `audit_read` decide qué filas existen para este rol y `GET /audit` ya trae los
 * filtros; replicarlos aquí daría dos verdades y una de ellas mentiría en cuanto
 * llegara la segunda página.
 */
export function useAudit(filters: AuditFilters): AuditData {
  const query = useInfiniteQuery({
    queryKey: ["audit", filters],
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }) => {
      const { data, response } = await listAuditAuditGet({
        query: queryFor(filters, pageParam),
      });
      if (data === undefined) {
        throw new AuditRequestError(response.status);
      }
      return data;
    },
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    refetchInterval: AUDIT_REFETCH_MS,
  });

  const rows = useMemo(
    () => (query.data?.pages ?? []).flatMap((p) => p.items),
    [query.data?.pages],
  );

  return {
    rows,
    loading: query.isPending,
    // Con páginas ya cargadas manda el stale, no el error: el dato viejo sigue
    // siendo cierto (la tabla es append-only), solo dejó de estar al día.
    error: query.data === undefined && query.error ? query.error.message : null,
    dataUpdatedAt: query.dataUpdatedAt,
    hasMore: query.hasNextPage,
    loadingMore: query.isFetchingNextPage,
    loadMore: () => void query.fetchNextPage(),
    refetch: () => void query.refetch(),
  };
}
