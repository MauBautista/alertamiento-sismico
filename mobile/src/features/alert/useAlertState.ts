// Hook de la máquina de crisis: la PUSH despierta (invalidación) y el REST
// reconstruye (spec §4.1). Poll dinámico honesto: 30 s en reposo, 5 s con
// incidente vivo. El estado derivado NUNCA sale de datos locales — solo de
// mobile-state + los check-ins PROPIOS.
import {
  listMyCheckinsIncidentsIncidentIdCheckinsGet,
  mobileStateSitesSiteIdMobileStateGet,
  type MobileStateOut,
} from "@takab/sdk";
import { useQuery } from "@tanstack/react-query";

import { useStaleSince } from "@/ui/useStaleSince";

import { hasLocalCheckin } from "@/offline/queue";
import { useQueueStore } from "@/offline/queue.store";

import { type AlertState, deriveAlertState } from "./machine";

export const MOBILE_STATE_KEY = "mobile-state";

const IDLE_POLL_MS = 30_000;
const CRISIS_POLL_MS = 5_000;

export type AlertSnapshot = {
  /** null mientras no haya datos (la UI declara "verificando", jamás finge). */
  state: AlertState | null;
  data: MobileStateOut | null;
  hasOwnCheckin: boolean;
  refetch: () => void;
  dataUpdatedAt: number;
  /** [T-2.07] Para el contrato StateFrame: cargando SIN datos. */
  loading: boolean;
  /** Error SIN datos que mostrar (con datos viejos habla `stale`). */
  error: string | null;
  /**
   * [T-5.21] Epoch ms del dato cuando YA ES VIEJO, o `null` si es fresco — la
   * entrada que `StateFrame` espera.
   *
   * Sustituye a un `stale: boolean` que valía `isError && data !== undefined`:
   * eso contestaba «¿está fallando el refetch?» y no «¿de cuándo es esto?». Con
   * red sana y un estado de hace diez minutos, valía `false` y **siete
   * pantallas afirmaban frescura**. Sale del reloj contra el intervalo de poll.
   */
  staleSinceMs: number | null;
};

export function useAlertState(siteId: string | null): AlertSnapshot {
  const mobileState = useQuery({
    queryKey: [MOBILE_STATE_KEY, siteId],
    enabled: siteId != null,
    queryFn: async () => {
      const res = await mobileStateSitesSiteIdMobileStateGet({
        path: { site_id: siteId as string },
      });
      if (!res.data) {
        throw new Error("mobile-state no disponible");
      }
      return res.data;
    },
    refetchInterval: (query) =>
      query.state.data && query.state.data.phase !== "idle" ? CRISIS_POLL_MS : IDLE_POLL_MS,
  });

  const incidentId = mobileState.data?.incident?.incident_id ?? null;
  const checkins = useQuery({
    queryKey: ["my-checkins", incidentId],
    enabled: incidentId != null,
    queryFn: async () => {
      const res = await listMyCheckinsIncidentsIncidentIdCheckinsGet({
        path: { incident_id: incidentId as string },
        query: { scope: "me" },
      });
      if (!res.data) {
        throw new Error("check-ins no disponibles");
      }
      return res.data;
    },
    refetchInterval: CRISIS_POLL_MS,
  });

  // [T-2.06] El check-in ENCOLADO en este dispositivo cuenta como propio
  // (existe y viajará — el servidor deduplica por checkin_id); uno "failed"
  // NO cuenta: jamás aterrizó y el usuario debe poder reintentar.
  const queueItems = useQueueStore((s) => s.items);
  const hasOwnCheckin =
    (checkins.data?.length ?? 0) > 0 ||
    (incidentId != null && hasLocalCheckin(queueItems, incidentId));
  const state = mobileState.data
    ? deriveAlertState(mobileState.data.phase, hasOwnCheckin)
    : null;
  // El poll es variable (`CRISIS_POLL_MS` en crisis, `IDLE_POLL_MS` en reposo):
  // se mide contra el que de verdad está corriendo, o en reposo el dato saldría
  // viejo cada quince segundos y el aviso se volvería ruido que nadie mira.
  const pollVigente =
    mobileState.data && mobileState.data.phase !== "idle" ? CRISIS_POLL_MS : IDLE_POLL_MS;
  const staleSinceMs = useStaleSince(mobileState.dataUpdatedAt, pollVigente);

  return {
    state,
    data: mobileState.data ?? null,
    hasOwnCheckin,
    refetch: () => {
      void mobileState.refetch();
    },
    dataUpdatedAt: mobileState.dataUpdatedAt,
    loading: siteId != null && mobileState.isLoading && mobileState.data === undefined,
    error:
      mobileState.isError && mobileState.data === undefined
        ? "No se pudo consultar el estado del sitio."
        : null,
    staleSinceMs,
  };
}
