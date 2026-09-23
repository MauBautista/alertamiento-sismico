// Provider del socket del shell (T-1.49): vida atada a la sesión, factory
// inyectable para tests y cableado al store de salud.

import { render, screen } from "@testing-library/react";
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TOPIC_SITE_STATE, type LiveSocketOptions, type ServerFrame } from "@takab/sdk";

// [T-8.03] Sin fábrica inyectada el provider construye el LiveSocket REAL; aquí
// se sustituye por uno que solo recuerda las opciones, para ver QUÉ le pasa el
// provider ante un 4401 (renovar) y un 4440 (tope de sesión).
const ws = vi.hoisted(() => ({ opciones: [] as unknown[] }));
vi.mock("../lib/ws", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/ws")>();
  class LiveSocketEspia {
    status = "closed" as const;
    constructor(options: unknown) {
      ws.opciones.push(options);
    }
    connect(): void {}
    close(): void {}
    subscribe(): () => void {
      return () => undefined;
    }
    lastFrameAt(): number | null {
      return null;
    }
    onStatus(): () => void {
      return () => undefined;
    }
  }
  return { ...actual, LiveSocket: LiveSocketEspia };
});

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

describe("[T-8.03] el canal live renueva el token en vez de cerrar la sesión", () => {
  function opcionesDelSocketReal(): LiveSocketOptions {
    ws.opciones.length = 0;
    render(
      <LiveSocketProvider>
        <Probe />
      </LiveSocketProvider>,
    );
    expect(ws.opciones).toHaveLength(1);
    return ws.opciones[0] as LiveSocketOptions;
  }

  it("ante un 4401 el socket puede renovar: delega en la renovación de vuelo único del store", async () => {
    const renewToken = vi.fn().mockResolvedValue("tok-nuevo");
    useSessionStore.setState({ renewToken });

    const opciones = opcionesDelSocketReal();

    expect(opciones.renewToken).toBeTypeOf("function");
    await expect(opciones.renewToken?.()).resolves.toBe("tok-nuevo");
    expect(renewToken).toHaveBeenCalledTimes(1);
  });

  it("4440 (tope de la sesión) ⇒ fin con causa 'max_age'", () => {
    const handleUnauthorized = vi.fn();
    const logout = vi.fn();
    useSessionStore.setState({ handleUnauthorized, logout });

    opcionesDelSocketReal().onUnauthorized("max_age");

    expect(handleUnauthorized).toHaveBeenCalledWith("max_age");
    expect(logout).not.toHaveBeenCalled();
  });

  it("4401 sin renovación posible ⇒ fin 'expired' CON causa (antes era un logout mudo)", () => {
    // Antes: `logout()` — borraba la causa (`endedReason: null`) y mandaba al
    // /logout del Hosted UI, así que el operador aparecía en un login idéntico
    // al de un arranque en frío. Es el silencio que T-6.07 cerró para el REST.
    const handleUnauthorized = vi.fn();
    const logout = vi.fn();
    useSessionStore.setState({ handleUnauthorized, logout });

    const opciones = opcionesDelSocketReal();
    opciones.onUnauthorized("expired");
    opciones.onUnauthorized();

    expect(handleUnauthorized).toHaveBeenNthCalledWith(1, "expired");
    expect(handleUnauthorized).toHaveBeenNthCalledWith(2, "expired");
    expect(logout).not.toHaveBeenCalled();
  });

  it("el token se lee EN CADA conexión (el renovado, no el del primer handshake)", () => {
    useSessionStore.setState({ idToken: "t1" });
    const opciones = opcionesDelSocketReal();
    act(() => {
      useSessionStore.setState({ idToken: "t2" });
    });
    expect(opciones.getToken()).toBe("t2");
  });
});
