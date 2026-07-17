// Query con copia offline (patrón 1.6/1.7): la respuesta buena se persiste en
// la caché cifrada; sin red se sirve la copia con su edad (StateFrame stale).
// Regla react-hooks v6: nada de setState síncrono en effects — continuaciones.
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { cacheGet, cachePut, type CachedDoc } from "./docCache";

export type CachedQueryResult<T> = {
  /** Dato fresco o copia offline; null mientras no exista ninguno. */
  data: T | null;
  /** Epoch ms de la copia mostrada cuando NO es fresca; null = fresca. */
  staleSinceMs: number | null;
  /** Cargando sin NADA que mostrar. */
  loading: boolean;
  /** Error sin NADA que mostrar (con copia, habla el stale). */
  error: string | null;
  refetch: () => void;
};

export function useCachedQuery<T>(args: {
  cacheKey: string;
  queryKey: unknown[];
  enabled: boolean;
  queryFn: () => Promise<T>;
}): CachedQueryResult<T> {
  const query = useQuery({
    queryKey: args.queryKey,
    enabled: args.enabled,
    queryFn: args.queryFn,
  });
  const [fallback, setFallback] = useState<CachedDoc | null>(null);

  // Persistir la respuesta buena (best-effort declarado en cachePut).
  useEffect(() => {
    if (query.data !== undefined) {
      void cachePut(args.cacheKey, query.data, Date.now());
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- cacheKey estable por pantalla
  }, [query.data, query.dataUpdatedAt]);

  // Sin dato fresco y con error: buscar la copia offline.
  useEffect(() => {
    if (!query.isError || query.data !== undefined) {
      return;
    }
    let alive = true;
    cacheGet(args.cacheKey).then((doc) => {
      if (alive && doc !== null) {
        setFallback(doc);
      }
    });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- cacheKey estable por pantalla
  }, [query.isError, query.data]);

  const fresh = query.data !== undefined;
  const data = fresh ? (query.data as T) : ((fallback?.json as T | undefined) ?? null);
  return {
    data,
    staleSinceMs: !fresh && fallback !== null ? fallback.cached_at : null,
    loading: args.enabled && query.isLoading && data === null,
    error: query.isError && data === null ? "No hay copia local de esta información." : null,
    refetch: () => {
      void query.refetch();
    },
  };
}
