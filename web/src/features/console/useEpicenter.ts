// Mutación de reubicación de epicentro (T-1.51) sobre POST
// /incidents/{id}/epicenter (T-1.48). Tras el éxito invalida todo lo que pinta
// el epicentro: incidentes (link de evento nuevo), mapa, eventos e historial.

import { useMutation, useQueryClient } from "@tanstack/react-query";

import {
  relocateEpicenterIncidentsIncidentIdEpicenterPost,
  type EpicenterRelocateOut,
} from "@takab/sdk";

export interface EpicenterInput {
  incidentId: string;
  lon: number;
  lat: number;
  note: string | null;
}

export function useEpicenter() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: EpicenterInput): Promise<EpicenterRelocateOut> => {
      const res = await relocateEpicenterIncidentsIncidentIdEpicenterPost({
        path: { incident_id: input.incidentId },
        body: { lon: input.lon, lat: input.lat, note: input.note },
        throwOnError: true,
      });
      return res.data;
    },
    onSuccess: async (_out, input) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["incidents"] }),
        queryClient.invalidateQueries({ queryKey: ["mapState"] }),
        queryClient.invalidateQueries({ queryKey: ["events"] }),
        queryClient.invalidateQueries({ queryKey: ["event"] }),
        queryClient.invalidateQueries({ queryKey: ["incident", input.incidentId, "actions"] }),
      ]);
    },
  });
}
