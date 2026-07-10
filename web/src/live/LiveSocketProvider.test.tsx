// Provider del socket del shell (T-1.49): vida atada a la sesión, factory
// inyectable para tests y cableado al store de salud.

import { render, screen } from "@testing-library/react";
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { TOPIC_SITE_STATE, type ServerFrame } from "@takab/sdk";

import { resetSessionStoreForTests, useSessionStore } from "../auth/session.store";
import { FakeLiveSocket } from "../test-utils/liveSocket";
import LiveSocketProvider from "./LiveSocketProvider";
import { resetLiveHealthForTests, useLiveHealthStore } from "./liveHealth.store";
import { LiveSocketFactoryContext, useLiveSocket } from "./socket";

function Probe() {
  const socket = useLiveSocket();
  return <span data-testid="probe">{socket === null ? "sin-socket" : "con-socket"}</span>;
}

function renderProvider(socket: FakeLiveSocket) {
  return render(
    <LiveSocketFactoryContext.Provider value={() => socket}>
      <LiveSocketProvider>
        <Probe />
      </LiveSocketProvider>
    </LiveSocketFactoryContext.Provider>,
  );
}

beforeEach(() => {
  resetSessionStoreForTests();
  resetLiveHealthForTests();
});

afterEach(() => {
  resetLiveHealthForTests();
});

describe("LiveSocketProvider", () => {
  it("sin idToken NO conecta; con sesión conecta y cierra al desmontar", () => {
    const socket = new FakeLiveSocket();
    const view = renderProvider(socket);
    expect(socket.connectCalls).toBe(0);

    act(() => {
      useSessionStore.setState({ status: "authenticated", idToken: "tok" });
    });
    expect(socket.connectCalls).toBe(1);

    view.unmount();
    expect(socket.closeCalls).toBeGreaterThanOrEqual(1);
  });

  it("provee el socket por contexto a los hooks consumidores", () => {
    renderProvider(new FakeLiveSocket());
    expect(screen.getByTestId("probe")).toHaveTextContent("con-socket");
  });

  it("cablea status y heartbeats de site_state al store de salud", () => {
    const socket = new FakeLiveSocket();
    renderProvider(socket);

    act(() => {
      socket.setStatus("connecting");
    });
    expect(useLiveHealthStore.getState().status).toBe("connecting");

    act(() => {
      socket.emit(TOPIC_SITE_STATE, {
        type: "site_state",
        kind: "device_health",
        gateway_id: "gw-1",
        tenant_id: "t-1",
        ts: "2026-07-10T00:00:00Z",
        mqtt_rtt_ms: 72.9,
      } as ServerFrame);
    });
    expect(useLiveHealthStore.getState().heartbeats["gw-1"]).toBeDefined();
  });

  it("al cerrar sesión (idToken → null) cierra el socket", () => {
    const socket = new FakeLiveSocket();
    renderProvider(socket);
    act(() => {
      useSessionStore.setState({ status: "authenticated", idToken: "tok" });
    });
    expect(socket.connectCalls).toBe(1);
    act(() => {
      useSessionStore.setState({ status: "anonymous", idToken: null });
    });
    expect(socket.closeCalls).toBeGreaterThanOrEqual(1);
  });
});
