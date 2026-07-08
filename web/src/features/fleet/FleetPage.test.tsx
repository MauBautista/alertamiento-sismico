import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { expectFourStates } from "../../test-utils/states";
import FleetPage from "./FleetPage";
import type { FleetCabinet, FleetData } from "./useFleet";

const mocks = vi.hoisted(() => ({ useFleet: vi.fn() }));

vi.mock("./useFleet", () => ({
  useFleet: mocks.useFleet,
  FLEET_STALE_MS: 90_000,
}));

function cabinet(id: string, state: string): FleetCabinet {
  return {
    gateway: {
      gateway_id: id,
      site_id: `s-${id}`,
      serial: `TKB-${id}`,
      fw_version: "edge-1.4.0",
      iot_thing: null,
      status: "active",
      has_wr1: true,
      installed_at: null,
      derived_state: state,
      last_heartbeat_ts: null,
      power_status: "line",
      battery_pct: 100,
      cert_days_remaining: null,
      mqtt_rtt_ms: 1.2,
      seedlink_lag_s: 0.2,
      ntp_offset_ms: null,
    },
    siteName: `Sitio ${id}`,
    siteCode: null,
    relays: null,
  };
}

function fleetData(over: Partial<FleetData> = {}): FleetData {
  return {
    cabinets: [],
    loading: false,
    error: null,
    dataUpdatedAt: Date.now(),
    refetch: vi.fn(),
    ...over,
  };
}

describe("FleetPage", () => {
  beforeEach(() => {
    mocks.useFleet.mockReset();
  });

  it("materializa los 4 estados obligatorios (regla de oro 7)", () => {
    expectFourStates((state) => {
      mocks.useFleet.mockReturnValue(
        fleetData({
          loading: state === "loading",
          error: state === "error" ? "GET /fleet/gateways falló (503)" : null,
          cabinets: state === "stale" ? [cabinet("1", "OPERATIVO")] : [],
          dataUpdatedAt: state === "stale" ? Date.now() - 100_000 : Date.now(),
        }),
      );
      return <FleetPage />;
    });
  });

  it("KPIs cuentan por derived_state del servidor, sin recalcular umbrales", () => {
    mocks.useFleet.mockReturnValue(
      fleetData({
        cabinets: [
          cabinet("1", "OPERATIVO"),
          cabinet("2", "OPERATIVO"),
          cabinet("3", "DEGRADADO"),
          cabinet("4", "SIN ENLACE"),
        ],
      }),
    );
    render(<FleetPage />);
    const kpis = screen.getAllByTestId("fleet-kpi").map((el) => el.textContent);
    expect(kpis).toEqual(["4GABINETES", "2OPERATIVOS", "1DEGRADADOS", "1SIN ENLACE"]);
  });

  it("pinta una tarjeta por gabinete", () => {
    mocks.useFleet.mockReturnValue(
      fleetData({ cabinets: [cabinet("1", "OPERATIVO"), cabinet("2", "DEGRADADO")] }),
    );
    render(<FleetPage />);
    expect(screen.getByText("Sitio 1")).toBeInTheDocument();
    expect(screen.getByText("Sitio 2")).toBeInTheDocument();
  });

  it("REINTENTAR dispara refetch", () => {
    const data = fleetData({ error: "GET /fleet/gateways falló (503)" });
    mocks.useFleet.mockReturnValue(data);
    render(<FleetPage />);
    fireEvent.click(screen.getByRole("button", { name: "REINTENTAR" }));
    expect(data.refetch).toHaveBeenCalledTimes(1);
  });

  it("flota vacía muestra el empty propio", () => {
    mocks.useFleet.mockReturnValue(fleetData());
    render(<FleetPage />);
    expect(screen.getByText("SIN GABINETES REGISTRADOS EN EL TENANT")).toBeInTheDocument();
  });

  it("dato fresco no muestra banner de retención", () => {
    mocks.useFleet.mockReturnValue(fleetData({ cabinets: [cabinet("1", "OPERATIVO")] }));
    render(<FleetPage />);
    expect(screen.queryByText(/DATOS RETENIDOS/)).toBeNull();
  });
});
