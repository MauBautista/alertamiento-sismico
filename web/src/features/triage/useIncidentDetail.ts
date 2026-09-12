import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { UseQueryResult } from "@tanstack/react-query";
import { useEffect } from "react";

import {
  downloadEvidenceEvidenceEvidenceIdDownloadPost,
  generateReportIncidentsIncidentIdReportPost,
  getEventEventsEventIdGet,
  listDictamensIncidentsIncidentIdDictamensGet,
  listEvidenceIncidentsIncidentIdEvidenceGet,
  listIncidentActionsIncidentsIncidentIdActionsGet,
  signDictamenIncidentsIncidentIdDictamensPost,
  TOPIC_INCIDENTS,
} from "@takab/sdk";
import type {
  DictamenOut,
  EventDetailOut,
  EvidenceObject,
  IncidentActionFrame,
  IncidentActionOut,
} from "@takab/sdk";

import { openPendingDownload, type PendingDownload } from "../../lib/download";
import { useNow } from "../../lib/useNow";
import { useLiveSocket } from "../../live/socket";
import {
  dictamenRefetchMs,
  type DictamenChainRow,
  type IncidentRefreshHint,
} from "./dictamenRefresh";
import { staleSinceOf } from "./staleness";

class DetailRequestError extends Error {
  constructor(resource: string, status: number) {
    super(`${resource} falló (${status})`);
    this.name = "DetailRequestError";
  }
}

/** [T-6.16] El motivo que se escribe EN la pestaña reservada. Un objeto sin
 *  mensaje no se le enseña a nadie: se traduce a una frase. */
function _motivo(err: unknown): string {
  return err instanceof Error && err.message ? err.message : "el servidor no devolvió el documento";
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
  /**
   * [T-2.82.a] Epoch ms de la última respuesta buena CUANDO ya se considera
   * vieja; null = fresca.
   *
   * Va en el recurso y no en cada panel a propósito. Cuatro marcos de la
   * pantalla donde se FIRMA un dictamen —evidencia, dictamen, bitácora y
   * quórum— clavaban `staleSince={null}` porque su recurso no llevaba la marca
   * de tiempo de la consulta; fabricársela en el marcado habría sido inventar
   * cuatro relojes distintos para cuatro consultas que ya tienen el suyo dentro
   * de react-query. Es el veredicto ya resuelto, no la materia prima: un panel
   * que reciba `dataUpdatedAt` a secas puede volver a decidir por su cuenta, y
   * quién gana entre `empty` y `stale` lo decide `STATE_PRECEDENCE` para toda
   * la consola (T-2.79.d).
   */
  staleSince: number | null;
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
  /**
   * [T-7.05 · C-3] La FILA del incidente: `opened_at` es el ancla de la ventana
   * en la que la pasada automática todavía puede escribir (`dictamenRefresh.ts`).
   *
   * OBLIGATORIO, y ése es todo el punto. Con un `= null` por defecto, el
   * llamador que no supiera de esto se llevaba la rama sin ventana —sondeo cada
   * 5 s sobre dos endpoints, sin condición de parada— sin que nada se pusiera
   * rojo (revisión adversaria f0r2 · nº3). Ahora el que no tenga la fila tiene
   * que escribir `null` y con eso está diciendo, a sabiendas, «sin suelo de
   * refresco: me fío del canal live».
   */
  incident: IncidentRefreshHint | null,
): IncidentDetailData {
  const qc = useQueryClient();
  const socket = useLiveSocket();
  const enabled = incidentId !== null;

  // Un único "ahora" para toda la pantalla: fecha la edad de los cuatro
  // recursos (`staleSinceOf`) y acota la ventana del sondeo del dictamen.
  const now = useNow(30_000);

  /**
   * [T-7.05 · C-3] EL SUELO DEL REFRESCO MIENTRAS LA PASADA AUTOMÁTICA ESCRIBE.
   *
   * Se evalúa en forma de función a propósito: react-query la vuelve a llamar
   * con el estado ACTUAL de la consulta cada vez que reinstala el temporizador,
   * así que en cuanto la cadena queda firmada el propio intervalo se apaga —sin
   * un render de más ni una condición duplicada fuera del hook.
   *
   * El corte por ventana usa el `now` de `useNow(30_000)`, o sea que puede
   * llegar hasta 30 s tarde. Cabe de sobra: `DICTAMEN_WATCH_MS` ya lleva el
   * doble del lookback del worker como holgura.
   */
  const cadencia = (cadena: readonly DictamenChainRow[] | undefined) =>
    dictamenRefetchMs({ incidentId, incident, dictamens: cadena, now });

  const dictamens = useQuery({
    queryKey: ["dictamens", incidentId],
    queryFn: () => fetchDictamens(incidentId as string),
    enabled,
    refetchInterval: (query) => cadencia(query.state.data),
  });
  const actions = useQuery({
    queryKey: ["incident-actions", incidentId],
    queryFn: () => fetchActions(incidentId as string),
    enabled,
    // La bitácora acompaña a la cadena en la MISMA ventana: la pasada de
    // dictamen escribe las dos cosas (el INSERT en `dictamens` y su
    // `incident_actions` de kind `dictamen`), y refrescar una sin la otra deja
    // la pantalla diciendo dos cosas distintas del mismo hecho.
    refetchInterval: () => cadencia(dictamens.data),
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

  /**
   * [T-7.05 · C-3] EL CAMINO BUENO: el canal live, que llega en <1 s.
   *
   * La pasada de dictamen no sólo INSERTA en `dictamens`: deja su huella en
   * `incident_actions` con kind `dictamen` (api · `dictamen/service.py`). El
   * trigger `trg_incident_actions_notify` (migración 0004) lanza el NOTIFY y el
   * hub lo reparte como `incident_action` por el topic `incidents`, ya filtrado
   * por RLS. O sea: el servidor YA estaba avisando y esta pantalla era la única
   * que no escuchaba — `useMapState`, `liveHealth.store` y `useActiveDrill` sí.
   *
   * Se invalida, no se fusiona: al revés que `useIncidentActions` del wall, aquí
   * el frame no basta para pintar (la CADENA de dictámenes no viaja en él), así
   * que lo que hace es preguntar. Y la cadena sólo se re-consulta cuando la
   * acción ES un dictamen; la bitácora, con cualquiera de este incidente.
   */
  useEffect(() => {
    if (!socket || incidentId === null) {
      return undefined;
    }
    return socket.subscribe(TOPIC_INCIDENTS, (frame) => {
      if (frame.type !== "incident_action") {
        return;
      }
      const action = frame as IncidentActionFrame;
      if (action.incident_id !== incidentId) {
        return;
      }
      void qc.invalidateQueries({ queryKey: ["incident-actions", incidentId] });
      if (action.kind === "dictamen") {
        void qc.invalidateQueries({ queryKey: ["dictamens", incidentId] });
      }
    });
  }, [socket, incidentId, qc]);

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

  // La pestaña se RESERVA en el gesto del usuario (ver lib/download.ts) y viaja
  // como variable de la mutación: la URL presignada no existe hasta que el
  // servidor responde, y abrirla entonces llega tarde al popup blocker.
  const pdfMutation = useMutation({
    mutationFn: async (pending: PendingDownload) => {
      try {
        const { data, response } = await generateReportIncidentsIncidentIdReportPost({
          path: { incident_id: incidentId as string },
        });
        if (data === undefined) {
          throw new DetailRequestError("POST /incidents/{id}/report", response.status);
        }
        return data;
      } catch (err) {
        // Cualquier fallo (503 sin bucket, red caída): la pestaña reservada lo
        // DICE. Cerrarla dejaba al operador sin pestaña y sin explicación.
        pending.fail(_motivo(err));
        throw err;
      }
    },
    onSuccess: (data, pending) => {
      pending.resolve(data.url);
      // El PDF queda registrado como evidencia inmutable: la lista cambió.
      void qc.invalidateQueries({ queryKey: ["evidence", incidentId] });
    },
  });

  const downloadMutation = useMutation({
    mutationFn: async (vars: { evidenceId: string; pending: PendingDownload }) => {
      try {
        const { data, response } = await downloadEvidenceEvidenceEvidenceIdDownloadPost({
          path: { evidence_id: vars.evidenceId },
        });
        if (data === undefined) {
          throw new DetailRequestError("POST /evidence/{id}/download", response.status);
        }
        return data;
      } catch (err) {
        vars.pending.fail(_motivo(err));
        throw err;
      }
    },
    onSuccess: (data, vars) => vars.pending.resolve(data.url),
  });

  const exportError = pdfMutation.error?.message ?? downloadMutation.error?.message ?? null;

  const wrap = <T>(q: UseQueryResult<T>, isEnabled: boolean): Resource<T> => ({
    data: q.data,
    loading: isEnabled && q.isPending,
    error: q.error ? q.error.message : null,
    disabled: !isEnabled,
    staleSince: staleSinceOf(q.dataUpdatedAt, now),
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
    // `openPendingDownload()` corre AQUÍ, sincrónicamente dentro del onClick:
    // es lo único que el navegador acepta como "el usuario pidió esta ventana".
    generatePdf: () => pdfMutation.mutate(openPendingDownload()),
    pdfPending: pdfMutation.isPending,
    downloadEvidence: (id) =>
      downloadMutation.mutate({ evidenceId: id, pending: openPendingDownload() }),
    downloadPending: downloadMutation.isPending,
    exportError,
  };
}
