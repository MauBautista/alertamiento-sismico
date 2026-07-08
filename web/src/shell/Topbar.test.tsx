import { fireEvent, render, screen, within } from "@testing-library/react";
import { act } from "react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { MeResponse } from "../auth/me";
import { resetSessionStoreForTests, useSessionStore } from "../auth/session.store";
import { ME_FIXTURES, WEB_ROLES } from "../test-utils/meFixtures";
import Topbar from "./Topbar";

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

describe("Topbar", () => {
  beforeEach(() => {
    resetSessionStoreForTests();
  });

  afterEach(() => {
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

  it('pills de estado en "SIN DATOS" explícito (sin heartbeat todavía)', () => {
    seed(ME_FIXTURES.soc_operator);
    renderTopbar();
    expect(screen.getAllByText(/SIN DATOS/)).toHaveLength(2);
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

  it("el botón de logout dispara logout() del store", () => {
    seed(ME_FIXTURES.soc_operator);
    const logout = vi.fn().mockResolvedValue(undefined);
    useSessionStore.setState({ logout });
    renderTopbar();
    fireEvent.click(screen.getByRole("button", { name: "Cerrar sesión" }));
    expect(logout).toHaveBeenCalledTimes(1);
  });
});
