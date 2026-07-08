import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
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
}));
vi.mock("./useLiveIncidents", () => ({ useLiveIncidents: mocks.useLiveIncidents }));
vi.mock("./useMapState", () => ({ useMapState: mocks.useMapState }));
vi.mock("./useSiteFeatures", () => ({ useSiteFeatures: mocks.useSiteFeatures }));
vi.mock("./useIncidentActions", () => ({ useIncidentActions: mocks.useIncidentActions }));
vi.mock("./useSiteSoh", () => ({ useSiteSoh: mocks.useSiteSoh }));
vi.mock("./MapPanel", () => ({ default: mocks.MapPanel }));
vi.mock("../../lib/ws", () => ({
  LiveSocket: vi.fn(() => ({ connect: vi.fn(), close: vi.fn() })),
  liveWsUrl: () => "ws://test/api/ws",
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
  return (
    <QueryClientProvider client={client}>
      <ConsolePage />
    </QueryClientProvider>
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
          sign_dictamen: false,
          siren_test: true,
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
