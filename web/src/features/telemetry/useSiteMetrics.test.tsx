// [A-112 · T-8.09] El historial pasaba a «DATOS RETENIDOS» a los 3 minutos
// aunque todo funcionara: la consulta NO tenía cadencia, así que nunca se
// releía, y el marco —con razón— declaraba viejo un dato que nadie refrescaba.
// Un rótulo de retención que salta con el sistema sano entrena a ignorarlo, y
// entonces no se lee el día que es verdad (regla de oro 7, en las dos direcciones).
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const sdk = vi.hoisted(() => ({ siteMetricsTelemetrySitesSiteIdMetricsGet: vi.fn() }));
vi.mock("@takab/sdk", () => sdk);

import { METRICS_REFRESH_MS, METRICS_STALE_MS, useSiteMetrics } from "./useSiteMetrics";

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
  sdk.siteMetricsTelemetrySitesSiteIdMetricsGet.mockResolvedValue({
    data: { ts: [], max_pga_g: [], max_pgv_cms: [], bucket: "1m", calibrated: true },
    response: { status: 200 },
  });
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useSiteMetrics · se relee antes de envejecer", () => {
  it("la cadencia es más corta que el umbral de retención", () => {
    expect(METRICS_REFRESH_MS).toBeLessThan(METRICS_STALE_MS);
  });

  it("con el servidor sano, vuelve a preguntar antes de que el marco la declare vieja", async () => {
    const { result } = renderHook(() => useSiteMetrics("s-1", "24h"), { wrapper });
    await avanza(10);
    expect(sdk.siteMetricsTelemetrySitesSiteIdMetricsGet).toHaveBeenCalledTimes(1);
    const primera = result.current.dataUpdatedAt;

    await avanza(METRICS_STALE_MS - 1_000);
    expect(sdk.siteMetricsTelemetrySitesSiteIdMetricsGet.mock.calls.length).toBeGreaterThan(1);
    // Y la edad que mira el marco se renovó: por debajo del umbral, no por encima.
    expect(result.current.dataUpdatedAt).toBeGreaterThan(primera);
    expect(Date.now() - result.current.dataUpdatedAt).toBeLessThan(METRICS_STALE_MS);
  });
});
