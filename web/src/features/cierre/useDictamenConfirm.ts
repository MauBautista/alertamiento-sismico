// [T-9.41 · D-43] CONFIRMAR el dictamen AMARILLO vigente.
//
// La confirmación ESPERA al servidor (patrón de `useIncidentAck`): el paso 4 sólo
// pasa a «hecho» cuando la cadena, RELEÍDA, trae la cabeza firmada. Los 409 del
// servidor ya vienen en español («el dictamen vigente ya está firmado», «el
// edificio sigue en movimiento…») y se pintan detrás, tal cual.

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { confirmDictamenIncidentsIncidentIdDictamensDictamenIdConfirmPost } from "@takab/sdk";

import { leer } from "./respuesta";

export function confirmErrorMessage(status: number | null, detail: string | null): string {
  const causa =
    status === null
      ? "SIN RESPUESTA DEL SERVIDOR"
      : status === 409
        ? "LA CADENA CAMBIÓ O EL EDIFICIO NO ESTÁ EN CALMA"
        : status === 403
          ? "TU SESIÓN NO PUEDE CONFIRMAR ESTE DICTAMEN"
          : status === 404
            ? "EL INCIDENTE NO EXISTE O YA NO ESTÁ EN TU ALCANCE"
            : "EL SERVIDOR NO REGISTRÓ LA CONFIRMACIÓN";
  const codigo = status === null ? "" : ` (HTTP ${status})`;
  return `NO SE CONFIRMÓ · ${causa}${codigo}${detail === null ? "" : ` · ${detail}`}`;
}

export function useDictamenConfirm(incidentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (dictamenId: string) => {
      let res;
      try {
        res = await confirmDictamenIncidentsIncidentIdDictamensDictamenIdConfirmPost({
          path: { incident_id: incidentId, dictamen_id: dictamenId },
        });
      } catch {
        throw new Error(confirmErrorMessage(null, null));
      }
      const r = leer(res);
      if (!r.ok) throw new Error(confirmErrorMessage(r.status, r.detail));
      return r.data;
    },
    onSuccess: async () => {
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["dictamens", incidentId] }),
        qc.invalidateQueries({ queryKey: ["incident-actions", incidentId] }),
      ]);
    },
  });
}
