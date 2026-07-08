import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { IncidentActionFrame, IncidentActionOut } from "@takab/sdk";

import { FakeLiveSocket, withLiveSocket } from "../../test-utils/liveSocket";
import { mergeActions, useIncidentActions } from "./useIncidentActions";

const mocks = vi.hoisted(() => ({
  listIncidentActionsIncidentsIncidentIdActionsGet: vi.fn(),
  TOPIC_INCIDENTS: "incidents",
}));

vi.mock("@takab/sdk", () => mocks);

function action(id: string, over: Partial<IncidentActionOut> = {}): IncidentActionOut {
  return {
    action_id: id,
    incident_id: "i-1",
    tenant_id: "t-1",
    ts: "2026-07-08T10:00:00Z",
    kind: "siren_on",
    actor: "edge:gw-dev-0001",
    payload: {},
    ...over,
  };
}

describe("mergeActions (puro)", () => {
  it("dedup por action_id y orden cronológico", () => {
    const merged = mergeActions(
      [action("a", { ts: "2026-07-08T10:00:02Z" }), action("b", { ts: "2026-07-08T10:00:01Z" })],
      [action("a", { ts: "2026-07-08T10:00:02Z" }), action("c", { ts: "2026-07-08T10:00:03Z" })],
    );
    expect(merged.map((a) => a.action_id)).toEqual(["b", "a", "c"]);
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

describe("useIncidentActions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("backfill + frames del MISMO incidente (los ajenos se ignoran)", async () => {
    mocks.listIncidentActionsIncidentsIncidentIdActionsGet.mockResolvedValue({
      data: [action("a")],
      response: { status: 200 },
    });
    const socket = new FakeLiveSocket();
    const { result } = renderHook(() => useIncidentActions("i-1"), {
      wrapper: makeWrapper(socket),
    });
    await waitFor(() => expect(result.current.loading).toBe(false));

    const mine: IncidentActionFrame = {
      type: "incident_action",
      action_id: "b",
      incident_id: "i-1",
      tenant_id: "t-1",
      ts: "2026-07-08T10:00:05Z",
      kind: "ack",
      actor: "user:soc",
      payload: {},
    };
    act(() => {
      socket.emit("incidents", mine);
      socket.emit("incidents", { ...mine, action_id: "x", incident_id: "OTRO" });
    });
    expect(result.current.actions.map((a) => a.action_id)).toEqual(["a", "b"]);
  });

  it("sin incidente no consulta", () => {
    const socket = new FakeLiveSocket();
    const { result } = renderHook(() => useIncidentActions(null), {
      wrapper: makeWrapper(socket),
    });
    expect(result.current.actions).toEqual([]);
    expect(mocks.listIncidentActionsIncidentsIncidentIdActionsGet).not.toHaveBeenCalled();
  });
});
