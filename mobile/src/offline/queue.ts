// Cola offline (spec §4.2) — LÓGICA PURA, sin I/O: transiciones de estado,
// vencimiento de reintentos y retención. El almacenamiento vive en store.ts y
// el motor de envío en sync.ts.
//
// Estados: pending → uploading → synced (terminal feliz)
//                    └→ pending (error RECUPERABLE, con backoff)
//                    └→ failed  (error NO recuperable: visible, jamás se oculta)
import { retryDelayMs } from "./backoff";

export type QueueItemState = "pending" | "uploading" | "synced" | "failed";

export type CheckinPayload = {
  incident_id: string;
  status: "safe" | "need_help";
  zone_id: string | null;
  /** [lon, lat] SOLO con consentimiento GPS y solo en need_help (LFPDPPP). */
  location: [number, number] | null;
  /** Sellado al TOQUE del botón (el servidor sella created_at aparte). */
  ts_device: string;
};

export type QueueItem = {
  /** UUID generado en el dispositivo = checkin_id en el servidor (idempotencia). */
  id: string;
  kind: "checkin";
  payload: CheckinPayload;
  /** SHA-256 del payload canónico, sellado al capturar (cadena de custodia). */
  sha256: string;
  state: QueueItemState;
  attempts: number;
  /** epoch ms; 0 = elegible ya. */
  next_attempt_at: number;
  created_at: number;
  synced_at: number | null;
  last_error: string | null;
};

/** Nada se borra hasta synced + 24 h (criterio T-2.06). */
export const RETENTION_AFTER_SYNC_MS = 24 * 60 * 60 * 1000;

export function newQueueItem(
  id: string,
  payload: CheckinPayload,
  sha256: string,
  now: number,
): QueueItem {
  return {
    id,
    kind: "checkin",
    payload,
    sha256,
    state: "pending",
    attempts: 0,
    next_attempt_at: 0,
    created_at: now,
    synced_at: null,
    last_error: null,
  };
}

export function markUploading(item: QueueItem): QueueItem {
  return { ...item, state: "uploading" };
}

export function markSynced(item: QueueItem, now: number): QueueItem {
  return { ...item, state: "synced", synced_at: now, last_error: null };
}

/** Error RECUPERABLE (red caída, 5xx): vuelve a pending con backoff+jitter. */
export function markRetry(
  item: QueueItem,
  now: number,
  error: string,
  rng?: () => number,
): QueueItem {
  const attempts = item.attempts + 1;
  return {
    ...item,
    state: "pending",
    attempts,
    next_attempt_at: now + retryDelayMs(attempts, rng),
    last_error: error,
  };
}

/** Error NO recuperable (4xx de contrato): queda visible como failed. */
export function markFailed(item: QueueItem, error: string): QueueItem {
  return { ...item, state: "failed", last_error: error };
}

export function isDue(item: QueueItem, now: number): boolean {
  return item.state === "pending" && item.next_attempt_at <= now;
}

/** Un item que quedó "uploading" (la app murió a media subida) vuelve a
 *  pending al hidratar: no sabemos si aterrizó, y reintentar es SEGURO
 *  porque el servidor deduplica por checkin_id (regla de oro 3). */
export function recoverInterrupted(item: QueueItem): QueueItem {
  if (item.state !== "uploading") {
    return item;
  }
  return { ...item, state: "pending", next_attempt_at: 0 };
}

/** SOLO lo sincronizado hace 24 h+ se poda; pending/uploading/failed JAMÁS. */
export function shouldPurge(item: QueueItem, now: number): boolean {
  return (
    item.state === "synced" &&
    item.synced_at !== null &&
    item.synced_at + RETENTION_AFTER_SYNC_MS < now
  );
}

/** ¿Este dispositivo ya registró check-in del incidente? (pending/uploading/
 *  synced cuentan — el dato existe y viajará; failed NO: ese check-in no
 *  aterrizó y el usuario debe poder reintentarlo.) */
export function hasLocalCheckin(items: QueueItem[], incidentId: string): boolean {
  return items.some(
    (i) => i.kind === "checkin" && i.payload.incident_id === incidentId && i.state !== "failed",
  );
}
