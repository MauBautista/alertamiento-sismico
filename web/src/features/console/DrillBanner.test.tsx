// DrillBanner (T-1.60): rotulado NO-real, precedencia de la alerta y gates.

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ useActiveDrill: vi.fn() }));
vi.mock("./useActiveDrill", () => ({ useActiveDrill: mocks.useActiveDrill }));

import { resetSessionStoreForTests, useSessionStore } from "../../auth/session.store";
import { ME_FIXTURES } from "../../test-utils/meFixtures";
import DrillBanner from "./DrillBanner";
import type { ActiveDrillData } from "./useActiveDrill";

function drillData(over: Partial<ActiveDrillData> = {}): ActiveDrillData {
  return {
    drill: null,
    loading: false,
    start: vi.fn(),
    stop: vi.fn(),
    pending: false,
    error: null,
    ...over,
  };
}

const DRILL = {
  drill_id: "d-1",
  tenant_id: "t-1",
  initiated_by: "u-1",
  note: null,
  duration_s: 300,
  scheduled_at: null,
  started_at: "2026-07-12T18:00:00Z",
  stopped_at: null,
  stop_reason: null,
  active: true,
  sites: [
    {
      site_id: "s-1",
      site_name: "Sitio Dev",
      command_id: "c-1",
      command_status: "acked",
      ack: null,
    },
  ],
};

beforeEach(() => {
  resetSessionStoreForTests();
  vi.clearAllMocks();
});

describe("DrillBanner", () => {
  it("con drill activo pinta el banner rotulado NO-real", () => {
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.soc_operator });
    mocks.useActiveDrill.mockReturnValue(drillData({ drill: DRILL }));
    render(<DrillBanner hasLiveIncident={false} />);
    const banner = screen.getByTestId("drill-banner");
    expect(banner).toHaveTextContent("SIMULACRO EN CURSO — ESTO NO ES UNA ALERTA REAL");
    expect(banner).toHaveTextContent("1 SITIO(S)");
    // soc_operator no puede terminarlo (gate drill_start).
    expect(screen.queryByRole("button", { name: "TERMINAR" })).toBeNull();
  });

  it("con incidente VIVO el banner se degrada a badge: lo real domina", () => {
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.tenant_admin });
    mocks.useActiveDrill.mockReturnValue(drillData({ drill: DRILL }));
    render(<DrillBanner hasLiveIncident={true} />);
    expect(screen.getByTestId("drill-badge")).toHaveTextContent("LA ALERTA REAL DOMINA");
    expect(screen.queryByTestId("drill-banner")).toBeNull();
  });

  it("sin drill: solo quien tiene drill_start ve el botón de iniciar", () => {
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.soc_operator });
    mocks.useActiveDrill.mockReturnValue(drillData());
    const { unmount } = render(<DrillBanner hasLiveIncident={false} />);
    expect(screen.queryByTestId("drill-idle")).toBeNull();
    unmount();

    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.tenant_admin });
    const start = vi.fn();
    mocks.useActiveDrill.mockReturnValue(drillData({ start }));
    render(<DrillBanner hasLiveIncident={false} />);
    fireEvent.click(screen.getByRole("button", { name: /INICIAR SIMULACRO/ }));
    expect(start).toHaveBeenCalledWith(300);
  });

  it("tenant_admin puede TERMINAR el drill activo", () => {
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.tenant_admin });
    const stop = vi.fn();
    mocks.useActiveDrill.mockReturnValue(drillData({ drill: DRILL, stop }));
    render(<DrillBanner hasLiveIncident={false} />);
    fireEvent.click(screen.getByRole("button", { name: "TERMINAR" }));
    expect(stop).toHaveBeenCalledWith("d-1");
  });
});
