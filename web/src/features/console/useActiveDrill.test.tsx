// [T-6.17] El frame `drill` del canal live invalida el banner de simulacro sin
// esperar al sondeo de 10 s. Sin socket, el hook sigue funcionando por sondeo.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TOPIC_INCIDENTS } from "@takab/sdk";

import { FakeLiveSocket } from "../../test-utils/liveSocket";
import { LiveSocketContext } from "./socket";
import { useActiveDrill } from "./useActiveDrill";

const sdk = vi.hoisted(() => ({
  activeDrillDrillsActiveGet: vi.fn(),
  listDrillsDrillsGet: vi.fn(),
}));

vi.mock("@takab/sdk", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@takab/sdk")>()),
  activeDrillDrillsActiveGet: sdk.activeDrillDrillsActiveGet,
  listDrillsDrillsGet: sdk.listDrillsDrillsGet,
}));

function wrapper(socket: FakeLiveSocket | null) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={qc}>
        <LiveSocketContext.Provider value={socket}>{children}</LiveSocketContext.Provider>
      </QueryClientProvider>
    );
  };
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("useActiveDrill · push por WS", () => {
  it("un frame `drill` re-consulta el simulacro activo sin esperar al sondeo", async () => {
    sdk.activeDrillDrillsActiveGet.mockResolvedValue({ data: { drill: null } });
    sdk.listDrillsDrillsGet.mockResolvedValue({ data: { items: [], total: 0 } });
    const socket = new FakeLiveSocket();
    renderHook(() => useActiveDrill(), { wrapper: wrapper(socket) });
    await waitFor(() => expect(sdk.activeDrillDrillsActiveGet).toHaveBeenCalledTimes(1));

    socket.emit(TOPIC_INCIDENTS, {
      type: "drill",
      tenant_id: "t-1",
      drill_id: "d-1",
    } as never);
    await waitFor(() => expect(sdk.activeDrillDrillsActiveGet).toHaveBeenCalledTimes(2));
  });

  it("otros frames del mismo topic no disparan la re-consulta", async () => {
    sdk.activeDrillDrillsActiveGet.mockResolvedValue({ data: { drill: null } });
    sdk.listDrillsDrillsGet.mockResolvedValue({ data: { items: [], total: 0 } });
    const socket = new FakeLiveSocket();
    renderHook(() => useActiveDrill(), { wrapper: wrapper(socket) });
    await waitFor(() => expect(sdk.activeDrillDrillsActiveGet).toHaveBeenCalledTimes(1));

    socket.emit(TOPIC_INCIDENTS, { type: "checkin", tenant_id: "t-1" } as never);
    await new Promise((r) => setTimeout(r, 20));
    expect(sdk.activeDrillDrillsActiveGet).toHaveBeenCalledTimes(1);
  });

  it("sin socket sigue consultando por REST (el sondeo es el respaldo)", async () => {
    sdk.activeDrillDrillsActiveGet.mockResolvedValue({ data: { drill: null } });
    sdk.listDrillsDrillsGet.mockResolvedValue({ data: { items: [], total: 0 } });
    renderHook(() => useActiveDrill(), { wrapper: wrapper(null) });
    await waitFor(() => expect(sdk.activeDrillDrillsActiveGet).toHaveBeenCalledTimes(1));
  });
});
