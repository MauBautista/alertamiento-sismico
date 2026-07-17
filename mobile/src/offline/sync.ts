// Motor de sincronización: drena la cola respetando next_attempt_at, UNO a la
// vez (candado) y en orden de captura. El checkin_id que viaja es el id del
// item ⇒ el replay tras una red que murió a medias NO duplica (el servidor
// deduplica — regla de oro 3).
import { submitCheckinIncidentsIncidentIdCheckinsPost } from "@takab/sdk";

import { isDue, markFailed, markRetry, markSynced, markUploading, type QueueItem } from "./queue";
import { useQueueStore } from "./queue.store";

export type SendOutcome = { ok: true } | { ok: false; retryable: boolean; error: string };

/** 401 se reintenta (la sesión puede recuperarse); 4xx de contrato NO. */
export function isRetryableStatus(status: number): boolean {
  if (status === 401 || status === 408 || status === 429) {
    return true;
  }
  return status === 0 || status >= 500;
}

async function sendCheckin(item: QueueItem): Promise<SendOutcome> {
  try {
    const res = await submitCheckinIncidentsIncidentIdCheckinsPost({
      path: { incident_id: item.payload.incident_id },
      body: {
        checkin_id: item.id,
        status: item.payload.status,
        zone_id: item.payload.zone_id,
        location: item.payload.location,
        ts_device: item.payload.ts_device,
      },
    });
    if (res.data) {
      return { ok: true };
    }
    const status = res.response?.status ?? 0;
    return { ok: false, retryable: isRetryableStatus(status), error: `HTTP ${status}` };
  } catch {
    // fetch murió: sin red (modo avión) — recuperable por definición.
    return { ok: false, retryable: true, error: "sin red" };
  }
}

let draining = false;

/** Drena los items vencidos. Reentrante-seguro: una sola pasada a la vez. */
export async function drainQueue(now: number = Date.now(), rng?: () => number): Promise<void> {
  if (draining) {
    return;
  }
  draining = true;
  try {
    const { hydrated, purgeExpired, apply } = useQueueStore.getState();
    if (!hydrated) {
      return;
    }
    await purgeExpired(now);
    const due = useQueueStore.getState().items.filter((i) => isDue(i, now));
    for (const item of due) {
      const uploading = markUploading(item);
      await apply(uploading);
      const outcome = await sendCheckin(uploading);
      if (outcome.ok) {
        await apply(markSynced(uploading, Date.now()));
      } else if (outcome.retryable) {
        await apply(markRetry(uploading, Date.now(), outcome.error, rng));
      } else {
        await apply(markFailed(uploading, outcome.error));
      }
    }
  } finally {
    draining = false;
  }
}
