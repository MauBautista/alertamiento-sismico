// useCatalog (T-1.52): fetch del catálogo global con staleTime de 24 h.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

const sdk = vi.hoisted(() => ({ listReferenceEarthquakesCatalogEarthquakesGet: vi.fn() }));
vi.mock("@takab/sdk", () => sdk);

import { CATALOG_PAGE_SIZE, useCatalog } from "./useCatalog";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{client && children}</QueryClientProvider>;
}

describe("useCatalog", () => {
  it("devuelve los items del endpoint", async () => {
    sdk.listReferenceEarthquakesCatalogEarthquakesGet.mockResolvedValue({
      data: { items: [{ catalog_key: "SSN-X" }] },
      response: { status: 200 },
    });
    const { result } = renderHook(() => useCatalog(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.items).toHaveLength(1);
    expect(result.current.error).toBeNull();
  });

  it("error honesto con el status del fallo", async () => {
    sdk.listReferenceEarthquakesCatalogEarthquakesGet.mockResolvedValue({
      data: undefined,
      response: { status: 503 },
    });
    const { result } = renderHook(() => useCatalog(), { wrapper });
    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.error).toContain("503");
    expect(result.current.items).toEqual([]);
  });

  it("[T-9.61] pide la PRIMERA página con su límite y declara si hay más", async () => {
    sdk.listReferenceEarthquakesCatalogEarthquakesGet.mockResolvedValue({
      data: { items: [{ ref_id: "a" }], siguiente: "2026-09-01T00:00:00Z" },
      response: { status: 200 },
    });
    const { result } = renderHook(() => useCatalog(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(sdk.listReferenceEarthquakesCatalogEarthquakesGet).toHaveBeenLastCalledWith({
      query: { limit: CATALOG_PAGE_SIZE },
    });
    expect(result.current.hayMas).toBe(true);
    expect(result.current.primeraPagina).toHaveLength(1);
  });

  it("[T-9.61] CARGAR MÁS pide `antes_de = siguiente` y ACUMULA; la primera página no cambia", async () => {
    sdk.listReferenceEarthquakesCatalogEarthquakesGet
      .mockResolvedValueOnce({
        data: { items: [{ ref_id: "a" }, { ref_id: "b" }], siguiente: "2020-01-01T00:00:00Z" },
        response: { status: 200 },
      })
      .mockResolvedValueOnce({
        // `b` repetido: un cursor por instante puede devolver el borde otra vez.
        data: { items: [{ ref_id: "b" }, { ref_id: "c" }], siguiente: null },
        response: { status: 200 },
      });
    const { result } = renderHook(() => useCatalog(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => {
      result.current.cargarMas();
    });
    await waitFor(() => expect(result.current.items).toHaveLength(3));
    expect(sdk.listReferenceEarthquakesCatalogEarthquakesGet).toHaveBeenLastCalledWith({
      query: { limit: CATALOG_PAGE_SIZE, antes_de: "2020-01-01T00:00:00Z" },
    });
    expect(result.current.items.map((q) => q.ref_id)).toEqual(["a", "b", "c"]);
    expect(result.current.primeraPagina.map((q) => q.ref_id)).toEqual(["a", "b"]);
    expect(result.current.hayMas).toBe(false);
    expect(result.current.errorMas).toBeNull();
  });

  it("[T-9.61] si falla CARGAR MÁS, lo ya cargado se conserva y el fallo se dice aparte", async () => {
    sdk.listReferenceEarthquakesCatalogEarthquakesGet
      .mockResolvedValueOnce({
        data: { items: [{ ref_id: "a" }], siguiente: "2020-01-01T00:00:00Z" },
        response: { status: 200 },
      })
      .mockResolvedValueOnce({ data: undefined, response: { status: 502 } });
    const { result } = renderHook(() => useCatalog(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => {
      result.current.cargarMas();
    });
    await waitFor(() => expect(result.current.errorMas).not.toBeNull());
    expect(result.current.errorMas).toContain("502");
    expect(result.current.error).toBeNull();
    expect(result.current.items).toHaveLength(1);
  });
});
