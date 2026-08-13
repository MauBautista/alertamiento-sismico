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
  // [T-2.129] El topic LOCAL de la salud del canal. Sin él en el doble, el hook
  // se suscribiría a `undefined` y los tests de abajo pasarían por accidente.
  TOPIC_LIVE_HEALTH: "live_health",
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

/* =====================================================================
   [T-2.129] SALUD DEL CANAL — degradado NO es «sin conexión»
   ===================================================================== */

function salud(topic: string, degraded: boolean, detail: string | null = null) {
  return { type: "live_health", topic, degraded, detail } as unknown as IncidentFrame;
}

describe("[T-2.129] useLiveIncidents · degradación del canal live", () => {
  async function montado() {
    mocks.listIncidentsIncidentsGet.mockResolvedValue({
      data: { items: [out("a")] },
      response: { status: 200 },
    });
    const socket = new FakeLiveSocket();
    const { result } = renderHook(() => useLiveIncidents(), { wrapper: makeWrapper(socket) });
    await waitFor(() => expect(result.current.loading).toBe(false));
    return { socket, result };
  }

  it("un canal sano no declara nada", async () => {
    const { result } = await montado();
    expect(result.current.degraded).toEqual([]);
    expect(result.current.liveStatus).toBe("ready");
  });

  it("el frame `live_health` enciende el aviso CON el topic traducido", async () => {
    const { socket, result } = await montado();
    act(() => socket.emit("live_health", salud("incidents", true, "incident: LockTimeout")));
    expect(result.current.degraded).toEqual([
      { topic: "incidents", label: "INCIDENTES", detail: "incident: LockTimeout" },
    ]);
    // Y NO es «sin conexión»: el transporte sigue listo, que es justo la
    // distinción que esta ficha existe para poder hacer.
    expect(result.current.liveStatus).toBe("ready");
  });

  it("`degraded: false` lo APAGA (un aviso perpetuo es otra mentira)", async () => {
    const { socket, result } = await montado();
    act(() => socket.emit("live_health", salud("incidents", true, "x")));
    act(() => socket.emit("live_health", salud("incidents", false)));
    expect(result.current.degraded).toEqual([]);
  });

  it("acumula topics distintos y cada uno se apaga por su cuenta", async () => {
    const { socket, result } = await montado();
    act(() => socket.emit("live_health", salud("incidents", true, "a")));
    act(() => socket.emit("live_health", salud("features:s-1", true, "b")));
    // Orden ESTABLE por topic (no por llegada): dos degradaciones simultáneas no
    // pueden bailar en pantalla según cuál avisó primero.
    expect(result.current.degraded.map((d) => d.label)).toEqual(["SISMOGRAMA", "INCIDENTES"]);
    act(() => socket.emit("live_health", salud("incidents", false)));
    expect(result.current.degraded.map((d) => d.topic)).toEqual(["features:s-1"]);
  });

  it("al caerse el socket se OLVIDA la degradación: el servidor no la recuerda", async () => {
    // Al reconectar, el hub registra un suscriptor NUEVO y limpio. Arrastrar el
    // aviso del socket anterior pintaría una degradación que ya no existe —y que
    // nadie podría apagar, porque su `degraded: false` nunca llegará.
    const { socket, result } = await montado();
    act(() => socket.emit("live_health", salud("incidents", true, "x")));
    act(() => socket.setStatus("connecting"));
    expect(result.current.degraded).toEqual([]);
  });
});
