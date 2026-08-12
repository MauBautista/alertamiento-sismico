// Datos del Triage Estructural (T-2.10): reportes de daños del incidente +
// verificación de hash de evidencias bajo demanda. Cada verify re-hashea el
// objeto subido server-side y devuelve verified/tampered (regla de oro 7: el
// estado de integridad se muestra tal cual, jamás se asume).
import { useMutation, useQuery } from "@tanstack/react-query";

import {
  listDamageReportsIncidentsIncidentIdDamageReportsGet,
  verifyEvidenceEvidenceEvidenceIdVerifyPost,
} from "@takab/sdk";
import type { DamageReportOut, EvidenceVerifyOut } from "@takab/sdk";

import { useNow } from "../../lib/useNow";
import { staleSinceOf } from "./staleness";

async function fetchDamageReports(incidentId: string): Promise<DamageReportOut[]> {
  const { data, response } = await listDamageReportsIncidentsIncidentIdDamageReportsGet({
    path: { incident_id: incidentId },
  });
  if (data === undefined) {
    throw new Error(`GET /incidents/{id}/damage-reports falló (${response.status})`);
  }
  return data;
}

export function useDamageReports(incidentId: string) {
  const query = useQuery({
    queryKey: ["damage-reports", incidentId],
    queryFn: () => fetchDamageReports(incidentId),
  });
  const now = useNow(30_000);
  return {
    reports: query.data,
    loading: query.isLoading,
    error: query.isError ? "No se pudieron cargar los reportes de daños." : null,
    /**
     * [T-2.82.a] Epoch ms de la última respuesta buena cuando ya es vieja.
     *
     * El panel que consume esto era el ÚNICO de la pantalla de firma que ni
     * siquiera declaraba la entrada, y callarse que un dato puede envejecer es
     * afirmar que no puede. Son los reportes que los tácticos levantan dentro
     * del edificio durante la emergencia: los únicos de la pantalla que siguen
     * llegando mientras el inspector lee, y por tanto los que peor mienten
     * congelados — «sin reportes de daños» puede significar que nadie ha podido
     * mandarlos.
     */
    staleSince: staleSinceOf(query.dataUpdatedAt, now),
  };
}

export function useVerifyEvidence() {
  return useMutation<EvidenceVerifyOut, Error, string>({
    mutationFn: async (evidenceId: string) => {
      const { data, response } = await verifyEvidenceEvidenceEvidenceIdVerifyPost({
        path: { evidence_id: evidenceId },
      });
      if (data === undefined) {
        throw new Error(`POST /evidence/{id}/verify falló (${response.status})`);
      }
      return data;
    },
  });
}
