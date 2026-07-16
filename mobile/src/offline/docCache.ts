// Caché de documentos JSON (rutas, directorio, assets — spec 1.6/1.7): última
// respuesta buena persistida con su cached_at para que sin red la pantalla
// muestre DATOS RETENIDOS con edad honesta, jamás un spinner infinito.
export type CachedDoc = { json: unknown; cached_at: number };

export interface DocCachePersistence {
  init(): Promise<void>;
  get(key: string): Promise<CachedDoc | null>;
  put(key: string, json: unknown, cachedAt: number): Promise<void>;
}

export class MemoryDocCache implements DocCachePersistence {
  private docs = new Map<string, CachedDoc>();

  async init(): Promise<void> {}

  async get(key: string): Promise<CachedDoc | null> {
    const doc = this.docs.get(key);
    return doc ? { ...doc } : null;
  }

  async put(key: string, json: unknown, cachedAt: number): Promise<void> {
    this.docs.set(key, { json, cached_at: cachedAt });
  }
}

let impl: DocCachePersistence | null = null;

/** Inyección explícita (tests). En runtime la carga perezosa usa SQLite. */
export function configureDocCache(p: DocCachePersistence): void {
  impl = p;
}

/** Reset SOLO para tests. */
export function resetDocCacheForTests(): void {
  impl = null;
}

async function getImpl(): Promise<DocCachePersistence> {
  if (impl === null) {
    const mod = await import("./docCache.sqlite");
    impl = new mod.SqliteDocCache();
  }
  return impl;
}

export async function cacheGet(key: string): Promise<CachedDoc | null> {
  const p = await getImpl();
  await p.init();
  return p.get(key);
}

/** Best-effort DECLARADO: un fallo al escribir la caché no rompe la pantalla
 *  (el dato fresco ya está en memoria); simplemente no habrá copia offline. */
export async function cachePut(key: string, json: unknown, now: number): Promise<void> {
  try {
    const p = await getImpl();
    await p.init();
    await p.put(key, json, now);
  } catch {
    // sin copia offline esta vez
  }
}
