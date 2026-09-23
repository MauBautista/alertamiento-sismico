// [A-112 · T-8.09] La cabecera del edificio pasaba a «DATOS RETENIDOS» a los 5
// minutos con todo funcionando: `GET /sites/{id}` se pedía UNA vez y nunca más,
// y el marco declaraba vieja una identidad que nadie releía.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const sdk = vi.hoisted(() => ({ getSiteSitesSiteIdGet: vi.fn() }));
vi.mock("@takab/sdk", () => sdk);

import { SITE_REFRESH_MS, SITE_STALE_MS, useBuildingSite } from "./useBuildingSite";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

/** Avanza el reloj falso DENTRO de `act`: las relecturas actualizan estado. */
async function avanza(ms: number): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  sdk.getSiteSitesSiteIdGet.mockResolvedValue({
    data: { site_id: "s-1", name: "Torre", code: "T-1", lat: 19, lon: -99 },
    response: { status: 200 },
  });
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useBuildingSite · la identidad del edificio se relee", () => {
  it("la cadencia es más corta que el umbral de retención", () => {
    expect(SITE_REFRESH_MS).toBeLessThan(SITE_STALE_MS);
  });

  it("con el servidor sano, nunca llega a la edad de retenido", async () => {
    const { result } = renderHook(() => useBuildingSite("s-1"), { wrapper });
    await avanza(10);
    expect(sdk.getSiteSitesSiteIdGet).toHaveBeenCalledTimes(1);

    await avanza(SITE_STALE_MS - 1_000);
    expect(sdk.getSiteSitesSiteIdGet.mock.calls.length).toBeGreaterThan(1);
    expect(Date.now() - result.current.dataUpdatedAt).toBeLessThan(SITE_STALE_MS);
  });

  it("un fallo se declara con el código del servidor", async () => {
    sdk.getSiteSitesSiteIdGet.mockResolvedValue({ data: undefined, response: { status: 404 } });
    const { result } = renderHook(() => useBuildingSite("s-1"), { wrapper });
    await avanza(10);
    expect(result.current.error?.message).toMatch(/404/);
  });
});
