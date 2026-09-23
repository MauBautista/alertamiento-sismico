// [A-011 · T-8.07] El acuse ESPERA al servidor.
//
// Hasta esta ficha el acuse se lanzaba dentro de un `void (async () => …)()` sin
// mirar la respuesta. El cliente hey-api no lanza con un 4xx/5xx —devuelve
// `{ error, response }`—, así que un 409 «ya no está abierto» (otro operador lo
// acusó antes, o el worker lo pasó a revisión), un 403 o un 500 se descartaban
// en silencio, y el botón pintaba «EJECUTADO» igual. Aquí la petición es una
// mutación de verdad: rechaza con lo que dijo el servidor y la consola lo pinta.

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { ackIncidentIncidentsIncidentIdAckPost } from "@takab/sdk";

/** El `detail` textual de un error de FastAPI, si lo trae. */
function detailOf(error: unknown): string | null {
  if (typeof error !== "object" || error === null) return null;
  const detail = (error as { detail?: unknown }).detail;
  return typeof detail === "string" && detail.trim() !== "" ? detail : null;
}

/**
 * Qué decirle al operador según el código. El 409 es el que más va a ver —dos
 * operadores sobre la misma cola— y no es un fallo del sistema: es que alguien
 * llegó antes. El `detail` del servidor va detrás, tal cual.
 */
export function ackErrorMessage(status: number | null, detail: string | null): string {
  const causa =
    status === null
      ? "SIN RESPUESTA DEL SERVIDOR"
      : status === 409
        ? "EL INCIDENTE YA NO ESTÁ ABIERTO: OTRO OPERADOR LO ACUSÓ O PASÓ A REVISIÓN"
        : status === 404
          ? "EL INCIDENTE NO EXISTE O YA NO ESTÁ EN TU ALCANCE"
          : status === 403
            ? "TU SESIÓN NO PUEDE ACUSAR ESTE INCIDENTE"
            : "EL SERVIDOR NO REGISTRÓ EL ACUSE";
  const codigo = status === null ? "" : ` (HTTP ${status})`;
  return `NO SE ACUSÓ · ${causa}${codigo}${detail === null ? "" : ` · ${detail}`}`;
}

export class AckError extends Error {
  readonly status: number | null;

  constructor(status: number | null, detail: string | null) {
    super(ackErrorMessage(status, detail));
    this.name = "AckError";
    this.status = status;
  }
}

export function useIncidentAck() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (incidentId: string) => {
      let res: Awaited<ReturnType<typeof ackIncidentIncidentsIncidentIdAckPost>>;
      try {
        res = await ackIncidentIncidentsIncidentIdAckPost({ path: { incident_id: incidentId } });
      } catch {
        // Red caída, CORS, un fetch abortado: el acuse NO consta.
        throw new AckError(null, null);
      }
      const status = res.response?.status ?? null;
      // El tipo de la respuesta es una unión (con y sin `error`): se lee sin
      // suponer la rama.
      const error = "error" in res ? res.error : undefined;
      if (error !== undefined || res.data === undefined || status === null || status >= 400) {
        throw new AckError(status, detailOf(error));
      }
      return res.data;
    },
    // Se ESPERA la relectura: así, cuando el botón dice «ACUSADO», la columna
    // ESTADO de la cola ya lo dice también (un refetch fallido no lanza: el
    // acuse sí entró, y la cola lo declarará vieja por su cuenta).
    onSuccess: async (_data, incidentId) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["incidents", "open"] }),
        queryClient.invalidateQueries({ queryKey: ["incident", incidentId, "actions"] }),
      ]);
    },
  });
}
