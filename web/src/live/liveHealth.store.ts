// Estado vivo del sistema para la topbar (T-1.49).
//
// UNA suscripción (la del provider) alimenta este store; la topbar lo lee en
// todas las páginas. Guarda el ÚLTIMO heartbeat de device_health por gateway
// con su hora de llegada (reloj de pared): pasado HEARTBEAT_STALE_MS sin frame
// el dato se declara S/D — jamás se congela un número viejo como fresco
// (regla de oro 7).

import { create } from "zustand";

import type { ServerFrame, SiteStateFrame } from "@takab/sdk";

import type { LiveStatus } from "../lib/ws";

/** Heartbeat del edge cada 60 s ⇒ 90 s sin frame = enlace/salud sospechosos. */
export const HEARTBEAT_STALE_MS = 90_000;

export interface Heartbeat {
  frame: SiteStateFrame;
  /** Llegada local (epoch ms) — la staleness se mide contra ESTO, no contra ts. */
  at: number;
}

interface LiveHealthState {
  status: LiveStatus;
  heartbeats: Record<string, Heartbeat>;
  setStatus: (status: LiveStatus) => void;
  applyFrame: (frame: ServerFrame) => void;
}

export const useLiveHealthStore = create<LiveHealthState>()((set) => ({
  status: "closed",
  heartbeats: {},
  setStatus: (status) => set({ status }),
  applyFrame: (frame) => {
    if (frame.type !== "site_state" || frame.kind !== "device_health") {
      return; // rule_evaluation y demás frames no son salud del enlace
    }
    const gatewayId = frame.gateway_id;
    if (!gatewayId) {
      return;
    }
    set((s) => ({
      heartbeats: { ...s.heartbeats, [gatewayId]: { frame, at: Date.now() } },
    }));
  },
}));

export interface EdgeMqttView {
  /** Peor RTT (ms) entre gateways con heartbeat fresco; null = S/D. */
  rttMs: number | null;
  /** true ⇒ ningún heartbeat fresco: la topbar pinta S/D. */
  stale: boolean;
}

/** Vista de la pill "EDGE · MQTT": función pura para testear staleness sin UI. */
export function edgeMqttView(heartbeats: Record<string, Heartbeat>, nowMs: number): EdgeMqttView {
  let worst: number | null = null;
  let anyFresh = false;
  for (const hb of Object.values(heartbeats)) {
    if (nowMs - hb.at > HEARTBEAT_STALE_MS) {
      continue;
    }
    anyFresh = true;
    const rtt = hb.frame.mqtt_rtt_ms;
    if (typeof rtt === "number" && (worst === null || rtt > worst)) {
      worst = rtt;
    }
  }
  return { rttMs: anyFresh ? worst : null, stale: !anyFresh };
}

/** Solo tests: estado limpio entre casos. */
export function resetLiveHealthForTests(): void {
  useLiveHealthStore.setState({ status: "closed", heartbeats: {} });
}
