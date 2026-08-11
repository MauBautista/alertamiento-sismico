// Motor de sincronización: drena la cola respetando next_attempt_at, UNO a la
// vez (candado) y en el orden que manda `dueForDispatch` — prioridad máxima
// primero (§2.4), FIFO dentro del nivel. El checkin_id que viaja es el id del
// item ⇒ el replay tras una red que murió a medias NO duplica (el servidor
// deduplica — regla de oro 3).
//
// [T-2.108] Un EMISOR POR TIPO, en un `Record<QueueKind, …>`: añadir un tipo
// nuevo (headcount) sin darle emisor no compila. Antes solo existía el
// check-in y por eso la foto forense y el reporte de daños hacían POST directo
// desde la pantalla — y sin red se perdían.
import {
  submitCheckinIncidentsIncidentIdCheckinsPost,
  submitDamageReportIncidentsIncidentIdDamageReportsPost,
} from "@takab/sdk";

import { buildDamageReportBody } from "@/features/damage/payload";
import { registerAndUploadEvidence } from "@/services/evidence";

import { isRetryableStatus, type SendOutcome } from "./httpOutcome";
import {
  dueForDispatch,
  indexById,
  markFailed,
  markRetry,
  markSynced,
  markUploading,
  resolveEvidenceIds,
  type QueueItem,
  type QueueItemOf,
  type QueueKind,
} from "./queue";
import { useQueueStore } from "./queue.store";

export { isRetryableStatus, type SendOutcome };

type ById = Map<string, QueueItem>;

async function sendCheckin(item: QueueItemOf<"checkin">): Promise<SendOutcome> {
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

/** La foto: se comprueba su huella, se registra y sube por el PUT presignado.
 *  El `evidence_id` que devuelve el servidor se guarda en `server_id` — es lo
 *  que después liga el reporte de daños con esta foto.
 *
 *  [T-2.113] El id que viaja es el del ITEM, igual que el `checkin_id`: no
 *  cambia entre intentos, así que el reintento tras un PUT a S3 que murió
 *  resuelve a la MISMA fila y al MISMO objeto (regla de oro 3). Antes el
 *  servidor inventaba un id por intento y el segundo chocaba contra el índice
 *  único (incidente, huella): 4xx ⇒ `failed`, y la fila se quedaba sin blob. */
async function sendEvidence(item: QueueItemOf<"evidence">): Promise<SendOutcome> {
  const out = await registerAndUploadEvidence({
    incidentId: item.payload.incident_id,
    evidenceId: item.id,
    uri: item.payload.uri,
    sha256: item.sha256,
    contentType: item.payload.content_type,
  });
  return out.ok
    ? { ok: true, serverId: out.evidenceId }
    : { ok: false, retryable: out.retryable, error: out.reason };
}

async function sendDamageReport(
  item: QueueItemOf<"damage_report">,
  byId: ById,
): Promise<SendOutcome> {
  // Las refs locales se traducen aquí, no al capturar: en avión el
  // `evidence_id` del servidor todavía no existía.
  const { ids } = resolveEvidenceIds(item.payload.evidence_refs, byId);
  try {
    const res = await submitDamageReportIncidentsIncidentIdDamageReportsPost({
      path: { incident_id: item.payload.incident_id },
      body: buildDamageReportBody({
        categories: item.payload.categories,
        notes: item.payload.notes ?? "",
        zoneId: item.payload.zone_id,
        evidenceIds: ids,
        tsDevice: item.payload.ts_device,
      }),
    });
    if (res.data) {
      return { ok: true };
    }
    const status = res.response?.status ?? 0;
    return { ok: false, retryable: isRetryableStatus(status), error: `HTTP ${status}` };
  } catch {
    return { ok: false, retryable: true, error: "sin red" };
  }
}

/** El censo de emisores. Es un `Record` sobre `QueueKind` A PROPÓSITO: un tipo
 *  nuevo en la cola sin emisor aquí rompe la compilación. */
const SENDERS: { [K in QueueKind]: (item: QueueItemOf<K>, byId: ById) => Promise<SendOutcome> } = {
  checkin: sendCheckin,
  evidence: sendEvidence,
  damage_report: sendDamageReport,
};

function send(item: QueueItem, byId: ById): Promise<SendOutcome> {
  const sender = SENDERS[item.kind] as (i: QueueItem, b: ById) => Promise<SendOutcome>;
  if (sender === undefined) {
    // Fila escrita por una versión más nueva de la app (downgrade): no se
    // inventa un envío ni se borra el dato — queda visible y fallido.
    return Promise.resolve({
      ok: false,
      retryable: false,
      error: `tipo desconocido en esta versión: ${String(item.kind)}`,
    });
  }
  // Único punto de estrechamiento: `kind` y `payload` viajan juntos por
  // construcción de `QueueItemOf`, así que el emisor recibe lo que espera.
  return sender(item, byId);
}

let draining = false;

/** Cota dura del drenaje. Cada item despachado SALE del conjunto elegible
 *  (queda synced, failed, o pending con `next_attempt_at` futuro), así que el
 *  bucle termina solo; esto únicamente impide que un fallo lógico lo vuelva
 *  infinito con la batería de alguien de por medio. */
const MAX_DISPATCHES = 500;

/** Drena los items vencidos. Reentrante-seguro: una sola pasada a la vez.
 *
 *  Se REELIGE el siguiente item tras cada envío, no se toma una lista fija:
 *  la foto que acaba de aterrizar DESBLOQUEA al reporte que la esperaba, y si
 *  ese reporte dice "personas atrapadas" tiene que salir en ese instante —no
 *  detrás del resto de la cola ni en el siguiente tic de 15 s (§2.4). */
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
    for (let n = 0; n < MAX_DISPATCHES; n += 1) {
      const items = useQueueStore.getState().items;
      const next = dueForDispatch(items, now)[0];
      if (next === undefined) {
        return;
      }
      // El índice se lee AQUÍ: la foto recién sincronizada ya trae su
      // `server_id`, y el reporte se liga con él.
      const byId = indexById(items);
      const uploading = markUploading(next);
      await apply(uploading);
      const outcome = await send(uploading, byId);
      if (outcome.ok) {
        await apply(markSynced(uploading, Date.now(), outcome.serverId));
      } else if (outcome.retryable) {
        // `Math.max` sostiene el invariante que hace terminar este bucle: el
        // próximo intento SIEMPRE queda por delante del `now` con el que se
        // eligió el item. Con `Date.now()` a secas, un `now` adelantado —un
        // test que simula "un minuto después", un salto de reloj— dejaba el
        // item elegible otra vez y lo reintentaba en bucle contra el servidor.
        await apply(markRetry(uploading, Math.max(now, Date.now()), outcome.error, rng));
      } else {
        await apply(markFailed(uploading, outcome.error));
      }
    }
  } finally {
    draining = false;
  }
}
