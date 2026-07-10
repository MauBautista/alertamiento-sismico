import { fireEvent, render, screen, within } from "@testing-library/react";
import { act } from "react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ServerFrame } from "@takab/sdk";

import type { MeResponse } from "../auth/me";
import { resetSessionStoreForTests, useSessionStore } from "../auth/session.store";
import { resetLiveHealthForTests, useLiveHealthStore } from "../live/liveHealth.store";
import { ME_FIXTURES, WEB_ROLES } from "../test-utils/meFixtures";
import Topbar from "./Topbar";

// OperatorMenu usa TanStack Query vía useProfile: aquí se mockea el módulo
// (la topbar solo necesita el nombre resuelto; el flujo de guardado se prueba
// en OperatorMenu.test).
const profileMocks = vi.hoisted(() => ({
  useProfile: vi.fn(),
  useProfileMutation: vi.fn(),
}));
vi.mock("../auth/useProfile", () => profileMocks);

const TAB_LABELS: Record<string, string> = {
  "/console": "CONSOLA C4I",
  "/fleet": "FLOTA EDGE",
  "/triage": "TRIAGE",
  "/tenants": "MULTI-TENANT",
};

function seed(me: MeResponse): void {
  useSessionStore.setState({ status: "authenticated", origin: "dev", idToken: "t", me });
}

function renderTopbar(initialPath = "/console") {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Topbar />
    </MemoryRouter>,
  );
}

function healthFrame(rtt: number | null): ServerFrame {
  return {
    type: "site_state",
    kind: "device_health",
    gateway_id: "gw-dev-0001",
    tenant_id: "t-1",
    ts: "2026-07-10T00:00:00Z",
    mqtt_rtt_ms: rtt,
  } as ServerFrame;
}

describe("Topbar", () => {
  beforeEach(() => {
    resetSessionStoreForTests();
    resetLiveHealthForTests();
    profileMocks.useProfile.mockReturnValue({ data: undefined });
    profileMocks.useProfileMutation.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      isError: false,
    });
  });

  afterEach(() => {
    resetLiveHealthForTests();
    vi.useRealTimers();
  });

  it.each(WEB_ROLES.map((role) => [role] as const))(
    "tabs exactas para %s en el orden del server",
    (role) => {
      seed(ME_FIXTURES[role]);
      renderTopbar();
      const nav = screen.getByRole("navigation", { name: "Primary" });
      const labels = within(nav)
        .getAllByRole("link")
        .map((el) => el.textContent);
      const expected = ME_FIXTURES[role].allowed_routes
        .filter((route) => route !== "/building")
        .map((route) => TAB_LABELS[route]);
      expect(labels).toEqual(expected);
    },
  );

  it("marca el tab activo con aria-current=page", () => {
    seed(ME_FIXTURES.soc_operator);
    renderTopbar("/console");
    expect(screen.getByRole("link", { name: "CONSOLA C4I" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("link", { name: "FLOTA EDGE" })).not.toHaveAttribute("aria-current");
  });

  it("arranque honesto: DESCONECTADO + EDGE·MQTT·S/D (canal cerrado, sin heartbeat)", () => {
    seed(ME_FIXTURES.soc_operator);
    renderTopbar();
    expect(screen.getByTestId("system-pill")).toHaveTextContent("DESCONECTADO");
    expect(screen.getByTestId("mqtt-pill")).toHaveTextContent("EDGE · MQTT · S/D");
  });

  it("canal ready ⇒ CONECTADO; connecting ⇒ CONECTANDO…", () => {
    seed(ME_FIXTURES.soc_operator);
    renderTopbar();
    act(() => {
      useLiveHealthStore.getState().setStatus("connecting");
    });
    expect(screen.getByTestId("system-pill")).toHaveTextContent("CONECTANDO…");
    act(() => {
      useLiveHealthStore.getState().setStatus("ready");
    });
    expect(screen.getByTestId("system-pill")).toHaveTextContent("CONECTADO");
  });

  it("heartbeat fresco ⇒ RTT real; 90 s sin frames ⇒ vuelve a S/D (no congela)", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-07-10T00:00:00Z"));
    seed(ME_FIXTURES.soc_operator);
    renderTopbar();

    act(() => {
      useLiveHealthStore.getState().applyFrame(healthFrame(72.9));
    });
    expect(screen.getByTestId("mqtt-pill")).toHaveTextContent("EDGE · MQTT 72.90 ms");

    act(() => {
      vi.advanceTimersByTime(95_000); // > HEARTBEAT_STALE_MS; el tick de useNow re-evalúa
    });
    expect(screen.getByTestId("mqtt-pill")).toHaveTextContent("EDGE · MQTT · S/D");
  });

  it("reloj UTC/CST con tick de 1 s", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-07-07T12:00:00Z"));
    seed(ME_FIXTURES.soc_operator);
    renderTopbar();
    expect(screen.getByText("12:00:00")).toBeInTheDocument();
    expect(screen.getByText("06:00:00")).toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(screen.getByText("12:00:01")).toBeInTheDocument();
  });

  it("zona de usuario: nombre del perfil si existe; logout vive en el menú", () => {
    profileMocks.useProfile.mockReturnValue({
      data: { user_sub: "u", display_name: "M. Rodríguez", updated_at: null },
    });
    seed(ME_FIXTURES.soc_operator);
    const logout = vi.fn().mockResolvedValue(undefined);
    useSessionStore.setState({ logout });
    renderTopbar();

    const trigger = screen.getByRole("button", { expanded: false });
    expect(trigger).toHaveTextContent("M. Rodríguez");
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole("button", { name: /Cerrar sesión/ }));
    expect(logout).toHaveBeenCalledTimes(1);
  });
});
