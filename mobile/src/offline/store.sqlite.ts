// Persistencia SQLite de la cola offline sobre la base cifrada COMPARTIDA
// (db.ts — SQLCipher verificado en runtime; la caché de documentos vive en la
// misma base, tabla aparte).
import type * as SQLite from "expo-sqlite";

import { openOfflineDb } from "./db";
import type { QueueItem } from "./queue";
import type { EncryptionStatus, QueuePersistence } from "./store";

type Row = {
  id: string;
  kind: string;
  payload: string;
  sha256: string;
  state: string;
  attempts: number;
  next_attempt_at: number;
  created_at: number;
  synced_at: number | null;
  last_error: string | null;
};

export class SqliteQueuePersistence implements QueuePersistence {
  private db: SQLite.SQLiteDatabase | null = null;
  private status: EncryptionStatus = { active: false, cipher: null };

  async init(): Promise<void> {
    const opened = await openOfflineDb();
    this.db = opened.db;
    this.status = opened.encryption;
  }

  encryption(): EncryptionStatus {
    return this.status;
  }

  private handle(): SQLite.SQLiteDatabase {
    if (this.db === null) {
      throw new Error("SqliteQueuePersistence sin init()");
    }
    return this.db;
  }

  async all(): Promise<QueueItem[]> {
    const rows = await this.handle().getAllAsync<Row>(
      "SELECT * FROM queue_items ORDER BY created_at ASC",
    );
    return rows.map((r) => ({
      id: r.id,
      kind: r.kind as QueueItem["kind"],
      payload: JSON.parse(r.payload) as QueueItem["payload"],
      sha256: r.sha256,
      state: r.state as QueueItem["state"],
      attempts: r.attempts,
      next_attempt_at: r.next_attempt_at,
      created_at: r.created_at,
      synced_at: r.synced_at,
      last_error: r.last_error,
    }));
  }

  async upsert(item: QueueItem): Promise<void> {
    await this.handle().runAsync(
      "INSERT OR REPLACE INTO queue_items " +
        "(id, kind, payload, sha256, state, attempts, next_attempt_at, created_at, synced_at, last_error) " +
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
      [
        item.id,
        item.kind,
        JSON.stringify(item.payload),
        item.sha256,
        item.state,
        item.attempts,
        item.next_attempt_at,
        item.created_at,
        item.synced_at,
        item.last_error,
      ],
    );
  }

  async remove(id: string): Promise<void> {
    await this.handle().runAsync("DELETE FROM queue_items WHERE id = ?", [id]);
  }
}
