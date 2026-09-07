// [T-6.01] La franja de escena: la tabla aplicada al DOM, con las cuatro fuentes
// y la excepción escrita. Los hooks se mockean (el dato entra por ellos); lo que
// se mide es qué pinta la franja para cada combinación, y que en NORMAL no pinta
// nada.

import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  useLiveIncidents: vi.fn(),
  useMapState: vi.fn(),
  useActiveDrill: vi.fn(),
  useMaintenanceWindows: vi.fn(),
  useDemoMode: vi.fn(),
}));
vi.mock("../console/useLiveIncidents", () => ({ useLiveIncidents: mocks.useLiveIncidents }));
vi.mock("../console/useMapState", () => ({ useMapState: mocks.useMapState }));
vi.mock("../console/useActiveDrill", () => ({ useActiveDrill: mocks.useActiveDrill }));
vi.mock("../console/useMaintenanceWindows", () => ({
  useMaintenanceWindows: mocks.useMaintenanceWindows,
}));
vi.mock("../console/useDemoMode", () => ({ useDemoMode: mocks.useDemoMode }));

import { resetSessionStoreForTests, useSessionStore } from "../../auth/session.store";
import { ME_FIXTURES } from "../../test-utils/meFixtures";
import { expectFourStates, type UiState } from "../../test-utils/states";
import type { ActiveDrillData } from "../console/useActiveDrill";
import type { DemoModeData } from "../console/useDemoMode";
import type { LiveIncident, LiveIncidentsData } from "../console/useLiveIncidents";
import type { MaintenanceData } from "../console/useMaintenanceWindows";
import type { MapStateData } from "../console/useMapState";
import SceneStrip, { SCENE_ALERT_STALE_MS } from "./SceneStrip";

const NOW = Date.parse("2026-09-07T10:00:00Z");

function incidente(over: Partial<LiveIncident> = {}): LiveIncident {
  return {
    incident_id: "abcdef12-0000-0000-0000-000000000000",
    tenant_id: "t-1",
    site_id: "s-1",
    event_id: "EVT-1",
    opened_at: "2026-09-07T09:59:00Z",
    closed_at: null,
    severity: "critical",
    state: "open",
    trigger: "sasmex",
    max_pga_g: 0.1,
    max_pgv_cms: 1,
    ...over,
  };
}

function incidentsData(over: Partial<LiveIncidentsData> = {}): LiveIncidentsData {
  return {
    incidents: [],
    loading: false,
    error: null,
    dataUpdatedAt: NOW - 1_000,
    liveStatus: "ready",
    lastFrameAt: null,
    degraded: [],
    refetch: vi.fn(),
    ...over,
  };
}

function mapData(over: Partial<MapStateData> = {}): MapStateData {
  return {
    sites: [
      {
        site_id: "s-1",
        tenant_id: "t-1",
        name: "Planta Cholula",
        code: "site-cholula-a",
        criticality: "high",
        lon: -98.3,
        lat: 19.06,
        last_bucket: null,
        max_pga_g: null,
        max_pgv_cms: null,
        open_incident: null,
        felt: "unknown",
      } as MapStateData["sites"][number],
    ],
    epicenters: [],
    loading: false,
    error: null,
    dataUpdatedAt: NOW - 1_000,
    refetch: vi.fn(),
    ...over,
  };
}

function drillData(over: Partial<ActiveDrillData> = {}): ActiveDrillData {
  return {
    drill: null,
    scheduled: [],
    loading: false,
    readError: null,
    updatedAt: NOW - 1_000,
    refetch: vi.fn(),
    start: vi.fn(),
    stop: vi.fn(),
    cancel: vi.fn(),
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
  started_at: "2026-09-07T09:58:00Z",
  stopped_at: null,
  stop_reason: null,
  active: true,
  sites: [
    {
      site_id: "s-1",
      site_name: "Planta Cholula",
      command_id: "c-1",
      command_status: "acked",
      ack: null,
      commandable: true,
    },
  ],
};

function maintData(over: Partial<MaintenanceData> = {}): MaintenanceData {
  return {
    items: [],
    loading: false,
    readError: null,
    forbidden: false,
    updatedAt: NOW - 1_000,
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

const WINDOW = {
  window_id: "w-1",
  tenant_id: "t-1",
  gateway_id: "gw-1",
  gateway_serial: "SER-1",
  site_name: "Torre Dev",
  scope: "gateway",
  opened_by: "u-1",
  reason: "cambio del cable de red del Shake",
  duration_s: 1800,
  opened_at: "2026-09-07T09:50:00Z",
  starts_at: "2026-09-07T09:50:00Z",
  ends_at: "2026-09-07T10:20:00Z",
  closed_at: null,
  active: true,
  alarm_names: ["a"],
  requested: 1,
  silenced: 1,
  missing_names: [],
  missing: 0,
  mute_rule: "r",
  mute_verified: true,
};

function demoData(over: Partial<DemoModeData> = {}): DemoModeData {
  return {
    demo: { active: false } as DemoModeData["demo"],
    loading: false,
    readError: false,
    updatedAt: NOW - 1_000,
    refetch: vi.fn(),
    encender: vi.fn(),
    apagar: vi.fn(),
    pending: false,
    ...over,
  };
}

const DEMO_ON = {
  active: true,
  tenant_id: "t-1",
  enabled_by: "u-1",
  enabled_at: "2026-09-07T09:00:00Z",
  expires_at: "2026-09-07T11:00:00Z",
  remaining_s: 3600,
  note: "",
};

function pintar(ruta = "/fleet") {
  return render(
    <MemoryRouter initialEntries={[ruta]}>
      <SceneStrip />
    </MemoryRouter>,
  );
}

/** Los hijos VISIBLES de la franja (los marcos `hidden` no cuentan). */
function visibles(container: HTMLElement): Element[] {
  return [...(container.querySelector(".soc-scene")?.children ?? [])].filter(
    (el) => !el.hasAttribute("hidden"),
  );
}

beforeEach(() => {
  resetSessionStoreForTests();
  useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.tenant_admin });
  vi.useFakeTimers();
  vi.setSystemTime(NOW);
  mocks.useLiveIncidents.mockReturnValue(incidentsData());
  mocks.useMapState.mockReturnValue(mapData());
  mocks.useActiveDrill.mockReturnValue(drillData());
  mocks.useMaintenanceWindows.mockReturnValue(maintData());
  mocks.useDemoMode.mockReturnValue(demoData());
});

afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe("SceneStrip · la escena NORMAL es la ausencia de franja (U-45)", () => {
  it("con nada vivo no hay UN solo hijo visible, y lo declara en el DOM", () => {
    const { container } = pintar();
    expect(screen.getByTestId("scene-strip")).toHaveAttribute("data-scene", "normal");
    expect(visibles(container)).toEqual([]);
    expect(screen.queryByText(/SIN SIMULACRO/)).toBeNull();
    expect(screen.queryByText(/SIN VENTANA/)).toBeNull();
  });

  it("…pero los cuatro marcos SIGUEN ahí, en `empty`: la tabla los ve, la hoja los esconde", () => {
    const { container } = pintar();
    const vacios = container.querySelectorAll('.soc-scene > [data-state="empty"][hidden]');
    expect(vacios).toHaveLength(4);
  });
});

describe("SceneStrip · cada fuente pinta lo suyo", () => {
  it("un simulacro en curso pinta el banner NO-real", () => {
    mocks.useActiveDrill.mockReturnValue(drillData({ drill: DRILL }));
    pintar();
    expect(screen.getByTestId("scene-strip")).toHaveAttribute("data-scene", "drill");
    expect(screen.getByTestId("drill-banner")).toHaveTextContent("ESTO NO ES UNA ALERTA REAL");
  });

  it("una ventana de mantenimiento pinta que hay alarmas mudas", () => {
    mocks.useMaintenanceWindows.mockReturnValue(maintData({ items: [WINDOW] as never }));
    pintar();
    expect(screen.getByTestId("scene-strip")).toHaveAttribute("data-scene", "maintenance");
    expect(screen.getByTestId("maintenance-banner")).toHaveTextContent("VENTANA DE MANTENIMIENTO");
  });

  it("el modo demostración pinta que no se avisa a nadie", () => {
    mocks.useDemoMode.mockReturnValue(demoData({ demo: DEMO_ON }));
    pintar();
    expect(screen.getByTestId("scene-strip")).toHaveAttribute("data-scene", "demo");
    expect(screen.getByTestId("demo-mode-banner")).toHaveTextContent("NO SE AVISA A NADIE");
  });

  it("una alerta real pinta la línea con el titular honesto, el sitio y el camino al wall", () => {
    mocks.useLiveIncidents.mockReturnValue(incidentsData({ incidents: [incidente()] }));
    pintar();
    expect(screen.getByTestId("scene-strip")).toHaveAttribute("data-scene", "alert");
    const linea = screen.getByTestId("scene-alert");
    expect(linea).toHaveAttribute("data-kind", "alert");
    expect(linea).toHaveTextContent("ALERTA SÍSMICA · PROTÉJASE");
    // El nombre sale del snapshot del mapa; la hoja lo pone en mayúsculas.
    expect(linea).toHaveTextContent("Planta Cholula");
    expect(linea).toHaveTextContent("EVENT_ID EVT-1");
    expect(screen.getByRole("link", { name: "IR AL MONITOREO" })).toHaveAttribute(
      "href",
      "/console",
    );
  });

  it("sin el sitio en el snapshot no inventa un nombre: SITIO + id corto", () => {
    mocks.useMapState.mockReturnValue(mapData({ sites: [] }));
    mocks.useLiveIncidents.mockReturnValue(incidentsData({ incidents: [incidente()] }));
    pintar();
    expect(screen.getByTestId("scene-alert")).toHaveTextContent("SITIO s-1");
  });
});

describe("SceneStrip · la precedencia y la excepción escrita", () => {
  it("[U-28] un AVISO instrumental es `notice`: se declara, pero NO degrada el simulacro", () => {
    mocks.useLiveIncidents.mockReturnValue(
      incidentsData({ incidents: [incidente({ trigger: "local_threshold" })] }),
    );
    mocks.useActiveDrill.mockReturnValue(drillData({ drill: DRILL }));
    pintar();
    expect(screen.getByTestId("scene-strip")).toHaveAttribute("data-scene", "notice");
    const linea = screen.getByTestId("scene-alert");
    expect(linea).toHaveAttribute("data-kind", "notice");
    expect(linea).toHaveTextContent("AVISO SÍSMICO · UMBRAL INSTRUMENTAL");
    expect(screen.getByTestId("drill-banner")).toBeInTheDocument();
    expect(screen.queryByTestId("drill-badge")).toBeNull();
  });

  it("una activación manual tampoco domina: es una persona, no una fuente que autoriza", () => {
    mocks.useLiveIncidents.mockReturnValue(
      incidentsData({ incidents: [incidente({ trigger: "manual" })] }),
    );
    mocks.useActiveDrill.mockReturnValue(drillData({ drill: DRILL }));
    pintar();
    expect(screen.getByTestId("scene-strip")).toHaveAttribute("data-scene", "notice");
    expect(screen.queryByTestId("drill-badge")).toBeNull();
  });

  it("bajo la ALERTA REAL el simulacro se degrada a badge; mantenimiento y demo NO", () => {
    mocks.useLiveIncidents.mockReturnValue(incidentsData({ incidents: [incidente()] }));
    mocks.useActiveDrill.mockReturnValue(drillData({ drill: DRILL }));
    mocks.useMaintenanceWindows.mockReturnValue(maintData({ items: [WINDOW] as never }));
    mocks.useDemoMode.mockReturnValue(demoData({ demo: DEMO_ON }));
    pintar();
    expect(screen.getByTestId("scene-strip")).toHaveAttribute("data-scene", "alert");
    expect(screen.getByTestId("scene-alert")).toBeInTheDocument();
    expect(screen.getByTestId("drill-badge")).toHaveTextContent("LA ALERTA REAL DOMINA");
    expect(screen.queryByTestId("drill-banner")).toBeNull();
    // La excepción escrita (T-2.71 / T-1.69 / D-27): siguen enteros.
    expect(screen.getByTestId("maintenance-banner")).toHaveTextContent("VENTANA DE MANTENIMIENTO");
    expect(screen.getByTestId("demo-mode-banner")).toHaveTextContent("NO SE AVISA A NADIE");
  });

  it("en el WALL la línea de alerta no se pinta (la tarjeta ya está), pero la escena sigue mandando", () => {
    // Medido a 1280×800: 42 px de línea dejaban el escenario en su piso y los
    // sobrepuestos del mapa se pisaban. El wall tiene su tarjeta anclada; la
    // línea es el eco para las otras cinco rutas. El simulacro sí se degrada.
    mocks.useLiveIncidents.mockReturnValue(incidentsData({ incidents: [incidente()] }));
    mocks.useActiveDrill.mockReturnValue(drillData({ drill: DRILL }));
    const { container } = pintar("/console");
    expect(screen.getByTestId("scene-strip")).toHaveAttribute("data-scene", "alert");
    expect(screen.getByTestId("scene-strip")).toHaveAttribute("data-wall", "true");
    expect(screen.queryByTestId("scene-alert")).toBeNull();
    expect(screen.getByTestId("drill-badge")).toHaveTextContent("LA ALERTA REAL DOMINA");
    // Tres marcos, no cuatro: el de la alerta no se monta en el wall.
    expect(container.querySelectorAll(".soc-scene > .soc-stateframe")).toHaveLength(3);
  });

  it("el orden en el DOM es el de la tabla: alerta, simulacro, mantenimiento, demo", () => {
    mocks.useLiveIncidents.mockReturnValue(incidentsData({ incidents: [incidente()] }));
    mocks.useActiveDrill.mockReturnValue(drillData({ drill: DRILL }));
    mocks.useMaintenanceWindows.mockReturnValue(maintData({ items: [WINDOW] as never }));
    mocks.useDemoMode.mockReturnValue(demoData({ demo: DEMO_ON }));
    const { container } = pintar();
    const ids = visibles(container).map(
      (el) => el.querySelector("[data-testid]")?.getAttribute("data-testid") ?? el.tagName,
    );
    expect(ids).toEqual(["scene-alert", "drill-badge", "maintenance-banner", "demo-mode-banner"]);
  });
});

describe("SceneStrip · los cuatro estados de cada fuente (regla de oro 7)", () => {
  it("la línea de alerta materializa los cuatro estados sobre /incidents", () => {
    const byState: Record<UiState, Partial<LiveIncidentsData>> = {
      loading: { loading: true },
      error: { error: "GET /incidents falló (503)" },
      empty: {},
      stale: { incidents: [incidente()], dataUpdatedAt: NOW - SCENE_ALERT_STALE_MS - 1 },
    };
    expectFourStates((state) => {
      mocks.useLiveIncidents.mockReturnValue(incidentsData(byState[state]));
      return (
        <MemoryRouter>
          <SceneStrip />
        </MemoryRouter>
      );
    });
  });

  it("una alerta con la lectura vieja se conserva y se rotula RETENIDA, jamás se calla", () => {
    mocks.useLiveIncidents.mockReturnValue(
      incidentsData({ incidents: [incidente()], dataUpdatedAt: NOW - SCENE_ALERT_STALE_MS - 1 }),
    );
    pintar();
    expect(screen.getByTestId("scene-alert")).toBeInTheDocument();
    expect(screen.getByText(/DATOS RETENIDOS/)).toBeInTheDocument();
  });

  it("un fallo de lectura del simulacro NO calla al mantenimiento, ni al revés", () => {
    mocks.useActiveDrill.mockReturnValue(
      drillData({ readError: "GET /drills/active falló (503)" }),
    );
    mocks.useMaintenanceWindows.mockReturnValue(maintData({ items: [WINDOW] as never }));
    const { container } = pintar();
    expect(container.querySelector('[data-state="error"]')).not.toBeNull();
    expect(screen.getByTestId("maintenance-banner")).toBeInTheDocument();
  });

  it("a quien la API le niega leer ventanas (403) no se le pinta un fallo en cada pantalla", () => {
    mocks.useMaintenanceWindows.mockReturnValue(
      maintData({ readError: "GET /maintenance-windows falló (403)", forbidden: true }),
    );
    const { container } = pintar();
    expect(container.querySelector('[data-state="error"]')).toBeNull();
    expect(screen.queryByRole("button", { name: "REINTENTAR" })).toBeNull();
    // Y sigue sin ser un hueco: los otros tres marcos están.
    expect(container.querySelectorAll(".soc-scene > .soc-stateframe")).toHaveLength(3);
  });

  it("[T-6.04] la línea de alerta de un sitio simulado lleva la cinta DEMO", () => {
    const base = mapData();
    mocks.useMapState.mockReturnValue(
      mapData({
        sites: [{ ...base.sites[0], name: "Sitio Sim 001 Puebla", code: "site-sim-001" }],
      }),
    );
    mocks.useLiveIncidents.mockReturnValue(
      incidentsData({ incidents: [incidente({ trigger: "local_threshold" })] }),
    );
    pintar();
    const linea = screen.getByTestId("scene-alert");
    expect(linea).toHaveTextContent("Sitio Sim 001 Puebla");
    expect(within(linea).getByTestId("site-demo")).toHaveTextContent("DEMO");
  });
});
