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
import type { MaintenanceData } from "../console/useMaintenanceWindows";
import type { FleetCabinet, FleetData } from "./useFleet";

const mocks = vi.hoisted(() => ({
  useFleet: vi.fn(),
  useFleetSyncStates: vi.fn(),
  useFleetHealth: vi.fn(),
  useRetireCodeConfigured: vi.fn(),
  useMaintenanceWindows: vi.fn(),
  updateMutate: vi.fn(),
  retireMutate: vi.fn(),
  restoreMutate: vi.fn(),
}));

vi.mock("./useFleet", () => ({
  useFleet: mocks.useFleet,
  FLEET_STALE_MS: 90_000,
}));

// [C3] Hasta aquí esta suite NO mockeaba las ventanas: el hook real salía a la
// red desde jsdom en cada test. Con el doble se puede escribir el caso que
// importa —la lectura FALLA— y de paso la suite deja de depender de un fetch.
vi.mock("../console/useMaintenanceWindows", () => ({
  useMaintenanceWindows: (...args: unknown[]) => mocks.useMaintenanceWindows(...args),
  MAINTENANCE_POLL_MS: 30_000,
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
      // [T-2.69] SHA de 7 hex: el único formato que produce `deploy/edge/deploy.sh`.
      fw_version: "62f3f1e",
      version_state: "AL DÍA",
      releases_behind: 0,
      release_age_s: 7200,
      version_age_s: 42,
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

function maintData(over: Partial<MaintenanceData> = {}): MaintenanceData {
  return {
    items: [],
    loading: false,
    readError: null,
    updatedAt: Date.now(),
    refetch: vi.fn(),
    close: vi.fn(),
    open: vi.fn(),
    pending: false,
    openPending: false,
    error: null,
    openError: null,
    ...over,
  };
}

// Raíz, no dentro de un `describe`: hay tres bloques en este archivo y solo dos
// tienen `beforeEach`. Un doble sin valor por defecto devolvería `undefined` y
// la página reventaría en el bloque que no lo prepara.
beforeEach(() => {
  mocks.useMaintenanceWindows.mockReturnValue(maintData());
});

// --- [C3] El fallo de lectura de ventanas no se puede TRAGAR -----------------
//
// `FleetPage` tomaba `useMaintenanceWindows(...)` y usaba SOLO `items`. Con la
// llamada fallando `items` es `[]`, ninguna tarjeta lleva rótulo y la pantalla
// dice, sin decirlo, "aquí no hay ninguna ventana abierta" — que es el cero
// tranquilizador que cerró T-2.59, reproducido tres tareas después en la
// pantalla que este mismo lote acababa de tocar.
//
// Lo que se pierde es concreto: un gabinete puede estar con las alarmas mudas y
// su tarjeta se ve exactamente igual que la de uno vigilado.
describe("FleetPage · ventanas de mantenimiento ilegibles [C3]", () => {
  beforeEach(() => {
    resetSessionStoreForTests();
    mocks.useFleetSyncStates.mockReturnValue(new Map());
    mocks.useFleetHealth.mockReturnValue(new Map());
    mocks.useRetireCodeConfigured.mockReturnValue(true);
    mocks.useFleet.mockReturnValue(fleetData({ cabinets: [cabinet("1", "OPERATIVO")] }));
  });

  it("declara que NO pudo leerlas, en vez de callar", () => {
    mocks.useMaintenanceWindows.mockReturnValue(
      maintData({ readError: "GET /maintenance-windows falló (503)" }),
    );
    render(<FleetPage />);
    const aviso = screen.getByTestId("fleet-maint-error");
    expect(aviso.textContent).toContain("VENTANAS DE MANTENIMIENTO");
    // La consecuencia, no el código HTTP: puede haber gabinetes mudos sin rótulo.
    expect(aviso.textContent).toContain("SIN RÓTULO");
    // Y la tarjeta sigue sin badge — eso no cambia; lo que cambia es que ahora
    // esa ausencia está EXPLICADA en vez de leerse como "no hay ventanas".
    expect(screen.queryByTestId("maintenance-badge")).toBeNull();
  });

  it("con rótulos en caché avisa de que son el ÚLTIMO dato conocido", () => {
    // El refetch de fondo falla y react-query conserva `data`: los badges siguen
    // pintados. Sin este aviso serían un dato congelado presentado como vivo
    // (regla de oro 7) — la ventana pudo cerrarse hace media hora.
    const ventana = {
      window_id: "w-1",
      tenant_id: "t-1",
      gateway_id: "1",
      gateway_serial: "TKB-1",
      site_name: "Sitio 1",
      scope: "gateway",
      opened_by: "u-1",
      reason: "cambio del cable de red del Shake",
      duration_s: 1800,
      opened_at: "2026-08-06T03:30:12Z",
      starts_at: "2026-08-06T03:31:00Z",
      ends_at: new Date(Date.now() + 1_800_000).toISOString(),
      closed_at: null,
      active: true,
      alarm_names: ["a", "b"],
      requested: 2,
      silenced: 2,
      missing_names: [],
      missing: 0,
      mute_rule: "takab-dev-mw-w-1",
    };
    mocks.useMaintenanceWindows.mockReturnValue(
      maintData({ items: [ventana] as never, readError: "GET /maintenance-windows falló (503)" }),
    );
    render(<FleetPage />);
    expect(screen.getByTestId("maintenance-badge")).toBeTruthy();
    expect(screen.getByTestId("fleet-maint-error").textContent).toContain("ÚLTIMO DATO CONOCIDO");
  });

  it("el aviso ofrece reintentar y llama al refetch de LAS VENTANAS", () => {
    // Botón propio, nombre propio: el REINTENTAR del StateFrame reintenta la
    // FLOTA, que no es lo que ha fallado aquí.
    const m = maintData({ readError: "GET /maintenance-windows falló (503)" });
    mocks.useMaintenanceWindows.mockReturnValue(m);
    render(<FleetPage />);
    fireEvent.click(screen.getByRole("button", { name: "REINTENTAR VENTANAS" }));
    expect(m.refetch).toHaveBeenCalledTimes(1);
  });

  it("sin fallo no inventa el aviso: un cero legítimo sigue siendo un cero", () => {
    mocks.useMaintenanceWindows.mockReturnValue(maintData());
    render(<FleetPage />);
    expect(screen.queryByTestId("fleet-maint-error")).toBeNull();
  });
});

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

  // [T-2.59] Regla de oro 7. La tira de KPI vive FUERA del StateFrame, así que
  // cuando la consulta falla `cabinets` es `[]` y los cuatro contadores daban
  // CERO — pintados con sus colores normales, verde el de operativos y rojo el
  // de sin-enlace. Un operador que barre la tira superior lee "cero gabinetes
  // sin enlace" = todo en orden, cuando la verdad es "no hay dato". Es el mismo
  // fallo del 2026-07-14 (15 h ciego con la consola en OPERATIVO), y es peor que
  // no mostrar nada porque el cero es tranquilizador.
  //
  // Reproducido en navegador con toda la API a 500: `0 GABINETES · 0 OPERATIVOS
  // · 0 DEGRADADOS · 0 SIN ENLACE` mientras el listado de abajo sí gritaba.
  it.each([
    ["error", { error: "GET /fleet/gateways falló (503)" }],
    ["carga", { loading: true }],
  ])("sin dato (%s) los KPI dicen S/D, no CERO", (_caso, patch) => {
    mocks.useFleet.mockReturnValue(fleetData(patch));
    render(<FleetPage />);
    const kpis = screen.getAllByTestId("fleet-kpi").map((el) => el.textContent);
    expect(kpis).toEqual(["S/DGABINETES", "S/DOPERATIVOS", "S/DDEGRADADOS", "S/DSIN ENLACE"]);
  });

  // El cero LEGÍTIMO —la consulta respondió y de verdad no hay gabinetes— tiene
  // que seguir siendo un cero: "S/D" ahí sería mentir en el otro sentido.
  it("cero real sigue siendo cero, no S/D", () => {
    mocks.useFleet.mockReturnValue(fleetData({ cabinets: [] }));
    render(<FleetPage />);
    const kpis = screen.getAllByTestId("fleet-kpi").map((el) => el.textContent);
    expect(kpis).toEqual(["0GABINETES", "0OPERATIVOS", "0DEGRADADOS", "0SIN ENLACE"]);
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

  // [T-2.71] Abrir ventana cuelga de su PROPIA acción, no de `manage_fleet`:
  // silenciar avisos y administrar inventario son permisos distintos.
  it("sin maintenance_window no se ofrece abrir ventana", () => {
    seedAuthenticated(ME_FIXTURES.soc_operator);
    render(<FleetPage />);
    expect(screen.queryByTestId("open-window")).not.toBeInTheDocument();
  });

  it("con maintenance_window se ofrece, y el motivo llega al servidor", () => {
    const maint = maintData();
    mocks.useMaintenanceWindows.mockReturnValue(maint);
    seedAuthenticated(ME_FIXTURES.tenant_admin);
    render(<FleetPage />);
    fireEvent.click(screen.getByTestId("open-window"));
    fireEvent.change(screen.getByTestId("open-window-reason"), {
      target: { value: "cambio de UPS" },
    });
    fireEvent.click(screen.getByTestId("open-window-confirm"));
    expect(maint.open).toHaveBeenCalledWith({
      gateway_id: "1",
      reason: "cambio de UPS",
      duration_s: 1800,
    });
  });

  // Dos ventanas sobre el mismo gabinete no suman silencio: suman confusión sobre
  // cuál venció. Con una viva, lo que se ofrece es CERRARLA, no abrir otra.
  it("con una ventana YA viva no se ofrece abrir otra", () => {
    mocks.useMaintenanceWindows.mockReturnValue(
      maintData({
        items: [
          {
            window_id: "w-1",
            gateway_id: "1",
            scope: "gateway",
            reason: "cambio de UPS",
            opened_at: new Date().toISOString(),
            ends_at: new Date(Date.now() + 3_600_000).toISOString(),
            // `windowCovering` descarta toda ventana con `closed_at` no nulo: sin
            // este campo el objeto no es una ventana viva y la tarjeta no la pinta.
            closed_at: null,
            muted_alarms: 0,
            total_alarms: 0,
            mute_verified: false,
          } as never,
        ],
      }),
    );
    seedAuthenticated(ME_FIXTURES.tenant_admin);
    render(<FleetPage />);
    expect(screen.getByTestId("maintenance-badge")).toBeInTheDocument();
    expect(screen.queryByTestId("open-window")).not.toBeInTheDocument();
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

// [T-2.60.a] El gabinete retirado que sigue latiendo.
//
// T-2.35 enseñó a esconder lo retirado y estuvo bien. Pero esconder por ESTADO
// sin mirar si el aparato habla creó el fallo simétrico, y el 2026-08-04 se lo
// comió un operador: su estación publicaba latidos cada 60 s mientras era
// invisible en la consola. Se supo porque preguntó él, no porque el sistema
// dijera nada.
//
// La contradicción —la organización lo cree dado de baja, el aparato reporta—
// exige acción humana en una de las dos direcciones, así que no puede vivir
// mezclada en el grid ni escondida: sección propia y ruidosa.
describe("FleetPage · fantasmas vivos", () => {
  function fantasma(id: string): FleetCabinet {
    const c = cabinet(id, "OPERATIVO");
    return {
      ...c,
      gateway: {
        ...c.gateway,
        status: "retired",
        is_ghost: true,
        retired_at: "2026-08-03T21:17:00Z",
        retired_by: "ana@takab.mx",
      },
    };
  }

  it("el fantasma sale en su propia sección, no escondido", () => {
    mocks.useFleet.mockReturnValue(fleetData({ cabinets: [fantasma("1")] }));
    render(<FleetPage />);
    expect(screen.getByTestId("fleet-ghosts")).toBeInTheDocument();
    expect(screen.getByText(/RETIRADO.*SIGUE REPORTANDO/i)).toBeInTheDocument();
  });

  it("dice cuándo y quién lo retiró, para no ir a la auditoría a mano", () => {
    mocks.useFleet.mockReturnValue(fleetData({ cabinets: [fantasma("1")] }));
    render(<FleetPage />);
    const seccion = screen.getByTestId("fleet-ghosts");
    expect(seccion.textContent).toMatch(/ana@takab\.mx/);
    expect(seccion.textContent).toMatch(/2026/);
  });

  it("NO se cuela además en el grid normal: eso resucitaría el bug de T-2.35", () => {
    mocks.useFleet.mockReturnValue(
      fleetData({ cabinets: [fantasma("1"), cabinet("2", "OPERATIVO")] }),
    );
    render(<FleetPage />);
    const grid = document.querySelector(".fleet__grid");
    expect(grid?.textContent).not.toMatch(/TKB-1/);
    expect(grid?.textContent).toMatch(/TKB-2/);
  });

  it("cuenta en la tira de KPI, porque exige acción", () => {
    mocks.useFleet.mockReturnValue(
      fleetData({ cabinets: [fantasma("1"), cabinet("2", "OPERATIVO")] }),
    );
    render(<FleetPage />);
    const kpis = screen.getAllByTestId("fleet-kpi").map((el) => el.textContent);
    expect(kpis.some((k) => k?.includes("FANTASMA"))).toBe(true);
  });

  it("sin fantasmas no hay sección ni KPI: una alarma que suena siempre no es alarma", () => {
    mocks.useFleet.mockReturnValue(fleetData({ cabinets: [cabinet("1", "OPERATIVO")] }));
    render(<FleetPage />);
    expect(screen.queryByTestId("fleet-ghosts")).toBeNull();
    const kpis = screen.getAllByTestId("fleet-kpi").map((el) => el.textContent);
    expect(kpis.some((k) => k?.includes("FANTASMA"))).toBe(false);
  });

  it("los KPI normales NO cuentan al fantasma: está dado de baja", () => {
    mocks.useFleet.mockReturnValue(
      fleetData({ cabinets: [fantasma("1"), cabinet("2", "OPERATIVO")] }),
    );
    render(<FleetPage />);
    const kpis = screen.getAllByTestId("fleet-kpi").map((el) => el.textContent);
    expect(kpis[0]).toBe("1GABINETES");
  });

  // La leyenda "MOSTRANDO n DE m" solo existe para avisar de que hay un FILTRO
  // escondiendo gabinetes. Sin filtro no debe aparecer: si lo hace, el operador
  // busca un filtro que no ha puesto.
  it("sin filtro NO aparece 'MOSTRANDO' aunque haya un fantasma apartado", () => {
    mocks.useFleet.mockReturnValue(
      fleetData({ cabinets: [fantasma("1"), cabinet("2", "OPERATIVO")] }),
    );
    render(<FleetPage />);
    expect(screen.queryByTestId("fleet-shown")).toBeNull();
  });

  // Y cuando sí hay filtro, el "DE m" tiene que ser el MISMO número que el KPI
  // GABINETES que se pinta tres centímetros más arriba. Dos cifras del mismo
  // conjunto discrepando en la misma pantalla es la regla de oro 7 al revés.
  it("con filtro, el 'DE m' coincide con el KPI GABINETES (sin el fantasma)", () => {
    mocks.useFleet.mockReturnValue(
      fleetData({
        cabinets: [fantasma("1"), cabinet("2", "OPERATIVO"), cabinet("3", "OPERATIVO")],
      }),
    );
    render(<FleetPage />);
    fireEvent.change(screen.getByLabelText("Buscar en la flota"), {
      target: { value: "TKB-2" },
    });
    const kpis = screen.getAllByTestId("fleet-kpi").map((el) => el.textContent);
    expect(kpis[0]).toBe("2GABINETES");
    expect(screen.getByTestId("fleet-shown")).toHaveTextContent("MOSTRANDO 1 DE 2");
  });
});

// [T-2.69] La deriva de versiones en la tira de KPI. Criterio 2 de la ficha:
// "se ve la deriva: cuántos gabinetes están atrás y cuánto".
describe("FleetPage · inventario de versiones", () => {
  beforeEach(() => {
    resetSessionStoreForTests();
    vi.clearAllMocks();
    mocks.useFleetSyncStates.mockReturnValue(new Map());
    mocks.useFleetHealth.mockReturnValue(new Map());
    mocks.useRetireCodeConfigured.mockReturnValue(true);
  });

  function conVersion(id: string, over: Record<string, unknown>): FleetCabinet {
    const c = cabinet(id, "OPERATIVO");
    return { ...c, gateway: { ...c.gateway, ...over } };
  }

  function kpiTexts(): string[] {
    return screen.getAllByTestId("fleet-kpi").map((el) => el.textContent ?? "");
  }

  it("cuenta cuántos gabinetes están atrás", () => {
    mocks.useFleet.mockReturnValue(
      fleetData({
        cabinets: [
          cabinet("1", "OPERATIVO"),
          conVersion("2", { version_state: "ATRASADA", releases_behind: 2 }),
          conVersion("3", { version_state: "ATRASADA", releases_behind: 1 }),
        ],
      }),
    );
    render(<FleetPage />);
    expect(kpiTexts().some((k) => k === "2ATRASADOS")).toBe(true);
  });

  it("cuenta aparte los gabinetes cuya versión NO se puede afirmar", () => {
    // Cuatro formas distintas de no saber, un solo contador: lo que el operador
    // necesita de la tira es "de cuántos no puedo responder", y el porqué de cada
    // uno vive en su tarjeta.
    mocks.useFleet.mockReturnValue(
      fleetData({
        cabinets: [
          cabinet("1", "OPERATIVO"),
          conVersion("2", { version_state: "ÚLTIMA CONOCIDA" }),
          conVersion("3", { version_state: "NO DECLARA" }),
          conVersion("4", { version_state: "SIN REPORTAR" }),
          conVersion("5", { version_state: "DESCONOCIDA" }),
        ],
      }),
    );
    render(<FleetPage />);
    expect(kpiTexts().some((k) => k === "4VERSIÓN S/D")).toBe(true);
  });

  it("el que escribió el código nuevo y no lo aplicó cuenta como ATRASADO [T-2.70]", () => {
    // SIN REINICIAR no es una forma de "no saber": se sabe exactamente qué corre
    // (lo viejo) y que no es lo publicado. Contarlo en VERSIÓN S/D lo escondería
    // entre los que no se pueden diagnosticar, cuando es de los pocos con una
    // acción concreta y urgente: ir a ver por qué la unidad no arrancó.
    mocks.useFleet.mockReturnValue(
      fleetData({
        cabinets: [
          cabinet("1", "OPERATIVO"),
          conVersion("2", { version_state: "ATRASADA", releases_behind: 1 }),
          conVersion("3", {
            version_state: "SIN REINICIAR",
            fw_version: "62f3f1e",
            fw_running: "d082095",
            releases_behind: 1,
          }),
        ],
      }),
    );
    render(<FleetPage />);
    expect(kpiTexts().some((k) => k === "2ATRASADOS")).toBe(true);
    expect(kpiTexts().some((k) => k?.includes("VERSIÓN S/D"))).toBe(false);
  });

  it("una plataforma sin releases publicados no se pinta como flota al día", () => {
    // Todos SIN REFERENCIA: se sabe qué corre cada uno, no si es lo actual. Si esto
    // contara como certeza, la tira diría "0 ATRASADOS" sobre un vacío.
    mocks.useFleet.mockReturnValue(
      fleetData({
        cabinets: [
          conVersion("1", { version_state: "SIN REFERENCIA", releases_behind: null }),
          conVersion("2", { version_state: "SIN REFERENCIA", releases_behind: null }),
        ],
      }),
    );
    render(<FleetPage />);
    expect(kpiTexts().some((k) => k === "2VERSIÓN S/D")).toBe(true);
  });

  it("con toda la flota al día no aparece ningún contador de versiones", () => {
    // Un contador clavado en cero deja de leerse a las dos semanas, y estos dos
    // tienen que dar un salto (mismo criterio que FANTASMAS).
    mocks.useFleet.mockReturnValue(
      fleetData({ cabinets: [cabinet("1", "OPERATIVO"), cabinet("2", "OPERATIVO")] }),
    );
    render(<FleetPage />);
    expect(kpiTexts().some((k) => k.includes("ATRASADOS"))).toBe(false);
    expect(kpiTexts().some((k) => k.includes("VERSIÓN"))).toBe(false);
  });

  it("sin respuesta de la API no se afirma nada sobre las versiones", () => {
    // [T-2.59] La tira vive FUERA del StateFrame: con la API caída, `cabinets` es
    // `[]` y "0 ATRASADOS" se leería como "flota entera al día".
    mocks.useFleet.mockReturnValue(fleetData({ error: "GET /fleet/gateways falló (503)" }));
    render(<FleetPage />);
    expect(kpiTexts().some((k) => k.includes("ATRASADOS"))).toBe(false);
    expect(kpiTexts().some((k) => k.includes("VERSIÓN"))).toBe(false);
  });

  it("el fantasma no engorda la deriva: está dado de baja", () => {
    const c = cabinet("1", "OPERATIVO");
    const ghost: FleetCabinet = {
      ...c,
      gateway: { ...c.gateway, status: "retired", is_ghost: true, version_state: "ATRASADA" },
    };
    mocks.useFleet.mockReturnValue(fleetData({ cabinets: [ghost, cabinet("2", "OPERATIVO")] }));
    render(<FleetPage />);
    expect(kpiTexts().some((k) => k.includes("ATRASADOS"))).toBe(false);
  });

  it("la tarjeta dice qué versión corre y de cuándo es el dato", () => {
    mocks.useFleet.mockReturnValue(
      fleetData({
        cabinets: [
          conVersion("1", {
            version_state: "ATRASADA",
            releases_behind: 3,
            release_age_s: 21 * 86_400,
            version_age_s: 30,
          }),
        ],
      }),
    );
    render(<FleetPage />);
    expect(screen.getByTestId("version-badge")).toHaveTextContent(/62f3f1e.*3 ATRÁS/);
  });
});
