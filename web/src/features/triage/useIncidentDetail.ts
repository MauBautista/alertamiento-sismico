import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { UseQueryResult } from "@tanstack/react-query";

import {
  downloadEvidenceEvidenceEvidenceIdDownloadPost,
  generateReportIncidentsIncidentIdReportPost,
  getEventEventsEventIdGet,
  listDictamensIncidentsIncidentIdDictamensGet,
  listEvidenceIncidentsIncidentIdEvidenceGet,
  listIncidentActionsIncidentsIncidentIdActionsGet,
  signDictamenIncidentsIncidentIdDictamensPost,
} from "@takab/sdk";
import type { DictamenOut, EventDetailOut, EvidenceObject, IncidentActionOut } from "@takab/sdk";

import { openDownload } from "../../lib/download";

class DetailRequestError extends Error {
  constructor(resource: string, status: number) {
    super(`${resource} falló (${status})`);
    this.name = "DetailRequestError";
  }
}

async function fetchDictamens(incidentId: string): Promise<DictamenOut[]> {
  const { data, response } = await listDictamensIncidentsIncidentIdDictamensGet({
    path: { incident_id: incidentId },
  });
  if (data === undefined) {
    throw new DetailRequestError("GET /incidents/{id}/dictamens", response.status);
  }
  return data.items;
}

async function fetchActions(incidentId: string): Promise<IncidentActionOut[]> {
  const { data, response } = await listIncidentActionsIncidentsIncidentIdActionsGet({
    path: { incident_id: incidentId },
  });
  if (data === undefined) {
    throw new DetailRequestError("GET /incidents/{id}/actions", response.status);
  }
  return data;
}

async function fetchEvidence(incidentId: string): Promise<EvidenceObject[]> {
  const { data, response } = await listEvidenceIncidentsIncidentIdEvidenceGet({
    path: { incident_id: incidentId },
  });
  if (data === undefined) {
    throw new DetailRequestError("GET /incidents/{id}/evidence", response.status);
  }
  return data.items;
}

async function fetchEventDetail(eventId: string): Promise<EventDetailOut> {
  const { data, response } = await getEventEventsEventIdGet({ path: { event_id: eventId } });
  if (data === undefined) {
    throw new DetailRequestError("GET /events/{id}", response.status);
  }
  return data;
}

/**
 * Cada recurso lleva SU propio estado. Colapsarlos en un único `loading`/`error`
 * hacía que un panel pintara ausencia ("0 OBJETOS", "SIN EVENTO ASOCIADO") cuando
 * su petición seguía en vuelo o había fallado — exactamente lo que la regla de oro 7
 * prohíbe: un dato ausente presentado como un hecho.
 */
export interface Resource<T> {
  data: T | undefined;
  loading: boolean;
  error: string | null;
  /** true sólo si la consulta ni siquiera se lanzó (no hay nada que pedir). */
  disabled: boolean;
}

export interface IncidentDetailData {
  dictamens: Resource<DictamenOut[]>;
  actions: Resource<IncidentActionOut[]>;
  evidence: Resource<EvidenceObject[]>;
  /** Trae `quorum_votes` con los offsets por nodo. `disabled` si el incidente no
   * referencia un evento del catálogo. */
  event: Resource<EventDetailOut>;
  refetch: () => void;
  sign: (status: string, notes: string | null) => void;
  signing: boolean;
  signError: string | null;
  /** POST /incidents/{id}/report → PDF nuevo; abre la URL presignada. */
  generatePdf: () => void;
  pdfPending: boolean;
  /** POST /evidence/{id}/download → presigned GET de un objeto ya archivado. */
  downloadEvidence: (evidenceId: string) => void;
  downloadPending: boolean;
  /** Última acción de exportación que falló (403/503), para el estado error. */
  exportError: string | null;
}

/**
 * Detalle de un incidente para el Triage: cadena de dictámenes (inmutable),
 * bitácora `incident_actions` (evidencia §9), evidencia S3 y el evento sísmico
 * con sus `quorum_votes`.
 *
 * `audit_log` NO tiene endpoint de lectura: la evidencia de cumplimiento visible
 * es `incident_actions`, que §9 nombra explícitamente como evidencia inmutable.
 */
export function useIncidentDetail(
  incidentId: string | null,
  eventId: string | null,
): IncidentDetailData {
  const qc = useQueryClient();
  const enabled = incidentId !== null;

  const dictamens = useQuery({
    queryKey: ["dictamens", incidentId],
    queryFn: () => fetchDictamens(incidentId as string),
    enabled,
  });
  const actions = useQuery({
    queryKey: ["incident-actions", incidentId],
    queryFn: () => fetchActions(incidentId as string),
    enabled,
  });
  const evidence = useQuery({
    queryKey: ["evidence", incidentId],
    queryFn: () => fetchEvidence(incidentId as string),
    enabled,
  });
  const event = useQuery({
    queryKey: ["event-detail", eventId],
    queryFn: () => fetchEventDetail(eventId as string),
    enabled: enabled && eventId !== null,
  });

  const signMutation = useMutation({
    mutationFn: async (vars: { status: string; notes: string | null }) => {
      const { data, response } = await signDictamenIncidentsIncidentIdDictamensPost({
        path: { incident_id: incidentId as string },
        body: { status: vars.status, notes: vars.notes },
      });
      if (data === undefined) {
        throw new DetailRequestError("POST /incidents/{id}/dictamens", response.status);
      }
      return data;
    },
    onSuccess: () => {
      // Firmar INSERTA una versión nueva: la cadena y la bitácora cambian.
      void qc.invalidateQueries({ queryKey: ["dictamens", incidentId] });
      void qc.invalidateQueries({ queryKey: ["incident-actions", incidentId] });
    },
  });

  const pdfMutation = useMutation({
    mutationFn: async () => {
      const { data, response } = await generateReportIncidentsIncidentIdReportPost({
        path: { incident_id: incidentId as string },
      });
      if (data === undefined) {
        throw new DetailRequestError("POST /incidents/{id}/report", response.status);
      }
      return data;
    },
    onSuccess: (data) => {
      openDownload(data.url);
      // El PDF queda registrado como evidencia inmutable: la lista cambió.
      void qc.invalidateQueries({ queryKey: ["evidence", incidentId] });
    },
  });

  const downloadMutation = useMutation({
    mutationFn: async (evidenceId: string) => {
      const { data, response } = await downloadEvidenceEvidenceEvidenceIdDownloadPost({
        path: { evidence_id: evidenceId },
      });
      if (data === undefined) {
        throw new DetailRequestError("POST /evidence/{id}/download", response.status);
      }
      return data;
    },
    onSuccess: (data) => openDownload(data.url),
  });

  const exportError = pdfMutation.error?.message ?? downloadMutation.error?.message ?? null;

  const wrap = <T>(q: UseQueryResult<T>, isEnabled: boolean): Resource<T> => ({
    data: q.data,
    loading: isEnabled && q.isPending,
    error: q.error ? q.error.message : null,
    disabled: !isEnabled,
  });

  return {
    dictamens: wrap(dictamens, enabled),
    actions: wrap(actions, enabled),
    evidence: wrap(evidence, enabled),
    event: wrap(event, enabled && eventId !== null),
    refetch: () => {
      void dictamens.refetch();
      void actions.refetch();
      void evidence.refetch();
      void event.refetch();
    },
    sign: (status, notes) => signMutation.mutate({ status, notes }),
    signing: signMutation.isPending,
    signError: signMutation.error?.message ?? null,
    generatePdf: () => pdfMutation.mutate(),
    pdfPending: pdfMutation.isPending,
    downloadEvidence: (id) => downloadMutation.mutate(id),
    downloadPending: downloadMutation.isPending,
    exportError,
  };
}
