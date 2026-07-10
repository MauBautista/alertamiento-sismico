// Store de salud viva de la topbar (T-1.49): reducción de frames y staleness.

import { afterEach, describe, expect, it, vi } from "vitest";

import type { ServerFrame, SiteStateFrame } from "@takab/sdk";

import {
  HEARTBEAT_STALE_MS,
  edgeMqttView,
  resetLiveHealthForTests,
  useLiveHealthStore,
} from "./liveHealth.store";

function healthFrame(over: Partial<SiteStateFrame> = {}): ServerFrame {
  return {
    type: "site_state",
    kind: "device_health",
    gateway_id: "gw-1",
    tenant_id: "t-1",
    ts: "2026-07-10T00:00:00Z",
    mqtt_rtt_ms: 72.9,
    ...over,
  } as ServerFrame;
}

afterEach(() => {
  resetLiveHealthForTests();
  vi.useRealTimers();
});

describe("liveHealth.store", () => {
  it("guarda el último heartbeat de device_health por gateway", () => {
    const s = useLiveHealthStore.getState();
    s.applyFrame(healthFrame());
    s.applyFrame(healthFrame({ gateway_id: "gw-2", mqtt_rtt_ms: 12.5 }));
    s.applyFrame(healthFrame({ mqtt_rtt_ms: 80.1 })); // gw-1 otra vez

    const hb = useLiveHealthStore.getState().heartbeats;
    expect(Object.keys(hb).sort()).toEqual(["gw-1", "gw-2"]);
    expect(hb["gw-1"].frame.mqtt_rtt_ms).toBe(80.1);
  });

  it("ignora rule_evaluation y frames que no son site_state", () => {
    const s = useLiveHealthStore.getState();
    s.applyFrame(healthFrame({ kind: "rule_evaluation" }));
    s.applyFrame({ type: "ready" } as ServerFrame);
    expect(useLiveHealthStore.getState().heartbeats).toEqual({});
  });

  it("setStatus refleja las transiciones del canal", () => {
    useLiveHealthStore.getState().setStatus("ready");
    expect(useLiveHealthStore.getState().status).toBe("ready");
    useLiveHealthStore.getState().setStatus("closed");
    expect(useLiveHealthStore.getState().status).toBe("closed");
  });
});

describe("edgeMqttView", () => {
  it("fresco: devuelve el PEOR RTT entre gateways (flota multi-gabinete)", () => {
    vi.useFakeTimers();
    vi.setSystemTime(1_000_000);
    const s = useLiveHealthStore.getState();
    s.applyFrame(healthFrame({ mqtt_rtt_ms: 72.9 }));
    s.applyFrame(healthFrame({ gateway_id: "gw-2", mqtt_rtt_ms: 110.4 }));

    const view = edgeMqttView(useLiveHealthStore.getState().heartbeats, Date.now());
    expect(view).toEqual({ rttMs: 110.4, stale: false });
  });

  it("pasado HEARTBEAT_STALE_MS sin frames ⇒ S/D (jamás congela un número)", () => {
    vi.useFakeTimers();
    vi.setSystemTime(1_000_000);
    useLiveHealthStore.getState().applyFrame(healthFrame());

    const later = Date.now() + HEARTBEAT_STALE_MS + 1;
    expect(edgeMqttView(useLiveHealthStore.getState().heartbeats, later)).toEqual({
      rttMs: null,
      stale: true,
    });
  });

  it("heartbeat fresco SIN rtt medido ⇒ rttMs null (S/D honesto, no 0)", () => {
    vi.useFakeTimers();
    vi.setSystemTime(1_000_000);
    useLiveHealthStore.getState().applyFrame(healthFrame({ mqtt_rtt_ms: null }));
    const view = edgeMqttView(useLiveHealthStore.getState().heartbeats, Date.now());
    expect(view.rttMs).toBeNull();
    expect(view.stale).toBe(false);
  });

  it("sin heartbeats ⇒ stale", () => {
    expect(edgeMqttView({}, Date.now())).toEqual({ rttMs: null, stale: true });
  });
});
