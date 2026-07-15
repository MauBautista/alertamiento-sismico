import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { MapSiteState } from "@takab/sdk";

import { resetSessionStoreForTests, useSessionStore } from "../../auth/session.store";
import { expectFourStates, type UiState } from "../../test-utils/states";
import type { IncidentActionsData } from "./useIncidentActions";
import type { LiveIncident, LiveIncidentsData } from "./useLiveIncidents";
import type { MapStateData } from "./useMapState";
import type { SiteFeaturesData } from "./useSiteFeatures";

const mocks = vi.hoisted(() => ({
  ackIncidentIncidentsIncidentIdAckPost: vi.fn(),
  requestDictamenIncidentsIncidentIdDictamenRequestPost: vi.fn(),
  relocateEpicenterIncidentsIncidentIdEpicenterPost: vi.fn(),
  getEventEventsEventIdGet: vi.fn(),
  useLiveIncidents: vi.fn(),
  useMapState: vi.fn(),
  useSiteFeatures: vi.fn(),
  useIncidentActions: vi.fn(),
  useSiteSoh: vi.fn(() => null),
  MapPanel: vi.fn(({ onSelectSite }: { onSelectSite: (id: string) => void }) => (
    <div data-testid="map-mock">
      <button onClick={() => onSelectSite("s-1")}>pick-site</button>
    </div>
  )),
}));

vi.mock("@takab/sdk", () => ({
  ackIncidentIncidentsIncidentIdAckPost: mocks.ackIncidentIncidentsIncidentIdAckPost,
  requestDictamenIncidentsIncidentIdDictamenRequestPost:
    mocks.requestDictamenIncidentsIncidentIdDictamenRequestPost,
  relocateEpicenterIncidentsIncidentIdEpicenterPost:
    mocks.relocateEpicenterIncidentsIncidentIdEpicenterPost,
  getEventEventsEventIdGet: mocks.getEventEventsEventIdGet,
}));
vi.mock("./useLiveIncidents", () => ({ useLiveIncidents: mocks.useLiveIncidents }));
vi.mock("./useMapState", () => ({ useMapState: mocks.useMapState }));
vi.mock("./useSiteFeatures", () => ({ useSiteFeatures: mocks.useSiteFeatures }));
vi.mock("./useIncidentActions", () => ({ useIncidentActions: mocks.useIncidentActions }));
vi.mock("./useSiteSoh", () => ({ useSiteSoh: mocks.useSiteSoh }));
// T-1.60: el banner del drill usa react-query + SDK — stub inerte aquí.
vi.mock("./useActiveDrill", () => ({
  useActiveDrill: () => ({
    drill: null,
    loading: false,
    start: () => undefined,
    stop: () => undefined,
    pending: false,
    error: null,
  }),
}));
vi.mock("./MapPanel", () => ({ default: mocks.MapPanel }));
// T-1.49: el socket vive en AppShell — la página ya no toca lib/ws. El perfil
// del operador se mockea (la etiqueta cae al rol+sub sin display_name).
vi.mock("../../auth/useProfile", () => ({
  useProfile: () => ({ data: undefined }),
  useProfileMutation: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
}));

import ConsolePage from "./ConsolePage";

const SITE: MapSiteState = {
  site_id: "s-1",
  tenant_id: "t-1",
  name: "Planta Cholula",
  criticality: "high",
  lon: -98.3014,
  lat: 19.0633,
  last_bucket: null,
  max_pga_g: 0.15,
  max_pgv_cms: 4.2,
  open_incident: null,
  felt: "unknown",
  felt_pga_g: null,
  felt_pgv_cms: null,
  calibrated: true,
};

const INCIDENT: LiveIncident = {
  incident_id: "i-1",
  tenant_id: "t-1",
  site_id: "s-1",
  event_id: "EVT-1041",
  opened_at: "2026-07-08T10:41:30Z",
  closed_at: null,
  severity: "critical",
  state: "open",
  trigger: "local_threshold",
  max_pga_g: 0.15,
  max_pgv_cms: 4.2,
};

function incidentsData(over: Partial<LiveIncidentsData> = {}): LiveIncidentsData {
  return {
    incidents: [INCIDENT],
    loading: false,
    error: null,
    dataUpdatedAt: Date.now(),
    liveStatus: "ready",
    lastFrameAt: Date.now(),
    refetch: vi.fn(),
    ...over,
  };
}

function mapData(over: Partial<MapStateData> = {}): MapStateData {
  return {
    sites: [SITE],
    epicenters: [],
    loading: false,
    error: null,
    dataUpdatedAt: Date.now(),
    refetch: vi.fn(),
    ...over,
  };
}

function featuresData(over: Partial<SiteFeaturesData> = {}): SiteFeaturesData {
  return {
    points: [],
    latest: null,
    calibrated: false,
    loading: false,
    error: null,
    lastFrameAt: null,
    refetch: vi.fn(),
    ...over,
  };
}

function actionsData(over: Partial<IncidentActionsData> = {}): IncidentActionsData {
  return { actions: [], loading: false, error: null, refetch: vi.fn(), ...over };
}

function page(): ReactElement {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  // MemoryRouter: ConsolePage usa useNavigate (T-1.51, flujo de dictamen).
  return (
    <MemoryRouter initialEntries={["/console"]}>
      <QueryClientProvider client={client}>
        <ConsolePage />
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("ConsolePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetSessionStoreForTests();
    useSessionStore.setState({
      status: "authenticated",
      idToken: "tok",
      me: {
        sub: "abcdef12-3456",
        role: "tenant_admin",
        tenant_id: "t-1",
        surface: "web",
        site_scope: "*",
        allowed_routes: ["/console"],
        allowed_actions: {
          ack_incident: true,
          edit_thresholds: true,
          export: true,
          generate_report: false,
          sign_dictamen: false,
          siren_test: true,
          manage_fleet: true,
          relocate_epicenter: true,
          request_dictamen: true,
          read_audit: false,
          self_test: false,
          drill_start: false,
          manage_tenants: false,
          manage_visibility: false,
        },
      },
    });
    mocks.useLiveIncidents.mockReturnValue(incidentsData());
    mocks.useMapState.mockReturnValue(mapData());
    mocks.useSiteFeatures.mockReturnValue(featuresData());
    mocks.useIncidentActions.mockReturnValue(actionsData());
  });

  it("monta el wall: mapa, banner crítico e incidentes con identidad real", () => {
    render(page());
    expect(screen.getByTestId("map-mock")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("ALERTA SÍSMICA · PROTÉJASE");
    expect(screen.getByRole("alert")).toHaveTextContent("Planta Cholula");
    expect(screen.getByText("1 ACTIVOS")).toBeInTheDocument();
    expect(screen.getByTestId("operator-label")).toHaveTextContent("TENANT_ADMIN · abcdef12");
  });

  it("seleccionar un sitio (mapa) abre el DetailPanel y cerrar lo quita", () => {
    render(page());
    expect(screen.queryByTestId("detail-panel")).toBeNull();
    fireEvent.click(screen.getByText("pick-site"));
    expect(screen.getByTestId("detail-panel")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cerrar" }));
    expect(screen.queryByTestId("detail-panel")).toBeNull();
  });

  it("el acuse two-step llama al endpoint real", async () => {
    mocks.ackIncidentIncidentsIncidentIdAckPost.mockResolvedValue({
      data: {},
      response: { status: 200 },
    });
    render(page());
    fireEvent.click(screen.getByRole("button", { name: /CONFIRMAR ACUSE/ }));
    fireEvent.click(await screen.findByRole("button", { name: /CLIC DE NUEVO PARA ACUSAR/ }));
    expect(mocks.ackIncidentIncidentsIncidentIdAckPost).toHaveBeenCalledWith({
      path: { incident_id: "i-1" },
    });
  });

  it("materializa los 4 estados obligatorios (regla de oro 7)", () => {
    expectFourStates((state: UiState) => {
      mocks.useLiveIncidents.mockReturnValue(
        incidentsData(state === "loading" ? { loading: true, incidents: [] } : { incidents: [] }),
      );
      mocks.useMapState.mockReturnValue(
        mapData(
          state === "loading"
            ? { loading: true, sites: [] }
            : state === "error"
              ? { error: "GET /telemetry/map/state falló (503)", sites: [] }
              : state === "empty"
                ? { sites: [] }
                : { dataUpdatedAt: Date.now() - 120_000 },
        ),
      );
      return page();
    });
  });
});

describe("contrato DOM del layout del wall (T-1.50)", () => {
  it("el StateFrame del wall lleva .soc-wall — sin ella .soc-stage colapsa a 0 y el mapa desaparece", () => {
    resetSessionStoreForTests();
    useSessionStore.setState({ status: "authenticated", idToken: "tok" });
    mocks.useLiveIncidents.mockReturnValue(incidentsData());
    mocks.useMapState.mockReturnValue(mapData());
    mocks.useSiteFeatures.mockReturnValue(featuresData());
    mocks.useIncidentActions.mockReturnValue({
      actions: [],
      loading: false,
      error: null,
      refetch: () => undefined,
    });
    const { container } = render(page());
    expect(container.querySelector(".soc-stateframe.soc-wall")).not.toBeNull();
    expect(container.querySelector(".soc-stage")).not.toBeNull();
  });
});

describe("flujo SOLICITAR DICTAMEN (T-1.51)", () => {
  it("two-step → POST → navega a /triage con el incidente preseleccionado", async () => {
    resetSessionStoreForTests();
    useSessionStore.setState({
      status: "authenticated",
      idToken: "tok",
      me: {
        sub: "abcdef12-3456",
        role: "soc_operator",
        tenant_id: "t-1",
        surface: "web",
        site_scope: "*",
        allowed_routes: ["/console", "/triage"],
        allowed_actions: {
          ack_incident: true,
          edit_thresholds: false,
          export: false,
          generate_report: false,
          sign_dictamen: false,
          siren_test: false,
          manage_fleet: false,
          relocate_epicenter: true,
          request_dictamen: true,
          read_audit: false,
          self_test: false,
          drill_start: false,
          manage_tenants: false,
          manage_visibility: false,
        },
      },
    });
    mocks.useLiveIncidents.mockReturnValue(incidentsData());
    mocks.useMapState.mockReturnValue(mapData());
    mocks.useSiteFeatures.mockReturnValue(featuresData());
    mocks.useIncidentActions.mockReturnValue(actionsData());
    mocks.requestDictamenIncidentsIncidentIdDictamenRequestPost.mockResolvedValue({
      data: { action_id: "a-9", incident_id: "i-1", kind: "dictamen_request" },
      response: { status: 201 },
    });

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter initialEntries={["/console"]}>
        <QueryClientProvider client={client}>
          <Routes>
            <Route path="/console" element={<ConsolePage />} />
            <Route path="/triage" element={<div data-testid="triage-probe" />} />
          </Routes>
        </QueryClientProvider>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: /SOLICITAR DICTAMEN TÉCNICO/ }));
    fireEvent.click(await screen.findByRole("button", { name: /CLIC DE NUEVO PARA SOLICITAR/ }));

    expect(await screen.findByTestId("triage-probe")).toBeInTheDocument();
    expect(mocks.requestDictamenIncidentsIncidentIdDictamenRequestPost).toHaveBeenCalledWith(
      expect.objectContaining({ path: { incident_id: "i-1" } }),
    );
  });
});
