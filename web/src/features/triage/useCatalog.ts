// Catálogo de referencia SSN/USGS (T-1.52) — GET /catalog/earthquakes (T-1.48).
// Datos históricos OFICIALES, globales y de solo lectura: staleTime largo.
//
// [T-9.61] PAGINADO. Con el worker `catalog-sync` el catálogo dejó de ser los 13
// sismos ratificados de T-1.46 y son cientos: el servidor devuelve de
// `CATALOG_PAGE_SIZE` en `CATALOG_PAGE_SIZE`, más reciente primero, con el cursor
// `siguiente` (el `origin_time` del último) que se vuelve `antes_de` en la página
// siguiente. El mapa de la consola usa sólo `primeraPagina`; el panel del
// triage acumula con «CARGAR MÁS».

import { useInfiniteQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { listReferenceEarthquakesCatalogEarthquakesGet } from "@takab/sdk";
import type { CatalogEarthquakeList, CatalogEarthquakeOut } from "@takab/sdk";

export const CATALOG_PAGE_SIZE = 100;

export interface CatalogData {
  /** Todo lo cargado hasta ahora (sin repetidos). */
  items: CatalogEarthquakeOut[];
  /** Sólo la primera página: la que pinta el mapa. */
  primeraPagina: CatalogEarthquakeOut[];
  loading: boolean;
  /** Falló la PRIMERA página: no hay nada que enseñar. */
  error: string | null;
  refetch: () => void;
  hayMas: boolean;
  cargandoMas: boolean;
  /** Falló una página SIGUIENTE: lo ya cargado se conserva. */
  errorMas: string | null;
  cargarMas: () => void;
}

async function fetchPage(antesDe: string | null): Promise<CatalogEarthquakeList> {
  const { data, response } = await listReferenceEarthquakesCatalogEarthquakesGet({
    query: {
      limit: CATALOG_PAGE_SIZE,
      ...(antesDe === null ? {} : { antes_de: antesDe }),
    },
  });
  if (data === undefined) {
    throw new Error(`GET /catalog/earthquakes falló (${response.status})`);
  }
  return data;
}

export function useCatalog(): CatalogData {
  const query = useInfiniteQuery({
    queryKey: ["catalog", "earthquakes", "paginas"],
    staleTime: 86_400_000, // 24 h: catálogo histórico, no telemetría
    queryFn: ({ pageParam }) => fetchPage(pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.siguiente ?? null,
  });

  const primeraPagina = useMemo(() => query.data?.pages[0]?.items ?? [], [query.data]);
  // Un cursor por instante puede repetir el borde entre dos páginas: se pinta
  // una vez, por `ref_id`.
  const items = useMemo(() => {
    const vistos = new Set<string>();
    const out: CatalogEarthquakeOut[] = [];
    for (const page of query.data?.pages ?? []) {
      for (const q of page.items) {
        if (vistos.has(q.ref_id)) continue;
        vistos.add(q.ref_id);
        out.push(q);
      }
    }
    return out;
  }, [query.data]);

  return {
    items,
    primeraPagina,
    loading: query.isPending,
    error: query.data === undefined && query.error ? query.error.message : null,
    refetch: () => {
      void query.refetch();
    },
    hayMas: query.hasNextPage,
    cargandoMas: query.isFetchingNextPage,
    errorMas: query.isFetchNextPageError && query.error ? query.error.message : null,
    cargarMas: () => {
      if (query.hasNextPage && !query.isFetchingNextPage) void query.fetchNextPage();
    },
  };
}
