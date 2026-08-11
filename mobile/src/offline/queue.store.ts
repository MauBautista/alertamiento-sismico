// Estado REACTIVO de la cola (zustand) con escritura write-through a la
// persistencia. La UI lee de aquí; la durabilidad la garantiza el store
// (SQLite cifrado en runtime nativo; memoria SOLO inyectada en tests).
import { create } from "zustand";

import { newId, sha256OfJson } from "./custody";
import {
  newQueueItem,
  recoverInterrupted,
  shouldPurge,
  withPriority,
  type CheckinPayload,
  type DamageReportPayload,
  type EvidencePayload,
  type QueueItem,
  type QueueItemOf,
  type QueueKind,
  type QueuePayloadByKind,
} from "./queue";
import type { EncryptionStatus, QueuePersistence } from "./store";

let persistence: QueuePersistence | null = null;

/** Inyección explícita (tests). En runtime la carga perezosa usa SQLite. */
export function configureQueuePersistence(p: QueuePersistence): void {
  persistence = p;
}

async function getPersistence(): Promise<QueuePersistence> {
  if (persistence === null) {
    // Carga perezosa: jest jamás toca el módulo nativo si inyecta memoria.
    const mod = await import("./store.sqlite");
    persistence = new mod.SqliteQueuePersistence();
  }
  return persistence;
}

type QueueStoreState = {
  hydrated: boolean;
  /** Abrir la cola local puede FALLAR (SQLCipher, disco). Se declara: sin esto
   *  la pantalla 2.5 se quedaba en "Cargando…" para siempre (regla de oro 7). */
  hydrationError: string | null;
  encryption: EncryptionStatus | null;
  items: QueueItem[];
  hydrate: () => Promise<void>;
  enqueueCheckin: (payload: CheckinPayload) => Promise<QueueItemOf<"checkin">>;
  /** La huella se calculó sobre los BYTES del archivo AL CAPTURAR y entra tal
   *  cual: la cola nunca re-hashea ni reescribe la evidencia (§4.2). */
  enqueueEvidence: (
    payload: EvidencePayload,
    sha256: string,
  ) => Promise<QueueItemOf<"evidence">>;
  enqueueDamageReport: (
    payload: DamageReportPayload,
    priority: number,
  ) => Promise<QueueItemOf<"damage_report">>;
  /** Persiste una transición y refleja el nuevo estado en memoria. */
  apply: (item: QueueItem) => Promise<void>;
  purgeExpired: (now: number) => Promise<void>;
};

export const useQueueStore = create<QueueStoreState>()((set, get) => {
  /** Alta genérica: el único camino de escritura. Un tipo nuevo (headcount)
   *  se añade con un envoltorio de una línea, sin tocar la cola. */
  async function enqueue<K extends QueueKind>(args: {
    kind: K;
    payload: QueuePayloadByKind[K];
    sha256: string;
    priority?: number;
  }): Promise<QueueItemOf<K>> {
    const item = newQueueItem({
      kind: args.kind,
      id: newId(),
      payload: args.payload,
      sha256: args.sha256,
      now: Date.now(),
      priority: args.priority,
    });
    // `QueueItemOf<K>` ES un miembro de la unión `QueueItem` por construcción,
    // pero TypeScript no lo demuestra con `K` genérica (limitación conocida al
    // indexar un tipo mapeado): un único ensanche, aquí y en ningún otro sitio.
    const stored = item as QueueItem;
    await (await getPersistence()).upsert(stored);
    set((s) => ({ items: [...s.items, stored] }));
    return item;
  }

  return {
    hydrated: false,
    hydrationError: null,
    encryption: null,
    items: [],

    hydrate: async () => {
      if (get().hydrated) {
        return;
      }
      try {
        const store = await getPersistence();
        await store.init();
        const items: QueueItem[] = [];
        for (const raw of await store.all()) {
          const item = recoverInterrupted(raw);
          if (item !== raw) {
            await store.upsert(item);
          }
          items.push(item);
        }
        set({ hydrated: true, hydrationError: null, encryption: store.encryption(), items });
      } catch (e) {
        set({
          hydrated: false,
          hydrationError:
            e instanceof Error && e.message ? e.message : "no se pudo abrir el almacén local",
        });
      }
    },

    enqueueCheckin: async (payload) =>
      enqueue({ kind: "checkin", payload, sha256: await sha256OfJson(payload) }),

    enqueueEvidence: (payload, sha256) => enqueue({ kind: "evidence", payload, sha256 }),

    enqueueDamageReport: async (payload, priority) => {
      const item = await enqueue({
        kind: "damage_report",
        payload,
        sha256: await sha256OfJson(payload),
        priority,
      });
      // Las fotos de un reporte urgente HEREDAN su prioridad: el reporte no
      // puede salir sin ellas (perdería el enlace forense), así que dejarlas
      // detrás de la cola normal retrasaría justo el aviso de vidas en riesgo.
      const refs = new Set(payload.evidence_refs);
      for (const dep of get().items) {
        if (refs.has(dep.id)) {
          const bumped = withPriority(dep, priority);
          if (bumped !== dep) {
            await get().apply(bumped);
          }
        }
      }
      return item;
    },

    apply: async (item: QueueItem) => {
      await (await getPersistence()).upsert(item);
      set((s) => ({ items: s.items.map((i) => (i.id === item.id ? item : i)) }));
    },

    purgeExpired: async (now: number) => {
      const expired = get().items.filter((i) => shouldPurge(i, now));
      const store = await getPersistence();
      for (const item of expired) {
        await store.remove(item.id);
      }
      if (expired.length > 0) {
        const gone = new Set(expired.map((i) => i.id));
        set((s) => ({ items: s.items.filter((i) => !gone.has(i.id)) }));
      }
    },
  };
});

/** Reset SOLO para tests (espejo de resetSessionStoreForTests). */
export function resetQueueStoreForTests(): void {
  persistence = null;
  useQueueStore.setState({
    hydrated: false,
    hydrationError: null,
    encryption: null,
    items: [],
  });
}
