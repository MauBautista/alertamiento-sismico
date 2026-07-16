// Estado REACTIVO de la cola (zustand) con escritura write-through a la
// persistencia. La UI lee de aquí; la durabilidad la garantiza el store
// (SQLite cifrado en runtime nativo; memoria SOLO inyectada en tests).
import { create } from "zustand";

import { newId, sha256OfJson } from "./custody";
import {
  newQueueItem,
  recoverInterrupted,
  shouldPurge,
  type CheckinPayload,
  type QueueItem,
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
  encryption: EncryptionStatus | null;
  items: QueueItem[];
  hydrate: () => Promise<void>;
  enqueueCheckin: (payload: CheckinPayload) => Promise<QueueItem>;
  /** Persiste una transición y refleja el nuevo estado en memoria. */
  apply: (item: QueueItem) => Promise<void>;
  purgeExpired: (now: number) => Promise<void>;
};

export const useQueueStore = create<QueueStoreState>()((set, get) => ({
  hydrated: false,
  encryption: null,
  items: [],

  hydrate: async () => {
    if (get().hydrated) {
      return;
    }
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
    set({ hydrated: true, encryption: store.encryption(), items });
  },

  enqueueCheckin: async (payload: CheckinPayload) => {
    const item = newQueueItem(newId(), payload, await sha256OfJson(payload), Date.now());
    await (await getPersistence()).upsert(item);
    set((s) => ({ items: [...s.items, item] }));
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
}));

/** Reset SOLO para tests (espejo de resetSessionStoreForTests). */
export function resetQueueStoreForTests(): void {
  persistence = null;
  useQueueStore.setState({ hydrated: false, encryption: null, items: [] });
}
