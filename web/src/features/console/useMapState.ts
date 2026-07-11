// Estado del mapa SOC (T-1.27): snapshot REST + invalidación por frames live.
//
// El endpoint /telemetry/map/state ya entrega TODO derivado server-side
// (última métrica 1m + incidente abierto por sitio); los frames del canal
// live solo INVALIDAN la query (throttled) — espejo del fetch-on-notify del
// hub: el frame avisa, la verdad se re-consulta con RLS.

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { mapStateTelemetryMapStateGet, TOPIC_INCIDENTS, TOPIC_SITE_STATE } from "@takab/sdk";
import type { MapEpicenter, MapSiteState } from "@takab/sdk";

import { useLiveSocket } from "./socket";

export const MAP_REFETCH_MS = 30_000;
export const MAP_INVALIDATE_THROTTLE_MS = 5_000;

interface MapSnapshot {
  sites: MapSiteState[];
  epicenters: MapEpicenter[];
}

async function fetchMapState(): Promise<MapSnapshot> {
  const { data, response } = await mapStateTelemetryMapStateGet();
  if (data === undefined) {
    throw new Error(`GET /telemetry/map/state falló (${response.status})`);
  }
  return { sites: data.sites, epicenters: data.epicenters };
}

export interface MapStateData {
  sites: MapSiteState[];
  /** Dónde se ORIGINÓ el sismo. Vacío = no hay ninguno localizado (no es el edificio). */
  epicenters: MapEpicenter[];
  loading: boolean;
  error: string | null;
  dataUpdatedAt: number;
  refetch: () => void;
}

export function useMapState(): MapStateData {
  const socket = useLiveSocket();
  const queryClient = useQueryClient();
  const lastInvalidateRef = useRef(0);
  const query = useQuery({
    queryKey: ["mapState"],
    queryFn: fetchMapState,
    refetchInterval: MAP_REFETCH_MS,
  });

  useEffect(() => {
    if (!socket) return undefined;
    const invalidate = () => {
      const now = Date.now();
      if (now - lastInvalidateRef.current < MAP_INVALIDATE_THROTTLE_MS) return;
      lastInvalidateRef.current = now;
      void queryClient.invalidateQueries({ queryKey: ["mapState"] });
    };
    const offIncidents = socket.subscribe(TOPIC_INCIDENTS, invalidate);
    const offSiteState = socket.subscribe(TOPIC_SITE_STATE, invalidate);
    return () => {
      offIncidents();
      offSiteState();
    };
  }, [socket, queryClient]);

  return {
    sites: query.data?.sites ?? [],
    epicenters: query.data?.epicenters ?? [],
    loading: query.isPending,
    error: query.data === undefined && query.error ? query.error.message : null,
    dataUpdatedAt: query.dataUpdatedAt,
    refetch: () => {
      void query.refetch();
    },
  };
}
