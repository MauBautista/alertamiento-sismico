// Solicitud de dictamen técnico (T-1.51) sobre POST
// /incidents/{id}/dictamen-request (T-1.48). 409 = ya hay una solicitud
// pendiente — se muestra tal cual, no es un error del sistema.

import { useMutation, useQueryClient } from "@tanstack/react-query";

import {
  requestDictamenIncidentsIncidentIdDictamenRequestPost,
  type IncidentActionOut,
} from "@takab/sdk";

export class DictamenRequestPendingError extends Error {
  constructor() {
    super("ya hay una solicitud de dictamen pendiente para este incidente");
    this.name = "DictamenRequestPendingError";
  }
}

export function useDictamenRequest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (incidentId: string): Promise<IncidentActionOut> => {
      const { data, response } = await requestDictamenIncidentsIncidentIdDictamenRequestPost({
        path: { incident_id: incidentId },
        body: {},
      });
      if (response.status === 409) {
        throw new DictamenRequestPendingError();
      }
      if (data === undefined) {
        throw new Error(`POST dictamen-request falló (${response.status})`);
      }
      return data;
    },
    onSuccess: async (action) => {
      await queryClient.invalidateQueries({
        queryKey: ["incident", action.incident_id, "actions"],
      });
    },
  });
}
