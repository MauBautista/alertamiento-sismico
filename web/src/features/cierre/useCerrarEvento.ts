// [T-9.41 · D-43] CERRAR EL EVENTO: `POST /incidents/{id}/close`.
//
// Cada 409 trae por `detail` el CÓDIGO del requisito que falta, en el orden del
// servidor: ya_cerrado → sin_acuse → sismo_en_curso → sin_clasificacion →
// sin_dictamen. Aquí se traduce a español; el código va detrás, entre paréntesis,
// para soporte — nunca solo.

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { closeIncidentIncidentsIncidentIdClosePost } from "@takab/sdk";

import { MOTIVO_MIN_CHARS } from "./pasos";
import { leer } from "./respuesta";
import { INCIDENTE_KEY } from "./useIncidente";
import { INFORME_KEY } from "./useInformeAutomatico";

export const CAUSA_409: Readonly<Record<string, string>> = {
  ya_cerrado: "EL EVENTO YA ESTÁ CERRADO",
  sin_acuse: "FALTA EL ACUSE: ACUSA EL INCIDENTE ANTES DE CERRARLO",
  sismo_en_curso: "EL EDIFICIO SIGUE EN MOVIMIENTO: SE PODRÁ CERRAR CUANDO VUELVA LA CALMA",
  sin_clasificacion: "FALTA LA CLASIFICACIÓN: CLASIFICA EL EVENTO ANTES DE CERRARLO",
  sin_dictamen: `SIN DICTAMEN FIRMADO: FIRMA EL DICTAMEN O ESCRIBE UN MOTIVO DE AL MENOS ${MOTIVO_MIN_CHARS} CARACTERES`,
};

export function cierreErrorMessage(status: number | null, detail: string | null): string {
  if (status === null) return "NO SE CERRÓ · SIN RESPUESTA DEL SERVIDOR";
  if (status === 409 && detail !== null && detail in CAUSA_409) {
    return `NO SE CERRÓ · ${CAUSA_409[detail]} (HTTP 409 · ${detail})`;
  }
  const causa =
    status === 409
      ? "EL SERVIDOR RECHAZÓ EL CIERRE"
      : status === 404
        ? "EL INCIDENTE NO EXISTE O YA NO ESTÁ EN TU ALCANCE"
        : status === 403
          ? "TU SESIÓN NO PUEDE CERRAR ESTE EVENTO"
          : "EL SERVIDOR NO REGISTRÓ EL CIERRE";
  return `NO SE CERRÓ · ${causa} (HTTP ${status})${detail === null ? "" : ` · ${detail}`}`;
}

export function useCerrarEvento(incidentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (motivo: string | null) => {
      let res;
      try {
        res = await closeIncidentIncidentsIncidentIdClosePost({
          path: { incident_id: incidentId },
          body: { motivo: motivo === null || motivo.trim() === "" ? null : motivo.trim() },
        });
      } catch {
        throw new Error(cierreErrorMessage(null, null));
      }
      const r = leer(res);
      if (!r.ok) throw new Error(cierreErrorMessage(r.status, r.detail));
      return r.data;
    },
    // Se ESPERA la relectura: «CERRADO» lo dice la FILA, no esta respuesta.
    onSuccess: async () => {
      await Promise.all([
        qc.invalidateQueries({ queryKey: INCIDENTE_KEY(incidentId) }),
        qc.invalidateQueries({ queryKey: INFORME_KEY(incidentId) }),
        qc.invalidateQueries({ queryKey: ["incidents"] }),
        qc.invalidateQueries({ queryKey: ["incident-actions", incidentId] }),
      ]);
    },
  });
}
