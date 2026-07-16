// El patrón offline de 1.6/1.7: éxito ⇒ persiste copia; sin red ⇒ sirve la
// copia con edad (stale); sin red NI copia ⇒ error honesto (jamás spinner
// infinito).
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react-native";

import { configureDocCache, MemoryDocCache, resetDocCacheForTests } from "./docCache";
import { useCachedQuery } from "./useCachedQuery";

function wrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  }
  return Wrapper;
}

let cache: MemoryDocCache;

beforeEach(() => {
  resetDocCacheForTests();
  cache = new MemoryDocCache();
  configureDocCache(cache);
});

describe("useCachedQuery", () => {
  it("éxito: entrega el dato fresco (sin stale) y lo persiste en la caché", async () => {
    const { result } = await renderHook(
      () =>
        useCachedQuery({
          cacheKey: "rutas:s1",
          queryKey: ["rutas", "s1"],
          enabled: true,
          queryFn: async () => ["ruta-norte"],
        }),
      { wrapper: wrapper() },
    );
    await waitFor(() => expect(result.current.data).toEqual(["ruta-norte"]));
    expect(result.current.staleSinceMs).toBeNull();
    expect(result.current.error).toBeNull();
    await waitFor(async () => {
      expect((await cache.get("rutas:s1"))?.json).toEqual(["ruta-norte"]);
    });
  });

  it("sin red CON copia: sirve la copia con su edad (stale honesto)", async () => {
    await cache.put("rutas:s1", ["ruta-cacheada"], 1_800_000_000_000);
    const { result } = await renderHook(
      () =>
        useCachedQuery({
          cacheKey: "rutas:s1",
          queryKey: ["rutas", "s1", "offline"],
          enabled: true,
          queryFn: async () => {
            throw new TypeError("Network request failed");
          },
        }),
      { wrapper: wrapper() },
    );
    await waitFor(() => expect(result.current.data).toEqual(["ruta-cacheada"]));
    expect(result.current.staleSinceMs).toBe(1_800_000_000_000);
    expect(result.current.error).toBeNull();
  });

  it("sin red SIN copia: error declarado, jamás spinner infinito", async () => {
    const { result } = await renderHook(
      () =>
        useCachedQuery({
          cacheKey: "rutas:vacio",
          queryKey: ["rutas", "vacio"],
          enabled: true,
          queryFn: async () => {
            throw new TypeError("Network request failed");
          },
        }),
      { wrapper: wrapper() },
    );
    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.loading).toBe(false);
    expect(result.current.data).toBeNull();
  });
});
