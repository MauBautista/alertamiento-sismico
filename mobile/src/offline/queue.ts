// Cola offline (spec §4.2) — LÓGICA PURA, sin I/O: tipos, transiciones de
// estado, orden de despacho, vencimiento de reintentos y retención. El
// almacenamiento vive en store.ts y el motor de envío en sync.ts.
//
// Estados: pending → uploading → synced (terminal feliz)
//                    └→ pending (error RECUPERABLE, con backoff)
//                    └→ failed  (error NO recuperable: visible, jamás se oculta)
//
// [T-2.108] La cola es MULTI-TIPO: la spec §4.2 la define «compartida por
// check-ins, reportes, fotos» y §7·2.5 exige que contenga «fotos, reportes,
// check-ins (incl. delegados), headcount». Hasta T-2.108 solo admitía
// `checkin`, así que la cámara forense y el formulario de daños hacían POST
// directo y SIN RED SE PERDÍAN. El tipo se extiende por `QueuePayloadByKind`:
// añadir `headcount` = una clave aquí + su etiqueta en syncView + su emisor en
// sync.ts, y el compilador exige las tres (son `Record<QueueKind, …>`).
import { orderByPriority } from "@/features/damage/categories";

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

/** Foto forense (2.3). El BINARIO no viaja en el payload: la cola guarda el
 *  puntero al archivo privado —jamás la galería (§7 L552)— y su huella. */
export type EvidencePayload = {
  incident_id: string;
  /** Archivo privado con la marca YA horneada. La cola no lo reescribe nunca. */
  uri: string;
  content_type: string;
  /** Tamaño medido al capturar: alimenta el "tamaño pendiente" de 2.5. */
  bytes: number;
  ts_device: string;
};

export type DamageCategoryPayload = { key: string; severity: string; note?: string };

/** Reporte de daños (2.4). No lleva `evidence_ids` del servidor porque en
 *  avión NO EXISTEN todavía: lleva `evidence_refs`, que son ids LOCALES de
 *  items `evidence` de esta misma cola, y se resuelven al despachar. */
export type DamageReportPayload = {
  incident_id: string;
  categories: DamageCategoryPayload[];
  notes: string | null;
  zone_id: string | null;
  evidence_refs: string[];
  ts_device: string;
};

/** El censo de tipos. Añadir uno aquí obliga (por tipos) a darle etiqueta en
 *  la UI y emisor en el motor de sync — no se puede olvidar a medias. */
export type QueuePayloadByKind = {
  checkin: CheckinPayload;
  evidence: EvidencePayload;
  damage_report: DamageReportPayload;
};

export type QueueKind = keyof QueuePayloadByKind;

type QueueItemBase = {
  /** UUID generado en el dispositivo. En un check-in ES el `checkin_id` del
   *  servidor (idempotencia, regla de oro 3). */
  id: string;
  /** SHA-256 sellado al capturar (cadena de custodia). En `evidence` es el
   *  hash de los BYTES del archivo; en el resto, el del payload canónico. */
  sha256: string;
  state: QueueItemState;
  attempts: number;
  /** epoch ms; 0 = elegible ya. */
  next_attempt_at: number;
  created_at: number;
  synced_at: number | null;
  last_error: string | null;
  /** 1 = frente de la cola (personas atrapadas/heridas, §2.4); 0 = normal. */
  priority: number;
  /** Id que devolvió el servidor al aterrizar (`evidence_id`). Es lo que
   *  permite ligar un reporte con las fotos que se subieron después. */
  server_id: string | null;
};

export type QueueItemOf<K extends QueueKind> = QueueItemBase & {
  kind: K;
  payload: QueuePayloadByKind[K];
};

/** Unión discriminada: `kind` y `payload` viajan SIEMPRE juntos. */
export type QueueItem = { [K in QueueKind]: QueueItemOf<K> }[QueueKind];

/** Nada se borra hasta synced + 24 h (criterio T-2.06). */
export const RETENTION_AFTER_SYNC_MS = 24 * 60 * 60 * 1000;

export function newQueueItem<K extends QueueKind>(args: {
  kind: K;
  id: string;
  payload: QueuePayloadByKind[K];
  sha256: string;
  now: number;
  priority?: number;
}): QueueItemOf<K> {
  return {
    id: args.id,
    kind: args.kind,
    payload: args.payload,
    sha256: args.sha256,
    state: "pending",
    attempts: 0,
    next_attempt_at: 0,
    created_at: args.now,
    synced_at: null,
    last_error: null,
    priority: args.priority ?? 0,
    server_id: null,
  };
}

export function markUploading(item: QueueItem): QueueItem {
  return { ...item, state: "uploading" };
}

export function markSynced(item: QueueItem, now: number, serverId?: string | null): QueueItem {
  return {
    ...item,
    state: "synced",
    synced_at: now,
    last_error: null,
    server_id: serverId ?? item.server_id,
  };
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

/** Sube la prioridad de un item ya encolado (un reporte urgente arrastra a sus
 *  fotos al frente: sin ellas no puede despacharse con el enlace forense). */
export function withPriority(item: QueueItem, priority: number): QueueItem {
  return priority > item.priority ? { ...item, priority } : item;
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

/** [T-2.11] Reintento MANUAL de un item fallido (2.5): vuelve a pending
 *  elegible ya, sin sumar intento (el usuario decide reintentar). */
export function retryFailed(item: QueueItem): QueueItem {
  if (item.state !== "failed") {
    return item;
  }
  return { ...item, state: "pending", next_attempt_at: 0, last_error: null };
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

export function indexById(items: QueueItem[]): Map<string, QueueItem> {
  return new Map(items.map((i) => [i.id, i]));
}

/** Referencias de evidencia que TODAVÍA pueden aterrizar y por tanto retienen
 *  al reporte: mandarlo antes perdería para siempre el enlace forense, porque
 *  el `evidence_id` lo inventa el servidor y no hay endpoint para ligar una
 *  foto a un reporte ya creado. Una referencia `failed` NO retiene (ya no va a
 *  aterrizar) y una que no existe tampoco (se podó tras 24 h). */
export function blockingRefs(item: QueueItem, byId: Map<string, QueueItem>): string[] {
  if (item.kind !== "damage_report") {
    return [];
  }
  return item.payload.evidence_refs.filter((ref) => {
    const dep = byId.get(ref);
    return dep !== undefined && (dep.state === "pending" || dep.state === "uploading");
  });
}

/** Traduce refs LOCALES a los `evidence_id` que devolvió el servidor.
 *  `dropped` = fotos que ya nunca se enlazarán (fallaron o se podaron): la UI
 *  lo dice en vez de fingir un reporte completo. */
export function resolveEvidenceIds(
  refs: string[],
  byId: Map<string, QueueItem>,
): { ids: string[]; dropped: number } {
  const ids: string[] = [];
  let dropped = 0;
  for (const ref of refs) {
    const dep = byId.get(ref);
    if (dep?.state === "synced" && dep.server_id) {
      ids.push(dep.server_id);
    } else {
      dropped += 1;
    }
  }
  return { ids, dropped };
}

/** Elegibles YA y en el orden en que deben salir: prioridad máxima primero
 *  (§2.4 — personas atrapadas/heridas saltan al frente), FIFO dentro del mismo
 *  nivel, y fuera los reportes retenidos por fotos aún en vuelo. */
export function dueForDispatch(items: QueueItem[], now: number): QueueItem[] {
  const byId = indexById(items);
  return orderByPriority(
    items.filter((i) => isDue(i, now) && blockingRefs(i, byId).length === 0),
  );
}
