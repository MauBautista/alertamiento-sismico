// [T-9.41] El estado del INFORME AUTOMÁTICO post-evento (T-9.4x).
//
// `GET /incidents/{id}/post-event-report` responde 404 `sin_informe` cuando
// todavía no tocaba generarlo (ni firma, ni cierre, ni plazo). Eso NO es un
// error: es el estado «sin informe», y se pinta como tal. Cualquier otro fallo sí
// es un error, y no se confunde con «sin informe».

import { useQuery } from "@tanstack/react-query";

import { getPostEventReportIncidentsIncidentIdPostEventReportGet } from "@takab/sdk";
import type { PostEventReportOut } from "@takab/sdk";

import { useNow } from "../../lib/useNow";
import { staleSinceOf } from "../triage/staleness";
import { leer } from "./respuesta";

export const INFORME_KEY = (id: string) => ["post-event-report", id] as const;

/** Mientras el worker lo genera, se vuelve a preguntar; en ok/fallido, no. */
export const INFORME_PENDIENTE_REFETCH_MS = 10_000;

export function useInformeAutomatico(incidentId: string) {
  const now = useNow(30_000);
  const q = useQuery({
    queryKey: INFORME_KEY(incidentId),
    queryFn: async (): Promise<PostEventReportOut | null> => {
      const r = leer(
        await getPostEventReportIncidentsIncidentIdPostEventReportGet({
          path: { incident_id: incidentId },
        }),
      );
      if (r.ok) return r.data;
      if (r.status === 404) return null;
      throw new Error(
        `GET /incidents/{id}/post-event-report falló (${r.status ?? "sin respuesta"})`,
      );
    },
    refetchInterval: (query) =>
      query.state.data?.state === "pendiente" ? INFORME_PENDIENTE_REFETCH_MS : false,
  });
  return {
    /** `null` = sin informe todavía (404); `undefined` = no se sabe. */
    informe: q.data,
    loading: q.isPending,
    error: q.error ? q.error.message : null,
    staleSince: staleSinceOf(q.dataUpdatedAt, now),
    refetch: () => void q.refetch(),
  };
}
