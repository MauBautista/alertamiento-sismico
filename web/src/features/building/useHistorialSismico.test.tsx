// [T-9.66 · D-46] El historial sísmico del inmueble: GET /sites/{id}/historial-sismico.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

const sdk = vi.hoisted(() => ({ historialSismicoSitesSiteIdHistorialSismicoGet: vi.fn() }));
vi.mock("@takab/sdk", () => sdk);

import {
  HISTORIAL_DIAS,
  HISTORIAL_REFETCH_MS,
  HISTORIAL_STALE_MS,
  useHistorialSismico,
} from "./useHistorialSismico";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("useHistorialSismico", () => {
  it("pide el historial DEL SITIO con su ventana de días y devuelve eventos y atribución", async () => {
    sdk.historialSismicoSitesSiteIdHistorialSismicoGet.mockResolvedValue({
      data: { eventos: [{ tipo: "sismo", place: "X" }], atribucion: "Fuente: USGS" },
      response: { status: 200 },
    });
    const { result } = renderHook(() => useHistorialSismico("s-1"), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(sdk.historialSismicoSitesSiteIdHistorialSismicoGet).toHaveBeenCalledWith({
      path: { site_id: "s-1" },
      query: { dias: HISTORIAL_DIAS },
    });
    expect(result.current.eventos).toHaveLength(1);
    expect(result.current.atribucion).toBe("Fuente: USGS");
    expect(result.current.error).toBeNull();
    expect(result.current.dataUpdatedAt).toBeGreaterThan(0);
  });

  it("error honesto con el status, sin inventar eventos", async () => {
    sdk.historialSismicoSitesSiteIdHistorialSismicoGet.mockResolvedValue({
      data: undefined,
      response: { status: 403 },
    });
    const { result } = renderHook(() => useHistorialSismico("s-1"), { wrapper });
    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.error).toContain("403");
    expect(result.current.eventos).toEqual([]);
    expect(result.current.atribucion).toBeNull();
  });

  it("se relee antes de llegar a la edad de retenido", () => {
    expect(HISTORIAL_REFETCH_MS).toBeLessThan(HISTORIAL_STALE_MS);
  });
});
