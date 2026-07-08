import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import type { MapSiteState } from "@takab/sdk";

import { FakeLiveSocket, withLiveSocket } from "../../test-utils/liveSocket";
import { useMapState } from "./useMapState";

const mocks = vi.hoisted(() => ({
  mapStateTelemetryMapStateGet: vi.fn(),
  TOPIC_INCIDENTS: "incidents",
  TOPIC_SITE_STATE: "site_state",
}));

vi.mock("@takab/sdk", () => mocks);

const SITE: MapSiteState = {
  site_id: "s-1",
  tenant_id: "t-1",
  name: "Planta Cholula",
  criticality: "high",
  lon: -98.3,
  lat: 19.06,
  last_bucket: "2026-07-08T10:00:00Z",
  max_pga_g: 0.05,
  max_pgv_cms: 1.1,
  open_incident: null,
};

function makeWrapper(socket: FakeLiveSocket) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return withLiveSocket(
      socket,
      <QueryClientProvider client={client}>{children}</QueryClientProvider>,
    );
  };
}

describe("useMapState", () => {
  it("entrega los sitios del snapshot y re-consulta al llegar un frame", async () => {
    mocks.mapStateTelemetryMapStateGet.mockResolvedValue({
      data: { sites: [SITE] },
      response: { status: 200 },
    });
    const socket = new FakeLiveSocket();
    const { result } = renderHook(() => useMapState(), { wrapper: makeWrapper(socket) });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.sites).toHaveLength(1);
    expect(mocks.mapStateTelemetryMapStateGet).toHaveBeenCalledTimes(1);

    // frame live ⇒ invalidación (fetch-on-notify); el segundo frame inmediato
    // queda dentro del throttle y NO produce otra consulta.
    act(() => {
      socket.emit("incidents", { type: "incident" } as never);
      socket.emit("site_state", { type: "site_state" } as never);
    });
    await waitFor(() => expect(mocks.mapStateTelemetryMapStateGet).toHaveBeenCalledTimes(2));
  });
});
