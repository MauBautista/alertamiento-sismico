// La cadena de acuse de un incidente (T-5.15): quién recibió la alerta.
//
// `notification_jobs` guardaba el destinatario y la confirmación de entrega
// desde la `0040` y **no la leía ningún router**: era una pregunta contestable
// en la base y no por la API ni por ninguna pantalla. Este hook es el otro
// extremo de esa lectura.

import { useQuery } from "@tanstack/react-query";

import { incidentNotificationsIncidentsIncidentIdNotificationsGet } from "@takab/sdk";
import type { NotificationJobOut, NotifyChainOut } from "@takab/sdk";

import { useNow } from "../../lib/useNow";
import { staleSinceOf } from "./staleness";

export interface NotifyChainData {
  items: NotificationJobOut[];
  /** Cuántos tienen entrega CONFIRMADA. Del servidor: no se recuenta aquí. */
  deliveredCount: number;
  loading: boolean;
  readError: boolean;
  /** Epoch ms del último dato bueno cuando ya es viejo (regla de oro 7). */
  staleSince: number | null;
  refetch: () => void;
}

export const NOTIFY_CHAIN_KEY = "notify-chain";

async function fetchChain(incidentId: string): Promise<NotifyChainOut> {
  const { data, response } = await incidentNotificationsIncidentsIncidentIdNotificationsGet({
    path: { incident_id: incidentId },
  });
  if (data === undefined) {
    throw new Error(`GET /incidents/${incidentId}/notifications falló (${response.status})`);
  }
  return data;
}

export function useNotifyChain(incidentId: string): NotifyChainData {
  const query = useQuery({
    queryKey: [NOTIFY_CHAIN_KEY, incidentId],
    queryFn: () => fetchChain(incidentId),
  });
  const now = useNow();

  return {
    items: query.data?.items ?? [],
    deliveredCount: query.data?.delivered_count ?? 0,
    loading: query.isPending,
    readError: query.error !== null,
    staleSince: staleSinceOf(query.dataUpdatedAt, now),
    refetch: () => void query.refetch(),
  };
}
