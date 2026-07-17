// Contrato de persistencia de la cola + implementación en memoria (tests y
// fallback declarado). La implementación SQLite/SQLCipher vive en
// store.sqlite.ts para que jest jamás cargue el módulo nativo.
import type { QueueItem } from "./queue";

export type EncryptionStatus = {
  /** true SOLO si SQLCipher respondió PRAGMA cipher_version (verificado). */
  active: boolean;
  /** p.ej. "SQLCipher 4.6.1 (AES-256)"; null = SIN cifrado (se declara, §7). */
  cipher: string | null;
};

export interface QueuePersistence {
  init(): Promise<void>;
  all(): Promise<QueueItem[]>;
  upsert(item: QueueItem): Promise<void>;
  remove(id: string): Promise<void>;
  encryption(): EncryptionStatus;
}

/** Persistencia en memoria: para tests y como último recurso EXPLÍCITO
 *  (encryption().active === false — la UI lo declara, jamás lo esconde). */
export class MemoryQueuePersistence implements QueuePersistence {
  private items = new Map<string, QueueItem>();

  async init(): Promise<void> {}

  async all(): Promise<QueueItem[]> {
    return [...this.items.values()].sort((a, b) => a.created_at - b.created_at);
  }

  async upsert(item: QueueItem): Promise<void> {
    this.items.set(item.id, { ...item });
  }

  async remove(id: string): Promise<void> {
    this.items.delete(id);
  }

  encryption(): EncryptionStatus {
    return { active: false, cipher: null };
  }
}
