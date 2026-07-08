// Acciones de un incidente (T-1.27): backfill REST + frames incident_action.
//
// Alimenta la traza operativa del DetalPanel (actuadores con ACK del edge,
// acuses, notificaciones). Dedup por action_id: el refetch y los frames
// convergen a las mismas filas.

import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { listIncidentActionsIncidentsIncidentIdActionsGet, TOPIC_INCIDENTS } from "@takab/sdk";
import type { IncidentActionFrame, IncidentActionOut } from "@takab/sdk";

import { useLiveSocket } from "./socket";

export function fromActionFrame(frame: IncidentActionFrame): IncidentActionOut {
  return {
    action_id: frame.action_id,
    incident_id: frame.incident_id,
    tenant_id: frame.tenant_id,
    ts: frame.ts,
    kind: frame.kind,
    actor: frame.actor,
    payload: frame.payload ?? {},
  };
}

/** Base REST + frames del incidente, dedup por action_id, orden cronológico. */
export function mergeActions(
  base: IncidentActionOut[],
  frames: IncidentActionOut[],
): IncidentActionOut[] {
  const byId = new Map(base.map((a) => [a.action_id, a]));
  for (const frame of frames) {
    byId.set(frame.action_id, frame);
  }
  return [...byId.values()].sort((a, b) => a.ts.localeCompare(b.ts));
}

export interface IncidentActionsData {
  actions: IncidentActionOut[];
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useIncidentActions(incidentId: string | null): IncidentActionsData {
  const socket = useLiveSocket();
  const query = useQuery({
    queryKey: ["incident", incidentId, "actions"],
    queryFn: async () => {
      const { data, response } = await listIncidentActionsIncidentsIncidentIdActionsGet({
        path: { incident_id: incidentId as string },
      });
      if (data === undefined) {
        throw new Error(`GET /incidents/${incidentId}/actions falló (${response.status})`);
      }
      return data;
    },
    enabled: incidentId !== null,
  });

  const [frames, setFrames] = useState<IncidentActionOut[]>([]);

  useEffect(() => {
    setFrames([]);
  }, [incidentId, query.dataUpdatedAt]);

  useEffect(() => {
    if (!socket || incidentId === null) return undefined;
    return socket.subscribe(TOPIC_INCIDENTS, (frame) => {
      if (frame.type !== "incident_action") return;
      const action = fromActionFrame(frame as IncidentActionFrame);
      if (action.incident_id !== incidentId) return;
      setFrames((prev) => [...prev, action]);
    });
  }, [socket, incidentId]);

  const actions = useMemo(() => mergeActions(query.data ?? [], frames), [query.data, frames]);

  return {
    actions,
    loading: incidentId !== null && query.isPending,
    error: query.data === undefined && query.error ? query.error.message : null,
    refetch: () => {
      void query.refetch();
    },
  };
}
