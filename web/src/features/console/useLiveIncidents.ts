// Incidentes abiertos EN VIVO (T-1.27): backfill REST + upsert de frames WS.
//
// TanStack Query es la fuente (poll de respaldo 30 s); los IncidentFrame del
// canal live se aplican encima por incident_id — al siguiente refetch REST y
// frames convergen (mismas filas), así que el merge es idempotente.

import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { listIncidentsIncidentsGet, TOPIC_INCIDENTS, TOPIC_LIVE_HEALTH } from "@takab/sdk";
import type { IncidentFrame, IncidentOut, LiveHealthFrame } from "@takab/sdk";

import type { LiveStatus } from "../../lib/ws";
import { useLiveSocket } from "./socket";

export const INCIDENTS_REFETCH_MS = 30_000;

/** Subconjunto común entre IncidentOut (REST) e IncidentFrame (WS). */
export interface LiveIncident {
  incident_id: string;
  tenant_id: string;
  site_id: string;
  event_id: string | null;
  opened_at: string;
  closed_at: string | null;
  severity: string;
  state: string;
  trigger: string;
  max_pga_g: number | null;
  max_pgv_cms: number | null;
}

const SEVERITY_RANK: Record<string, number> = { critical: 3, warning: 2, watch: 1, info: 0 };

export function fromOut(row: IncidentOut): LiveIncident {
  return {
    incident_id: row.incident_id,
    tenant_id: row.tenant_id,
    site_id: row.site_id,
    event_id: row.event_id,
    opened_at: row.opened_at,
    closed_at: row.closed_at,
    severity: row.severity,
    state: row.state,
    trigger: row.trigger,
    max_pga_g: row.max_pga_g,
    max_pgv_cms: row.max_pgv_cms,
  };
}

export function fromFrame(frame: IncidentFrame): LiveIncident {
  return {
    incident_id: frame.incident_id,
    tenant_id: frame.tenant_id,
    site_id: frame.site_id,
    event_id: frame.event_id ?? null,
    opened_at: frame.opened_at,
    closed_at: frame.closed_at ?? null,
    severity: frame.severity,
    state: frame.state,
    trigger: frame.trigger,
    max_pga_g: frame.max_pga_g ?? null,
    max_pgv_cms: frame.max_pgv_cms ?? null,
  };
}

/** Abierto = sin closed_at y no cerrado (el frame de cierre lo saca de la mesa). */
export function isOpen(incident: LiveIncident): boolean {
  return incident.closed_at === null && incident.state !== "closed";
}

/** Upserts de frames sobre la página REST + orden severidad desc, luego más nuevo. */
export function mergeIncidents(
  base: LiveIncident[],
  frames: ReadonlyMap<string, LiveIncident>,
): LiveIncident[] {
  const byId = new Map(base.map((i) => [i.incident_id, i]));
  for (const [id, frame] of frames) {
    byId.set(id, frame);
  }
  return [...byId.values()].filter(isOpen).sort((a, b) => {
    const rank = (SEVERITY_RANK[b.severity] ?? -1) - (SEVERITY_RANK[a.severity] ?? -1);
    return rank !== 0 ? rank : b.opened_at.localeCompare(a.opened_at);
  });
}

async function fetchOpenIncidents(): Promise<LiveIncident[]> {
  const { data, response } = await listIncidentsIncidentsGet({ query: { state: "open" } });
  if (data === undefined) {
    throw new Error(`GET /incidents falló (${response.status})`);
  }
  return data.items.map(fromOut);
}

/**
 * [T-2.129] Un topic del canal live que el servidor declara DEGRADADO: se le
 * escapó algo que debía entregar, pero el canal sigue abierto.
 *
 * No es «sin conexión», y confundirlos cuesta la decisión equivocada: sin
 * conexión el operador sabe que no le llega nada; degradado el canal SÍ entrega,
 * así que la cola puede estar incompleta pareciendo completa — que es la forma
 * exacta de la regla de oro 7 que esta ficha cierra.
 */
export interface LiveDegradation {
  /** Topic del protocolo (`incidents`, `site_state`, `features:<site_id>`). */
  topic: string;
  /** Rótulo para el operador; se calcula aquí para que la tabla no dependa del SDK. */
  label: string;
  /** Nombre técnico de lo que falló (`LockTimeout`…) — para soporte, no para el rótulo. */
  detail: string | null;
}

/**
 * Topic → lo que significa para quien opera. La familia `features:<site_id>` se
 * rotula por lo que es (el sismograma del sitio) en vez de escupir un UUID en
 * pantalla. El fallback imprime el topic crudo: un topic nuevo sin rótulo se ve
 * feo, que es infinitamente mejor que no verse.
 *
 * `site_state` y `features:` van como literales y NO derivados del SDK, y está
 * MEDIDO: derivar el prefijo con `featuresTopic("")` en el cuerpo del módulo
 * tumbó `useFleet.test.tsx` y `useSiteRelays.test.tsx` a CERO tests —fallo de
 * suite, no de aserción— porque sus `vi.mock("@takab/sdk")` sustituyen el SDK
 * entero sin `importOriginal` y `featuresTopic` llegaba `undefined`. Tres
 * cadenas del protocolo comparadas aquí valen menos que dos suites mudas.
 */
export function degradationLabel(topic: string): string {
  if (topic === TOPIC_INCIDENTS) return "INCIDENTES";
  if (topic === "site_state") return "SALUD DE GABINETES";
  if (topic.startsWith("features:")) return "SISMOGRAMA";
  return topic.toUpperCase();
}

export interface LiveIncidentsData {
  incidents: LiveIncident[];
  loading: boolean;
  error: string | null;
  dataUpdatedAt: number;
  liveStatus: LiveStatus;
  /** Epoch ms del último frame del topic incidents, o null (para staleness). */
  lastFrameAt: number | null;
  /** [T-2.129] Topics que el servidor declara degradados, ordenados por topic. */
  degraded: LiveDegradation[];
  refetch: () => void;
}

export function useLiveIncidents(): LiveIncidentsData {
  const socket = useLiveSocket();
  const query = useQuery({
    queryKey: ["incidents", "open"],
    queryFn: fetchOpenIncidents,
    refetchInterval: INCIDENTS_REFETCH_MS,
  });
  const [frames, setFrames] = useState<ReadonlyMap<string, LiveIncident>>(new Map());
  const [liveStatus, setLiveStatus] = useState<LiveStatus>(socket?.status ?? "closed");
  const [degradedBy, setDegradedBy] = useState<ReadonlyMap<string, string | null>>(new Map());

  useEffect(() => {
    if (!socket) return undefined;
    setLiveStatus(socket.status);
    const offStatus = socket.onStatus((status) => {
      setLiveStatus(status);
      // [T-2.129] Al perder el socket se OLVIDA lo declarado: al reconectar, el
      // hub registra un suscriptor nuevo y limpio, así que su `degraded: false`
      // nunca llegaría y el aviso se quedaría encendido para siempre.
      if (status !== "ready") setDegradedBy(new Map());
    });
    const offFrames = socket.subscribe(TOPIC_INCIDENTS, (frame) => {
      if (frame.type !== "incident") return; // incident_action vive en otro hook
      const live = fromFrame(frame as IncidentFrame);
      setFrames((prev) => new Map(prev).set(live.incident_id, live));
    });
    // [T-2.129] El canal ya sabe declarar su propia salud sin cerrarse. Este
    // topic es LOCAL: no viaja ningún `subscribe` al servidor (ver `ws.ts`).
    const offHealth = socket.subscribe(TOPIC_LIVE_HEALTH, (frame) => {
      const health = frame as LiveHealthFrame;
      setDegradedBy((prev) => {
        const next = new Map(prev);
        if (health.degraded) next.set(health.topic, health.detail ?? null);
        else next.delete(health.topic);
        return next;
      });
    });
    return () => {
      offStatus();
      offFrames();
      offHealth();
    };
  }, [socket]);

  // El refetch REST ya refleja los frames aplicados: poda el buffer local.
  useEffect(() => {
    if (query.dataUpdatedAt > 0) setFrames(new Map());
  }, [query.dataUpdatedAt]);

  const incidents = useMemo(() => mergeIncidents(query.data ?? [], frames), [query.data, frames]);
  const degraded = useMemo(
    () =>
      [...degradedBy.entries()]
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([topic, detail]) => ({ topic, label: degradationLabel(topic), detail })),
    [degradedBy],
  );

  return {
    incidents,
    loading: query.isPending,
    error: query.data === undefined && query.error ? query.error.message : null,
    dataUpdatedAt: query.dataUpdatedAt,
    liveStatus,
    lastFrameAt: socket?.lastFrameAt(TOPIC_INCIDENTS) ?? null,
    degraded,
    refetch: () => {
      void query.refetch();
    },
  };
}
