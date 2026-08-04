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

const mocks = vi.hoisted(() => ({
  useFleet: vi.fn(),
  useFleetSyncStates: vi.fn(),
  useFleetHealth: vi.fn(),
  useRetireCodeConfigured: vi.fn(),
  updateMutate: vi.fn(),
  retireMutate: vi.fn(),
  restoreMutate: vi.fn(),
}));

vi.mock("./useFleet", () => ({
  useFleet: mocks.useFleet,
  FLEET_STALE_MS: 90_000,
}));

const idleMutation = (mutate: ReturnType<typeof vi.fn>) => ({
  mutate,
  isPending: false,
  error: null,
  reset: vi.fn(),
});

vi.mock("./useFleetMutations", () => ({
  useFleetSyncStates: (...args: unknown[]) => mocks.useFleetSyncStates(...args),
  useFleetHealth: (...args: unknown[]) => mocks.useFleetHealth(...args),
  useRetireCodeConfigured: (...args: unknown[]) => mocks.useRetireCodeConfigured(...args),
  useUpdateGateway: () => idleMutation(mocks.updateMutate),
  useRetireGateway: () => idleMutation(mocks.retireMutate),
  useRestoreGateway: () => idleMutation(mocks.restoreMutate),
}));

// FleetAdmin tiene su propia suite y aquí solo estorba (monta /sites, formularios y
// mutaciones). Se sustituye por un marcador que CONSERVA su elemento y su clase: el
// contrato anti-solape de T-1.54 comprueba el orden de flujo entre la reja y esta
// sección, y un stub vacío lo habría desactivado en silencio.
vi.mock("./FleetAdmin", () => ({
  default: () => <section className="fleet__admin" data-testid="fleet-admin" />,
}));

function cabinet(id: string, state: string): FleetCabinet {
  return {
    gateway: {
      gateway_id: id,
      site_id: `s-${id}`,
      site_name: `Sitio ${id}`,
      site_code: `C-${id}`,
      site_status: "active",
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
    siteCode: `C-${id}`,
    siteStatus: "active",
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
    resetSessionStoreForTests();
    vi.clearAllMocks();
    mocks.useFleetSyncStates.mockReturnValue(new Map());
    mocks.useFleetHealth.mockReturnValue(new Map());
    mocks.useRetireCodeConfigured.mockReturnValue(true);
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

// [T-2.37] El CRUD del gabinete: hasta aquí la consola no podía editar ni retirar un
// gabinete pese a que la API lo permitía desde T-1.32.
describe("FleetPage · administración del gabinete [T-2.37]", () => {
  beforeEach(() => {
    resetSessionStoreForTests();
    vi.clearAllMocks();
    mocks.useFleetSyncStates.mockReturnValue(new Map());
    mocks.useFleetHealth.mockReturnValue(new Map());
    mocks.useRetireCodeConfigured.mockReturnValue(true);
    mocks.useFleet.mockReturnValue(fleetData({ cabinets: [cabinet("1", "OPERATIVO")] }));
  });

  it("sin manage_fleet no hay acciones de administración ni toggle", () => {
    seedAuthenticated(ME_FIXTURES.soc_operator);
    render(<FleetPage />);
    expect(screen.queryByTestId("card-admin")).not.toBeInTheDocument();
    expect(screen.queryByTestId("fleet-include-retired")).not.toBeInTheDocument();
  });

  it("con manage_fleet ofrece editar y retirar", () => {
    seedAuthenticated(ME_FIXTURES.takab_superadmin);
    render(<FleetPage />);
    expect(screen.getByRole("button", { name: "EDITAR GABINETE" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "RETIRAR" })).toBeInTheDocument();
  });

  it("EDITAR abre el formulario con el gabinete precargado", () => {
    seedAuthenticated(ME_FIXTURES.takab_superadmin);
    render(<FleetPage />);
    fireEvent.click(screen.getByRole("button", { name: "EDITAR GABINETE" }));
    expect(screen.getByTestId("gateway-form")).toBeInTheDocument();
    expect(screen.getByLabelText(/SERIAL/)).toHaveValue("TKB-1");
  });

  it("guardar manda base_row_version: la carrera se resuelve con 409, no pisando", () => {
    seedAuthenticated(ME_FIXTURES.takab_superadmin);
    render(<FleetPage />);
    fireEvent.click(screen.getByRole("button", { name: "EDITAR GABINETE" }));
    fireEvent.click(screen.getByRole("button", { name: /GUARDAR GABINETE/ }));
    expect(mocks.updateMutate.mock.calls[0][0].body.base_row_version).toBe("1");
  });

  it("RETIRAR abre el diálogo de doble fricción, no retira de un clic", () => {
    seedAuthenticated(ME_FIXTURES.takab_superadmin);
    render(<FleetPage />);
    fireEvent.click(screen.getByRole("button", { name: "RETIRAR" }));
    expect(screen.getByTestId("retire-dialog")).toBeInTheDocument();
    expect(mocks.retireMutate).not.toHaveBeenCalled();
  });

  it("el toggle VER RETIRADOS se lo pide al hook, no filtra en cliente", () => {
    seedAuthenticated(ME_FIXTURES.takab_superadmin);
    render(<FleetPage />);
    fireEvent.click(screen.getByRole("checkbox", { name: /VER RETIRADOS/ }));
    expect(mocks.useFleet).toHaveBeenLastCalledWith({ includeRetired: true });
  });

  it("un gabinete retirado se rotula y ofrece RESTAURAR en vez de retirar", () => {
    seedAuthenticated(ME_FIXTURES.takab_superadmin);
    const retired = cabinet("9", "SIN ENLACE");
    retired.gateway.status = "retired";
    mocks.useFleet.mockReturnValue(fleetData({ cabinets: [retired] }));
    render(<FleetPage />);
    expect(screen.getByTestId("card-retired")).toHaveTextContent("RETIRADO");
    expect(screen.getByRole("button", { name: "RESTAURAR" })).toBeInTheDocument();
    expect(screen.queryByTestId("card-admin")).not.toBeInTheDocument();
  });

  it("el estado del config firmado se pinta por gabinete", () => {
    seedAuthenticated(ME_FIXTURES.takab_superadmin);
    mocks.useFleetSyncStates.mockReturnValue(
      new Map([
        [
          "1",
          {
            gateway_id: "1",
            version: 12,
            published_at: null,
            sig_fingerprint: null,
            in_sync: true,
            has_edge_config: true,
            is_syncable: true,
          },
        ],
      ]),
    );
    render(<FleetPage />);
    expect(screen.getByTestId("sync-badge")).toHaveTextContent("SINCRONIZADO v12");
  });
});

// [T-2.38] Buscar, ordenar y filtrar sin que los KPI mientan.
describe("FleetPage · barra de herramientas [T-2.38]", () => {
  beforeEach(() => {
    resetSessionStoreForTests();
    vi.clearAllMocks();
    mocks.useFleetSyncStates.mockReturnValue(new Map());
    mocks.useFleetHealth.mockReturnValue(new Map());
    mocks.useRetireCodeConfigured.mockReturnValue(true);
    seedAuthenticated(ME_FIXTURES.takab_superadmin);
    const ok = cabinet("1", "OPERATIVO");
    ok.siteName = "Torre Norte";
    const dead = cabinet("2", "SIN ENLACE");
    dead.siteName = "Almacén";
    mocks.useFleet.mockReturnValue(fleetData({ cabinets: [ok, dead] }));
  });

  it("la búsqueda filtra la reja", () => {
    render(<FleetPage />);
    fireEvent.change(screen.getByLabelText("Buscar en la flota"), {
      target: { value: "torre" },
    });
    expect(screen.getAllByTestId("sync-badge")).toHaveLength(1);
  });

  // El invariante que importa: filtrar no puede reescribir los contadores.
  it("filtrar NO cambia los KPI y la leyenda dice cuántos de cuántos", () => {
    render(<FleetPage />);
    fireEvent.change(screen.getByLabelText("Buscar en la flota"), {
      target: { value: "torre" },
    });
    const kpis = screen.getAllByTestId("fleet-kpi").map((k) => k.textContent);
    expect(kpis[0]).toContain("2"); // GABINETES sigue diciendo 2
    expect(screen.getByTestId("fleet-shown")).toHaveTextContent("MOSTRANDO 1 DE 2");
  });

  it("sin filtro activo no se pinta la leyenda", () => {
    render(<FleetPage />);
    expect(screen.queryByTestId("fleet-shown")).not.toBeInTheDocument();
  });

  it("OCULTAR SIN ENLACE deja fuera al caído", () => {
    render(<FleetPage />);
    fireEvent.click(screen.getByRole("checkbox", { name: /OCULTAR SIN ENLACE/ }));
    expect(screen.getAllByTestId("sync-badge")).toHaveLength(1);
  });

  // "No hay gabinetes" y "no hay resultados" exigen acciones distintas del operador.
  it("el vacío POR FILTRO se distingue del vacío por flota sin gabinetes", () => {
    render(<FleetPage />);
    fireEvent.change(screen.getByLabelText("Buscar en la flota"), {
      target: { value: "zzz" },
    });
    expect(screen.getByText("SIN RESULTADOS PARA EL FILTRO")).toBeInTheDocument();
  });

  it("la historia de 24 h se pinta por gabinete cuando existe", () => {
    mocks.useFleetHealth.mockReturnValue(
      new Map([
        [
          "1",
          {
            gateway_id: "1",
            buckets: [
              { ts: "2026-08-03T09:00:00Z", heartbeats: 60, mqtt_rtt_p95_ms: 40 },
              { ts: "2026-08-03T10:00:00Z", heartbeats: 60, mqtt_rtt_p95_ms: 55 },
            ],
            outages: 2,
            downtime_s: 1800,
            last_outage_end: "2026-08-03T09:30:00Z",
            heartbeat_completeness: 0.92,
          },
        ],
      ]),
    );
    render(<FleetPage />);
    const history = screen.getAllByTestId("card-history")[0];
    expect(history).toHaveTextContent("CAÍDAS 24 H: 2");
    expect(history).toHaveTextContent("30 min sin enlace");
    expect(history).toHaveTextContent("LATIDOS 92%");
  });

  it("sin historia no se inventa una tarjeta vacía", () => {
    render(<FleetPage />);
    expect(screen.queryByTestId("card-history")).not.toBeInTheDocument();
  });
});
