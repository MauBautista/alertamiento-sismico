import { useQuery } from "@tanstack/react-query";
import { useCallback, useMemo } from "react";

import {
  listEventsEventsGet,
  listIncidentsIncidentsGet,
  listRuleSetsRuleSetsGet,
  listSitesSitesGet,
} from "@takab/sdk";
import type { IncidentOut, RuleSetOut, SeismicEventOut, SiteOut } from "@takab/sdk";

import { activeConfigFor, buildRows, minNodesFrom } from "./model";
import type { TriageRow } from "./model";

/** El historial es post-evento: no hay nada que refrescar cada segundo. */
export const TRIAGE_STALE_MS = 120_000;

/** Página del historial. El servidor pagina por keyset; el triage no pagina aún. */
export const HISTORY_LIMIT = 50;

export interface TriageFilters {
  /** null = TODAS. Valor del CHECK de incidents.severity. */
  severity: string | null;
  /** Prefijo de event_id — es lo ÚNICO que el servidor sabe buscar (`q`). */
  q: string;
}

class TriageRequestError extends Error {
  constructor(resource: string, status: number) {
    super(`GET ${resource} falló (${status})`);
    this.name = "TriageRequestError";
  }
}

async function fetchIncidents(filters: TriageFilters): Promise<IncidentOut[]> {
  const { data, response } = await listIncidentsIncidentsGet({
    query: {
      severity: filters.severity,
      q: filters.q.trim() === "" ? null : filters.q.trim(),
      limit: HISTORY_LIMIT,
    },
  });
  if (data === undefined) {
    throw new TriageRequestError("/incidents", response.status);
  }
  return data.items;
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
}

/**
 * Historial de triage: `/incidents` (por sitio, con PGA/PGV/severidad) enriquecido
 * con `/events` (magnitud, epicentro, nodos) y `/sites`. Ningún endpoint devuelve
 * la fila del mockup, que confundía evento con incidente.
 *
 * `/events`, `/sites` y `/rule-sets` degradan sin tumbar la página: sin ellos la
 * tabla pierde contexto, no el historial.
 */
export function useTriage(filters: TriageFilters): TriageData {
  const incidents = useQuery({
    queryKey: ["incidents", "history", filters.severity, filters.q.trim()],
    queryFn: () => fetchIncidents(filters),
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

  const rows = useMemo(
    () => buildRows(incidents.data, events.data, sites.data),
    [incidents.data, events.data, sites.data],
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
  };
}
