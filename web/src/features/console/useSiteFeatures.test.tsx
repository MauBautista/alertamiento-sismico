import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { FeatureSeries, FeaturesFrame } from "@takab/sdk";

import { FakeLiveSocket, withLiveSocket } from "../../test-utils/liveSocket";
import { appendRows, seriesToPoints, useSiteFeatures } from "./useSiteFeatures";

const mocks = vi.hoisted(() => ({
  siteFeaturesTelemetrySitesSiteIdFeaturesGet: vi.fn(),
  featuresTopic: (siteId: string) => `features:${siteId}`,
}));

vi.mock("@takab/sdk", () => mocks);

const SERIES: FeatureSeries = {
  ts: ["2026-07-08T10:00:00Z", "2026-07-08T10:00:01Z"],
  pga: [0.01, 0.02],
  pgv: [0.1, 0.2],
  stalta: [1.0, 1.1],
  clipping: [false, false],
  calibrated: false,
};

describe("seriesToPoints / appendRows (puro)", () => {
  it("colapsa filas por segundo con máximos y clipping OR", () => {
    const base = seriesToPoints(SERIES);
    const merged = appendRows(base, [
      { ts: "2026-07-08T10:00:01.400Z", channel: "ENZ", pga_g: 0.05, clipping: true },
      { ts: "2026-07-08T10:00:01.600Z", channel: "ENN", pga_g: 0.03, stalta: 4.0 },
      { ts: "2026-07-08T10:00:02Z", channel: "ENZ", pga_g: 0.04 },
    ]);
    expect(merged).toHaveLength(3);
    const second = merged[1];
    expect(second.pga).toBe(0.05); // máximo entre backfill (0.02) y canales live
    expect(second.stalta).toBe(4.0);
    expect(second.clipping).toBe(true);
  });

  it("recorta a la ventana rodante de 600 s y es idempotente", () => {
    const base = seriesToPoints(SERIES);
    const rows = [{ ts: "2026-07-08T10:11:00Z", channel: "ENZ", pga_g: 0.02 }];
    const once = appendRows(base, rows);
    expect(once.map((p) => p.ts)).not.toContain(Date.parse("2026-07-08T10:00:00Z"));
    expect(appendRows(once, rows)).toEqual(once); // duplicado ⇒ cero deltas
  });
});

function makeWrapper(socket: FakeLiveSocket) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return withLiveSocket(
      socket,
      <QueryClientProvider client={client}>{children}</QueryClientProvider>,
    );
  };
}

describe("useSiteFeatures", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("backfill + frames live del topic del sitio", async () => {
    mocks.siteFeaturesTelemetrySitesSiteIdFeaturesGet.mockResolvedValue({
      data: SERIES,
      response: { status: 200 },
    });
    const socket = new FakeLiveSocket();
    const { result } = renderHook(() => useSiteFeatures("s-1"), {
      wrapper: makeWrapper(socket),
    });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.points).toHaveLength(2);

    const frame: FeaturesFrame = {
      type: "features",
      site_id: "s-1",
      rows: [{ ts: "2026-07-08T10:00:02Z", channel: "ENZ", pga_g: 0.09, clipping: false }],
    };
    act(() => socket.emit("features:s-1", frame));
    expect(result.current.points).toHaveLength(3);
    expect(result.current.latest?.pga).toBe(0.09);
    expect(result.current.lastFrameAt).not.toBeNull();
  });

  it("sin sitio no consulta ni truena", () => {
    const socket = new FakeLiveSocket();
    const { result } = renderHook(() => useSiteFeatures(null), {
      wrapper: makeWrapper(socket),
    });
    expect(result.current.loading).toBe(false);
    expect(result.current.points).toEqual([]);
    expect(mocks.siteFeaturesTelemetrySitesSiteIdFeaturesGet).not.toHaveBeenCalled();
  });
});
