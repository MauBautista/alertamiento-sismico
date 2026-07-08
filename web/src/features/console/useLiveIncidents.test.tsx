import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import type { IncidentFrame, IncidentOut } from "@takab/sdk";

import { FakeLiveSocket, withLiveSocket } from "../../test-utils/liveSocket";
import { fromFrame, fromOut, mergeIncidents, useLiveIncidents } from "./useLiveIncidents";

const mocks = vi.hoisted(() => ({
  listIncidentsIncidentsGet: vi.fn(),
  TOPIC_INCIDENTS: "incidents",
}));

vi.mock("@takab/sdk", () => mocks);

function out(id: string, over: Partial<IncidentOut> = {}): IncidentOut {
  return {
    incident_id: id,
    tenant_id: "t-1",
    site_id: `s-${id}`,
    event_id: null,
    event_uuid: `uuid-${id}`,
    opened_at: "2026-07-08T10:00:00Z",
    closed_at: null,
    severity: "warning",
    state: "open",
    trigger: "local_threshold",
    max_pga_g: 0.05,
    max_pgv_cms: 1.2,
    summary: {},
    ...over,
  };
}

function frame(id: string, over: Partial<IncidentFrame> = {}): IncidentFrame {
  return {
    type: "incident",
    incident_id: id,
    tenant_id: "t-1",
    site_id: `s-${id}`,
    opened_at: "2026-07-08T10:05:00Z",
    severity: "critical",
    state: "open",
    trigger: "local_threshold",
    ...over,
  };
}

function makeWrapper(socket: FakeLiveSocket) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return withLiveSocket(
      socket,
      <QueryClientProvider client={client}>{children}</QueryClientProvider>,
    );
  };
}

describe("mergeIncidents (puro)", () => {
  it("ordena por severidad desc y luego por más reciente", () => {
    const base = [
      fromOut(out("a", { severity: "info", opened_at: "2026-07-08T09:00:00Z" })),
      fromOut(out("b", { severity: "critical", opened_at: "2026-07-08T08:00:00Z" })),
      fromOut(out("c", { severity: "warning", opened_at: "2026-07-08T10:00:00Z" })),
    ];
    const ids = mergeIncidents(base, new Map()).map((i) => i.incident_id);
    expect(ids).toEqual(["b", "c", "a"]);
  });

  it("el frame upsertea por incident_id y el cierre lo saca de la mesa", () => {
    const base = [fromOut(out("a")), fromOut(out("b"))];
    const closed = fromFrame(frame("a", { closed_at: "2026-07-08T11:00:00Z", state: "closed" }));
    const merged = mergeIncidents(base, new Map([["a", closed]]));
    expect(merged.map((i) => i.incident_id)).toEqual(["b"]);
  });
});

describe("useLiveIncidents", () => {
  it("backfill REST y upsert de frames live", async () => {
    mocks.listIncidentsIncidentsGet.mockResolvedValue({
      data: { items: [out("a")] },
      response: { status: 200 },
    });
    const socket = new FakeLiveSocket();
    const { result } = renderHook(() => useLiveIncidents(), { wrapper: makeWrapper(socket) });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.incidents.map((i) => i.incident_id)).toEqual(["a"]);

    act(() => socket.emit("incidents", frame("nuevo")));
    expect(result.current.incidents.map((i) => i.incident_id)).toEqual(["nuevo", "a"]);
    expect(result.current.lastFrameAt).not.toBeNull();
  });

  it("expone el error solo si nunca hubo datos", async () => {
    mocks.listIncidentsIncidentsGet.mockResolvedValue({
      data: undefined,
      response: { status: 503 },
    });
    const socket = new FakeLiveSocket();
    const { result } = renderHook(() => useLiveIncidents(), { wrapper: makeWrapper(socket) });
    await waitFor(() => expect(result.current.error).toMatch(/503/));
    expect(result.current.incidents).toEqual([]);
  });
});
