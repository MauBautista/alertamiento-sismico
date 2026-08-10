// Vista PURA de la cola offline (2.5) para la UI de sincronización. Solo
// resume lo que el teléfono PRODUCE (check-ins, reportes, fotos) — jamás
// miniSEED (ese sube edge→S3 y nunca pasa por el teléfono).
//
// [T-2.108] Hasta esta tarea el docstring de arriba y el banner de la pantalla
// decían "check-ins, reportes, evidencia", pero `KIND_LABEL` solo conocía
// `checkin` porque la cola solo admitía check-ins. Ahora las etiquetas son un
// `Record<QueueKind, …>`: un tipo nuevo sin nombre legible no compila.
import {
  blockingRefs,
  indexById,
  type QueueItem,
  type QueueItemState,
  type QueueKind,
} from "@/offline/queue";

export type SyncCounts = Record<QueueItemState, number>;

export function countByState(items: QueueItem[]): SyncCounts {
  const base: SyncCounts = { pending: 0, uploading: 0, synced: 0, failed: 0 };
  for (const i of items) {
    base[i.state] += 1;
  }
  return base;
}

/** Pendiente = todo lo que aún NO aterrizó en el servidor (no synced). */
export function pendingCount(items: QueueItem[]): number {
  return items.filter((i) => i.state !== "synced").length;
}

/** "Tamaño pendiente" (spec §7 · 2.5): bytes de las FOTOS que faltan por
 *  subir. Los payloads de texto son irrelevantes al lado de un JPEG y contarlos
 *  daría una cifra que no se parece a lo que la persona va a gastar de datos. */
export function pendingBytes(items: QueueItem[]): number {
  return items.reduce(
    (n, i) => (i.kind === "evidence" && i.state !== "synced" ? n + i.payload.bytes : n),
    0,
  );
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${Math.round(bytes / 1024)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const KIND_LABEL: Record<QueueKind, string> = {
  checkin: "Check-in de vida",
  evidence: "Foto forense",
  damage_report: "Reporte de daños",
};

const STATE_LABEL: Record<QueueItemState, string> = {
  pending: "PENDIENTE",
  uploading: "ENVIANDO…",
  synced: "SINCRONIZADO",
  failed: "FALLÓ",
};

export type SyncItemView = {
  id: string;
  title: string;
  state: QueueItemState;
  stateLabel: string;
  tone: "ok" | "warn" | "crit" | "muted";
  detail: string;
  retriable: boolean;
  /** Personas atrapadas/heridas: sale ANTES que todo lo demás (§2.4). */
  urgent: boolean;
};

function toneFor(state: QueueItemState): SyncItemView["tone"] {
  if (state === "synced") {
    return "ok";
  }
  if (state === "failed") {
    return "crit";
  }
  if (state === "uploading") {
    return "warn";
  }
  return "muted";
}

function detailFor(item: QueueItem, nowMs: number, blocked: number): string {
  if (item.state === "failed" && item.last_error) {
    return item.last_error;
  }
  if (blocked > 0) {
    // No es un atasco: es lo que conserva el enlace forense. El `evidence_id`
    // lo inventa el servidor y no hay forma de ligar una foto a un reporte ya
    // creado, así que el reporte espera a que sus fotos aterricen.
    return `Espera ${blocked} foto(s) para conservar el enlace forense`;
  }
  if (item.state === "pending" && item.attempts > 0) {
    const secs = Math.max(0, Math.ceil((item.next_attempt_at - nowMs) / 1000));
    return `${item.attempts} intento(s) · reintenta en ${secs} s`;
  }
  if (item.kind === "evidence" && item.state !== "synced") {
    return formatBytes(item.payload.bytes);
  }
  return "";
}

export function syncItemView(item: QueueItem, nowMs: number, all: QueueItem[] = []): SyncItemView {
  const blocked = blockingRefs(item, indexById(all)).length;
  return {
    id: item.id,
    title: KIND_LABEL[item.kind] ?? item.kind,
    state: item.state,
    stateLabel: STATE_LABEL[item.state],
    tone: toneFor(item.state),
    detail: detailFor(item, nowMs, blocked),
    // Un item FALLÓ por un error no recuperable: el reintento manual lo re-encola.
    retriable: item.state === "failed",
    urgent: item.priority > 0,
  };
}

/** Copy del badge de cifrado: SOLO afirma AES-256 si SQLCipher se verificó. */
export function encryptionBadge(status: { active: boolean; cipher: string | null } | null): {
  label: string;
  secure: boolean;
} {
  if (status?.active && status.cipher) {
    return { label: `CIFRADO · ${status.cipher}`, secure: true };
  }
  return { label: "SIN CIFRADO EN ESTE ENTORNO", secure: false };
}
