import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useCallback, useMemo } from "react";

import {
  listEventsEventsGet,
  listIncidentsIncidentsGet,
  listRuleSetsRuleSetsGet,
  listSitesSitesGet,
} from "@takab/sdk";
import type { IncidentPage, RuleSetOut, SeismicEventOut, SiteOut } from "@takab/sdk";

import { activeConfigFor, buildRows, minNodesFrom } from "./model";
import type { TriageRow } from "./model";

/** El historial es post-evento: no hay nada que refrescar cada segundo. */
export const TRIAGE_STALE_MS = 120_000;

/** Tamaño de página del keyset del servidor (T-1.58: el triage YA pagina). */
export const HISTORY_LIMIT = 50;

export interface TriageFilters {
  /** null = TODAS. Valor del CHECK de incidents.severity. */
  severity: string | null;
  /** Prefijo de event_id — es lo ÚNICO que el servidor sabe buscar (`q`). */
  q: string;
  /** yyyy-mm-dd del date picker (día LOCAL); null = sin acotar (T-1.57/58). */
  from: string | null;
  to: string | null;
}

class TriageRequestError extends Error {
  constructor(resource: string, status: number) {
    super(`GET ${resource} falló (${status})`);
    this.name = "TriageRequestError";
  }
}

/** Medianoche LOCAL del día del picker → RFC3339 (el server compara opened_at). */
function dayStartIso(day: string): string {
  return new Date(`${day}T00:00:00`).toISOString();
}

/** Cota EXCLUSIVA del server para incluir el día `to` completo: día siguiente. */
function nextDayIso(day: string): string {
  const d = new Date(`${day}T00:00:00`);
  d.setDate(d.getDate() + 1);
  return d.toISOString();
}

async function fetchIncidentsPage(
  filters: TriageFilters,
  cursor: string | null,
): Promise<IncidentPage> {
  const { data, response } = await listIncidentsIncidentsGet({
    query: {
      severity: filters.severity,
      q: filters.q.trim() === "" ? null : filters.q.trim(),
      from: filters.from ? dayStartIso(filters.from) : null,
      to: filters.to ? nextDayIso(filters.to) : null,
      cursor,
      limit: HISTORY_LIMIT,
    },
  });
  if (data === undefined) {
    throw new TriageRequestError("/incidents", response.status);
  }
  return data;
}

async function fetchEvents(): Promise<SeismicEventOut[]> {
  const { data, response } = await listEventsEventsGet({ query: { limit: HISTORY_LIMIT } });
  if (data === undefined) {
    throw new TriageRequestError("/events", response.status);
  }
  return data.items;
}

async function fetchSites(): Promise<SiteOut[]> {
  const { data, response } = await listSitesSitesGet();
  if (data === undefined) {
    throw new TriageRequestError("/sites", response.status);
  }
  return data;
}

async function fetchRuleSets(): Promise<RuleSetOut[]> {
  const { data, response } = await listRuleSetsRuleSetsGet();
  if (data === undefined) {
    throw new TriageRequestError("/rule-sets", response.status);
  }
  return data.items;
}

export interface TriageData {
  rows: TriageRow[];
  /** `config.quorum.min_nodes` ACTUAL que aplica a un sitio (scope site preferente
   * sobre tenant, como el motor). Es contexto de configuración, no un veredicto. */
  minNodesFor: (siteId: string | null) => number | null;
  loading: boolean;
  error: string | null;
  dataUpdatedAt: number;
  refetch: () => void;
  /** Paginación keyset (T-1.58): ¿hay más páginas en el servidor? */
  hasMore: boolean;
  loadingMore: boolean;
  loadMore: () => void;
}

/**
 * Historial de triage: `/incidents` (por sitio, con PGA/PGV/severidad) enriquecido
 * con `/events` (magnitud, epicentro, nodos) y `/sites`. Ningún endpoint devuelve
 * la fila del mockup, que confundía evento con incidente.
 *
 * T-1.58: paginación keyset real (`useInfiniteQuery` sobre `next_cursor`) + rango
 * de fechas del servidor (`from`/`to` de T-1.57). Cambiar cualquier filtro reinicia
 * la paginación (queryKey nueva).
 *
 * `/events`, `/sites` y `/rule-sets` degradan sin tumbar la página: sin ellos la
 * tabla pierde contexto, no el historial.
 */
export function useTriage(filters: TriageFilters): TriageData {
  const incidents = useInfiniteQuery({
    queryKey: [
      "incidents",
      "history",
      filters.severity,
      filters.q.trim(),
      filters.from,
      filters.to,
    ],
    queryFn: ({ pageParam }) => fetchIncidentsPage(filters, pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor ?? null,
    staleTime: TRIAGE_STALE_MS,
  });
  const events = useQuery({
    queryKey: ["events", "history"],
    queryFn: fetchEvents,
    staleTime: TRIAGE_STALE_MS,
  });
  const sites = useQuery({ queryKey: ["sites"], queryFn: fetchSites, staleTime: 300_000 });
  const ruleSets = useQuery({
    queryKey: ["rule-sets"],
    queryFn: fetchRuleSets,
    staleTime: 300_000,
  });

  const incidentItems = useMemo(
    () => incidents.data?.pages.flatMap((p) => p.items),
    [incidents.data],
  );
  const rows = useMemo(
    () => buildRows(incidentItems, events.data, sites.data),
    [incidentItems, events.data, sites.data],
  );

  const minNodesFor = useCallback(
    (siteId: string | null) => minNodesFrom(activeConfigFor(ruleSets.data, siteId)),
    [ruleSets.data],
  );

  return {
    rows,
    minNodesFor,
    loading: incidents.isPending,
    error: incidents.data === undefined && incidents.error ? incidents.error.message : null,
    dataUpdatedAt: incidents.dataUpdatedAt,
    refetch: () => {
      void incidents.refetch();
    },
    hasMore: incidents.hasNextPage,
    loadingMore: incidents.isFetchingNextPage,
    loadMore: () => {
      void incidents.fetchNextPage();
    },
  };
}
