// Base SQLite ÚNICA del almacenamiento offline (cola + caché de documentos),
// cifrada con SQLCipher cuando el build lo trae. HONESTIDAD: el cifrado se
// VERIFICA en runtime (PRAGMA cipher_version tras PRAGMA key) — en Expo Go o
// en un build sin SQLCipher el estado queda {active:false} y la UI lo declara;
// jamás se rotula "AES-256" sin comprobarlo (criterio T-2.06).
import * as Crypto from "expo-crypto";
import * as SecureStore from "expo-secure-store";
import * as SQLite from "expo-sqlite";

import type { EncryptionStatus } from "./store";

const DB_NAME = "takab-offline.db";
const DB_KEY_STORE = "takab.offline.dbkey.v1";

const SCHEMA_SQL = `
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
  last_error TEXT,
  priority INTEGER NOT NULL DEFAULT 0,
  server_id TEXT
);
CREATE TABLE IF NOT EXISTS doc_cache (
  key TEXT PRIMARY KEY,
  json TEXT NOT NULL,
  cached_at INTEGER NOT NULL
);`;

export type OfflineDb = {
  db: SQLite.SQLiteDatabase;
  encryption: EncryptionStatus;
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

/** [T-2.108] Columnas nuevas de la cola multi-tipo sobre una base YA creada:
 *  `CREATE TABLE IF NOT EXISTS` no las añade a un teléfono que ya venía con la
 *  tabla vieja, y perder la cola de alguien para migrarla no es opción (dentro
 *  puede haber un check-in de vida sin sincronizar). SQLite no tiene
 *  `ADD COLUMN IF NOT EXISTS`: se intenta y se ignora el "duplicate column". */
async function migrateQueueColumns(db: SQLite.SQLiteDatabase): Promise<void> {
  const adds = [
    "ALTER TABLE queue_items ADD COLUMN priority INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE queue_items ADD COLUMN server_id TEXT",
  ];
  for (const sql of adds) {
    await db.execAsync(sql).catch(() => undefined);
  }
}

let opened: Promise<OfflineDb> | null = null;

/** Abre (una sola vez) la base cifrada compartida del modo offline. */
export function openOfflineDb(): Promise<OfflineDb> {
  if (opened === null) {
    opened = (async () => {
      const db = await SQLite.openDatabaseAsync(DB_NAME);
      // La llave DEBE ser el primer statement tras abrir (SQLCipher);
      // en un build sin SQLCipher el PRAGMA es inocuo.
      const key = await dbKeyHex();
      await db.execAsync(`PRAGMA key = "x'${key}'";`);
      const row = await db
        .getFirstAsync<{ cipher_version?: string }>("PRAGMA cipher_version;")
        .catch(() => null);
      const encryption: EncryptionStatus = row?.cipher_version
        ? { active: true, cipher: `SQLCipher ${row.cipher_version} (AES-256)` }
        : { active: false, cipher: null };
      await db.execAsync(SCHEMA_SQL);
      await migrateQueueColumns(db);
      return { db, encryption };
    })();
  }
  return opened;
}
