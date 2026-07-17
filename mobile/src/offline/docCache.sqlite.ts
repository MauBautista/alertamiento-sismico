// Impl SQLite de la caché de documentos, sobre la base cifrada compartida.
import type * as SQLite from "expo-sqlite";

import { openOfflineDb } from "./db";
import type { CachedDoc, DocCachePersistence } from "./docCache";

export class SqliteDocCache implements DocCachePersistence {
  private db: SQLite.SQLiteDatabase | null = null;

  async init(): Promise<void> {
    if (this.db === null) {
      this.db = (await openOfflineDb()).db;
    }
  }

  private handle(): SQLite.SQLiteDatabase {
    if (this.db === null) {
      throw new Error("SqliteDocCache sin init()");
    }
    return this.db;
  }

  async get(key: string): Promise<CachedDoc | null> {
    const row = await this.handle().getFirstAsync<{ json: string; cached_at: number }>(
      "SELECT json, cached_at FROM doc_cache WHERE key = ?",
      [key],
    );
    if (!row) {
      return null;
    }
    return { json: JSON.parse(row.json) as unknown, cached_at: row.cached_at };
  }

  async put(key: string, json: unknown, cachedAt: number): Promise<void> {
    await this.handle().runAsync(
      "INSERT OR REPLACE INTO doc_cache (key, json, cached_at) VALUES (?, ?, ?)",
      [key, JSON.stringify(json), cachedAt],
    );
  }
}
