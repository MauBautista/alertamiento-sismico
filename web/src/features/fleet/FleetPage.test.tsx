import { fireEvent, render as rtlRender, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// T-1.59: SiteCard monta useSelfTest (react-query) — todo render lleva provider.
function render(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return rtlRender(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

import { resetSessionStoreForTests } from "../../auth/session.store";
import { ME_FIXTURES } from "../../test-utils/meFixtures";
import { seedAuthenticated } from "../../test-utils/renderRoutes";
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
      row_version: "1",
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
      // expectFourStates renderiza por su cuenta: el provider viaja en el JSX.
      const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      return (
        <QueryClientProvider client={client}>
          <FleetPage />
        </QueryClientProvider>
      );
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

describe("FleetPage · contrato anti-solape (T-1.54)", () => {
  function renderWithAdmin(cabinets: FleetCabinet[]) {
    // FleetAdmin solo monta con manage_fleet y usa react-query (useSites).
    resetSessionStoreForTests();
    seedAuthenticated(ME_FIXTURES.tenant_admin);
    mocks.useFleet.mockReturnValue(fleetData({ cabinets }));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(
      <QueryClientProvider client={client}>
        <FleetPage />
      </QueryClientProvider>,
    );
  }

  it("con 21 gabinetes: el grid fluye ANTES de la sección admin y el frame no usa .soc-wall", () => {
    const cabinets = Array.from({ length: 21 }, (_, i) =>
      cabinet(`g-${String(i).padStart(2, "0")}`, i === 0 ? "OPERATIVO" : "SIN ENLACE"),
    );
    const { container } = renderWithAdmin(cabinets);
    const grid = container.querySelector(".fleet__grid");
    const admin = container.querySelector(".fleet__admin");
    expect(grid).not.toBeNull();
    expect(admin).not.toBeNull();
    // orden de flujo del documento: primero las tarjetas, después la admin
    expect(grid!.compareDocumentPosition(admin!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // la clase de layout del wall es EXCLUSIVA de la consola
    expect(container.querySelector(".soc-stateframe.soc-wall")).toBeNull();
  });

  it("flota de 1 (post-purga): KPIs 1/1/0/0 y una sola tarjeta", () => {
    const { container } = renderWithAdmin([cabinet("g-1", "OPERATIVO")]);
    const kpis = screen.getAllByTestId("fleet-kpi").map((el) => el.textContent);
    expect(kpis).toEqual(["1GABINETES", "1OPERATIVOS", "0DEGRADADOS", "0SIN ENLACE"]);
    expect(container.querySelectorAll(".fleet-card")).toHaveLength(1);
  });
});
