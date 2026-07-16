// Persistencia SQLite de la cola offline. Con el plugin expo-sqlite
// {useSQLCipher:true} el archivo queda cifrado AES-256 (SQLCipher) con llave
// aleatoria de 32 bytes guardada en el almacén seguro del SO. HONESTIDAD:
// el cifrado se VERIFICA en runtime (PRAGMA cipher_version) — en Expo Go o en
// un build sin SQLCipher el estado queda {active:false} y la UI lo declara;
// jamás se rotula "AES-256" sin comprobarlo (criterio T-2.06).
import * as Crypto from "expo-crypto";
import * as SecureStore from "expo-secure-store";
import * as SQLite from "expo-sqlite";

import type { QueueItem } from "./queue";
import type { EncryptionStatus, QueuePersistence } from "./store";

const DB_NAME = "takab-offline.db";
const DB_KEY_STORE = "takab.offline.dbkey.v1";

const CREATE_SQL = `
CREATE TABLE IF NOT EXISTS queue_items (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  payload TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  state TEXT NOT NULL,
  attempts INTEGER NOT NULL,
  next_attempt_at INTEGER NOT NULL,
  created_at INTEGER NOT NULL,
  synced_at INTEGER,
  last_error TEXT
);`;

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

async function dbKeyHex(): Promise<string> {
  const existing = await SecureStore.getItemAsync(DB_KEY_STORE);
  if (existing) {
    return existing;
  }
  const bytes = await Crypto.getRandomBytesAsync(32);
  const hex = [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");
  await SecureStore.setItemAsync(DB_KEY_STORE, hex);
  return hex;
}

export class SqliteQueuePersistence implements QueuePersistence {
  private db: SQLite.SQLiteDatabase | null = null;
  private status: EncryptionStatus = { active: false, cipher: null };

  async init(): Promise<void> {
    this.db = await SQLite.openDatabaseAsync(DB_NAME);
    // La llave DEBE ser el primer statement tras abrir (SQLCipher);
    // en un build sin SQLCipher el PRAGMA es inocuo.
    const key = await dbKeyHex();
    await this.db.execAsync(`PRAGMA key = "x'${key}'";`);
    const row = await this.db
      .getFirstAsync<{ cipher_version?: string }>("PRAGMA cipher_version;")
      .catch(() => null);
    this.status = row?.cipher_version
      ? { active: true, cipher: `SQLCipher ${row.cipher_version} (AES-256)` }
      : { active: false, cipher: null };
    await this.db.execAsync(CREATE_SQL);
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
