import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LiveSocket, liveWsUrl } from "./ws";

/** Doble del WebSocket nativo: registra instancias y frames enviados, y deja
 *  que el test dispare open/message/close como lo haría el servidor. */
class FakeWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;
  static instances: FakeWebSocket[] = [];

  url: string;
  readyState = FakeWebSocket.CONNECTING;
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: ((ev: { code: number }) => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  send(data: string): void {
    this.sent.push(data);
  }

  close(code = 1000): void {
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.({ code });
  }

  // --- helpers del "servidor" ---
  open(): void {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.();
  }

  message(frame: unknown): void {
    this.onmessage?.({ data: typeof frame === "string" ? frame : JSON.stringify(frame) });
  }

  serverClose(code: number): void {
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.({ code });
  }
}

function lastSocket(): FakeWebSocket {
  const ws = FakeWebSocket.instances.at(-1);
  if (!ws) throw new Error("sin instancias de FakeWebSocket");
  return ws;
}

function sentFrames(ws: FakeWebSocket): Array<Record<string, unknown>> {
  return ws.sent.map((s) => JSON.parse(s) as Record<string, unknown>);
}

const INCIDENT_FRAME = {
  type: "incident",
  incident_id: "11111111-1111-1111-1111-111111111111",
  tenant_id: "22222222-2222-2222-2222-222222222222",
  site_id: "33333333-3333-3333-3333-333333333333",
  opened_at: "2026-07-08T10:00:00Z",
  severity: "critical",
  state: "open",
  trigger: "local_threshold",
};

function makeSocket(overrides: { onUnauthorized?: () => void } = {}) {
  const onUnauthorized = overrides.onUnauthorized ?? vi.fn();
  const socket = new LiveSocket({
    url: "ws://localhost/api/ws",
    getToken: () => "tok-1",
    onUnauthorized,
  });
  return { socket, onUnauthorized };
}

describe("LiveSocket", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-07-08T10:00:00Z"));
    FakeWebSocket.instances = [];
    vi.stubGlobal("WebSocket", FakeWebSocket);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("envía auth como PRIMER y único frame al abrir", () => {
    const { socket } = makeSocket();
    socket.connect();
    const ws = lastSocket();
    expect(ws.sent).toHaveLength(0); // nada antes del open
    ws.open();
    expect(sentFrames(ws)).toEqual([{ type: "auth", token: "tok-1" }]);
    socket.close();
  });

  it("subscribe espera al ready y no duplica el frame por topic", () => {
    const { socket } = makeSocket();
    socket.subscribe("incidents", vi.fn());
    socket.subscribe("incidents", vi.fn()); // segundo listener, mismo topic
    socket.connect();
    const ws = lastSocket();
    ws.open();
    expect(sentFrames(ws)).toHaveLength(1); // solo auth: aún sin ready
    ws.message({ type: "ready" });
    expect(sentFrames(ws)).toEqual([
      { type: "auth", token: "tok-1" },
      { type: "subscribe", topic: "incidents" },
    ]);
    expect(socket.status).toBe("ready");
    socket.close();
  });

  it("despacha frames al topic correcto (espejo del hub)", () => {
    const { socket } = makeSocket();
    const onIncidents = vi.fn();
    const onSiteState = vi.fn();
    const onFeatures = vi.fn();
    socket.subscribe("incidents", onIncidents);
    socket.subscribe("site_state", onSiteState);
    socket.subscribe("features:33333333-3333-3333-3333-333333333333", onFeatures);
    socket.connect();
    const ws = lastSocket();
    ws.open();
    ws.message({ type: "ready" });

    ws.message(INCIDENT_FRAME);
    ws.message({ ...INCIDENT_FRAME, type: "incident_action", action_id: "a", kind: "ack" });
    ws.message({
      type: "site_state",
      kind: "device_health",
      tenant_id: INCIDENT_FRAME.tenant_id,
      gateway_id: "44444444-4444-4444-4444-444444444444",
      ts: "2026-07-08T10:00:01Z",
    });
    ws.message({
      type: "features",
      site_id: "33333333-3333-3333-3333-333333333333",
      rows: [],
    });

    expect(onIncidents).toHaveBeenCalledTimes(2); // incident + incident_action
    expect(onSiteState).toHaveBeenCalledTimes(1);
    expect(onFeatures).toHaveBeenCalledTimes(1);
    expect(onIncidents.mock.calls[0][0]).toMatchObject({ type: "incident" });
    socket.close();
  });

  it("registra lastFrameAt por topic (staleness)", () => {
    const { socket } = makeSocket();
    socket.subscribe("incidents", vi.fn());
    socket.connect();
    const ws = lastSocket();
    ws.open();
    ws.message({ type: "ready" });
    expect(socket.lastFrameAt("incidents")).toBeNull();
    ws.message(INCIDENT_FRAME);
    expect(socket.lastFrameAt("incidents")).toBe(Date.parse("2026-07-08T10:00:00Z"));
    expect(socket.lastFrameAt("site_state")).toBeNull();
    socket.close();
  });

  it("reconecta con backoff exponencial y se resuscribe al reabrir", () => {
    const { socket } = makeSocket();
    socket.subscribe("incidents", vi.fn());
    socket.subscribe("site_state", vi.fn());
    socket.connect();
    lastSocket().open();
    lastSocket().message({ type: "ready" });
    expect(FakeWebSocket.instances).toHaveLength(1);

    lastSocket().serverClose(1006); // caída no intencional
    expect(socket.status).toBe("connecting");
    vi.advanceTimersByTime(1100 + 1); // 1er reintento ≈1 s (+jitter ≤10%)
    expect(FakeWebSocket.instances).toHaveLength(2);

    // reabre: auth de nuevo y RE-subscribe de TODOS los topics
    lastSocket().open();
    lastSocket().message({ type: "ready" });
    const frames = sentFrames(lastSocket());
    expect(frames[0]).toEqual({ type: "auth", token: "tok-1" });
    const topics = frames.filter((f) => f.type === "subscribe").map((f) => f.topic);
    expect(topics.sort()).toEqual(["incidents", "site_state"]);

    // segunda caída SIN ready intermedio no aplica: hubo ready ⇒ backoff se resetea
    lastSocket().serverClose(1006);
    vi.advanceTimersByTime(1100 + 1);
    expect(FakeWebSocket.instances).toHaveLength(3);

    // caída antes del ready ⇒ el siguiente delay crece (≈2 s): a 1.1 s aún nada
    lastSocket().serverClose(1006);
    vi.advanceTimersByTime(1100);
    expect(FakeWebSocket.instances).toHaveLength(3);
    vi.advanceTimersByTime(1200);
    expect(FakeWebSocket.instances).toHaveLength(4);
    socket.close();
  });

  it("close 4401 ⇒ onUnauthorized y SIN reconexión", () => {
    const onUnauthorized = vi.fn();
    const { socket } = makeSocket({ onUnauthorized });
    socket.connect();
    lastSocket().open();
    lastSocket().serverClose(4401);
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
    expect(socket.status).toBe("closed");
    vi.advanceTimersByTime(120_000);
    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it("close() intencional no reconecta", () => {
    const { socket } = makeSocket();
    socket.connect();
    lastSocket().open();
    socket.close();
    expect(socket.status).toBe("closed");
    vi.advanceTimersByTime(120_000);
    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it("ignora frames desconocidos o corruptos sin romper", () => {
    const { socket } = makeSocket();
    const onIncidents = vi.fn();
    socket.subscribe("incidents", onIncidents);
    socket.connect();
    const ws = lastSocket();
    ws.open();
    ws.message({ type: "ready" });
    expect(() => ws.message({ type: "frame-del-futuro" })).not.toThrow();
    expect(() => ws.message("esto no es json")).not.toThrow();
    ws.message(INCIDENT_FRAME); // el socket sigue vivo y despachando
    expect(onIncidents).toHaveBeenCalledTimes(1);
    socket.close();
  });

  it("el unsubscribe deja de despachar a ese listener", () => {
    const { socket } = makeSocket();
    const cb = vi.fn();
    const off = socket.subscribe("incidents", cb);
    socket.connect();
    const ws = lastSocket();
    ws.open();
    ws.message({ type: "ready" });
    off();
    ws.message(INCIDENT_FRAME);
    expect(cb).not.toHaveBeenCalled();
    socket.close();
  });

  it("notifica cambios de estado por onStatus", () => {
    const { socket } = makeSocket();
    const seen: string[] = [];
    socket.onStatus((s) => seen.push(s));
    socket.connect();
    lastSocket().open();
    lastSocket().message({ type: "ready" });
    socket.close();
    expect(seen).toEqual(["connecting", "ready", "closed"]);
  });
});

describe("liveWsUrl", () => {
  it("resuelve base relativa contra location con protocolo ws", () => {
    // jsdom: http://localhost:3000
    expect(liveWsUrl("/api")).toBe("ws://localhost:3000/api/ws");
  });

  it("resuelve base absoluta respetando https ⇒ wss", () => {
    expect(liveWsUrl("https://api.takab.example")).toBe("wss://api.takab.example/ws");
    expect(liveWsUrl("http://api.takab.example/v1/")).toBe("ws://api.takab.example/v1/ws");
  });
});
