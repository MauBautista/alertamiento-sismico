// Vista PURA de la cola offline (2.5) para la UI de sincronización. Solo
// resume lo que el teléfono PRODUCE (check-ins, reportes, evidencia) — jamás
// miniSEED (ese sube edge→S3 y nunca pasa por el teléfono).
import type { QueueItem, QueueItemState } from "@/offline/queue";

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

const KIND_LABEL: Record<string, string> = {
  checkin: "Check-in de vida",
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

export function syncItemView(item: QueueItem, nowMs: number): SyncItemView {
  const detail =
    item.state === "failed" && item.last_error
      ? item.last_error
      : item.state === "pending" && item.attempts > 0
        ? `${item.attempts} intento(s) · reintenta en ${Math.max(0, Math.ceil((item.next_attempt_at - nowMs) / 1000))} s`
        : "";
  return {
    id: item.id,
    title: KIND_LABEL[item.kind] ?? item.kind,
    state: item.state,
    stateLabel: STATE_LABEL[item.state],
    tone: toneFor(item.state),
    detail,
    // Un item FALLÓ por un error no recuperable: el reintento manual lo re-encola.
    retriable: item.state === "failed",
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
