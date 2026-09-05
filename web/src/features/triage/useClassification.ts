// [T-5.12] Clasificación de incidentes y tasa de falsos positivos.
//
// Dos consultas distintas y a propósito: la CADENA de un incidente (que se lee
// al abrirlo) y la TASA del cliente (que se lee al entrar al triage). Meterlas
// en un hook común obligaría a refrescar la tasa entera cada vez que alguien
// clasifica un incidente, y la tasa es una consulta de noventa días.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  classificationStatsClassificationStatsGet,
  classifyIncidentIncidentsIncidentIdClassificationPost,
  getClassificationsIncidentsIncidentIdClassificationsGet,
} from "@takab/sdk";
import type { ClassificationChainOut, ClassificationStatsOut } from "@takab/sdk";

export const CLASSIFICATION_KEY = (id: string) => ["classification", id] as const;
export const CLASSIFICATION_STATS_KEY = ["classification", "stats"] as const;

/** El catálogo cerrado, con la etiqueta que ve quien elige a las 3 de la mañana. */
export const CLASIFICACIONES = [
  { value: "real", label: "REAL", hint: "Hubo un evento: el sistema hizo lo que tenía que hacer" },
  {
    value: "falso_positivo",
    label: "FALSO POSITIVO",
    hint: "No hubo evento. Es la casilla que decide si el cliente renueva",
  },
  {
    value: "prueba",
    label: "PRUEBA",
    hint: "Prueba o mantenimiento. No cuenta como falso positivo",
  },
  {
    value: "indeterminado",
    label: "INDETERMINADO",
    hint: "Se revisó y no se pudo determinar. Distinto de no haberlo revisado",
  },
] as const;

export function useClassification(incidentId: string) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: CLASSIFICATION_KEY(incidentId),
    queryFn: async () => {
      const r = await getClassificationsIncidentsIncidentIdClassificationsGet({
        path: { incident_id: incidentId },
      });
      if (r.error !== undefined) throw new Error("classifications");
      return r.data as ClassificationChainOut;
    },
  });

  const clasificar = useMutation({
    mutationFn: async (input: { classification: string; note?: string; supersedesId?: string }) => {
      const r = await classifyIncidentIncidentsIncidentIdClassificationPost({
        path: { incident_id: incidentId },
        body: {
          classification: input.classification,
          note: input.note ?? "",
          supersedes_id: input.supersedesId ?? null,
        },
      });
      if (r.error !== undefined) throw new Error("classify");
      return r.data;
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: CLASSIFICATION_KEY(incidentId) });
      void qc.invalidateQueries({ queryKey: CLASSIFICATION_STATS_KEY });
    },
  });

  const items = q.data?.items ?? [];
  return {
    items,
    /** La vigente: la que nadie sustituye. La derivó el servidor. */
    current: items.find((i) => i.current) ?? null,
    loading: q.isLoading,
    readError: q.isError,
    updatedAt: q.dataUpdatedAt,
    refetch: () => void q.refetch(),
    clasificar: clasificar.mutate,
    pending: clasificar.isPending,
  };
}

export function useClassificationStats() {
  const q = useQuery({
    queryKey: CLASSIFICATION_STATS_KEY,
    queryFn: async () => {
      const r = await classificationStatsClassificationStatsGet();
      if (r.error !== undefined) throw new Error("classification-stats");
      return r.data as ClassificationStatsOut;
    },
  });
  return {
    stats: q.data ?? null,
    loading: q.isLoading,
    readError: q.isError,
    updatedAt: q.dataUpdatedAt,
    refetch: () => void q.refetch(),
  };
}
