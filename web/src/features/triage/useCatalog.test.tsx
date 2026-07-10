// useCatalog (T-1.52): fetch del catálogo global con staleTime de 24 h.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

const sdk = vi.hoisted(() => ({ listReferenceEarthquakesCatalogEarthquakesGet: vi.fn() }));
vi.mock("@takab/sdk", () => sdk);

import { useCatalog } from "./useCatalog";

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
});
