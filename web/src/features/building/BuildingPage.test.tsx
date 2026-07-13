import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { resetSessionStoreForTests } from "../../auth/session.store";
import { ME_FIXTURES } from "../../test-utils/meFixtures";
import { renderRoutesAt, seedAuthenticated } from "../../test-utils/renderRoutes";

const mocks = vi.hoisted(() => ({
  useSiteChannels: vi.fn(),
  useSiteMetrics: vi.fn(),
  useSiteIncidents: vi.fn(),
  useSirenTest: vi.fn(),
  useSiteSoh: vi.fn(),
  getSite: vi.fn(),
}));

vi.mock("../telemetry/useSiteChannels", () => ({
  useSiteChannels: mocks.useSiteChannels,
  CHANNELS_STALE_MS: 30_000,
}));
vi.mock("../telemetry/useSiteMetrics", () => ({
  useSiteMetrics: mocks.useSiteMetrics,
  bucketFor: (p: string) => (p === "7d" ? "1h" : "1m"),
  HISTORY_PRESETS: ["1h", "6h", "24h", "7d"],
}));
vi.mock("./useSiteIncidents", () => ({
  useSiteIncidents: mocks.useSiteIncidents,
  SITE_INCIDENTS_STALE_MS: 90_000,
}));
vi.mock("./useSirenTest", () => ({ useSirenTest: mocks.useSirenTest }));
vi.mock("../console/useSiteSoh", () => ({ useSiteSoh: mocks.useSiteSoh }));
// B-4 (T-1.58): el subtítulo depende de GET /sites/{id} — se mockea SOLO esa
// función del SDK (el resto del módulo sigue real).
vi.mock("@takab/sdk", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@takab/sdk")>()),
  getSiteSitesSiteIdGet: mocks.getSite,
}));

const CHANNELS = {
  channels: [
    {
      channel: "EHZ",
      ts: [Date.parse("2026-07-08T10:00:00Z"), Date.parse("2026-07-08T10:00:01Z")],
      pga: [0.01, 0.02],
      pgv: [0.1, 0.2],
      clipping: [false, false],
    },
  ],
  calibrated: false,
  loading: false,
  error: null,
  dataUpdatedAt: Date.now(),
  refetch: vi.fn(),
};

const METRICS = {
  points: [{ ts: Date.parse("2026-07-08T10:00:00Z"), maxPga: 0.03, maxPgv: 0.3 }],
  bucket: "1m",
  calibrated: false,
  loading: false,
  error: null,
  refetch: vi.fn(),
};

const INCIDENTS = {
  incidents: [
    {
      incident_id: "i-1",
      tenant_id: "t-1",
      site_id: "s-1",
      event_id: null,
      opened_at: "2026-07-08T10:41:00Z",
      closed_at: null,
      severity: "critical",
      state: "open",
      trigger: "sasmex",
      max_pga_g: 0.3,
      max_pgv_cms: 3,
    },
  ],
  loading: false,
  error: null,
  dataUpdatedAt: Date.now(),
  refetch: vi.fn(),
};

const SIREN_IDLE = {
  phase: "idle" as const,
  command: null,
  detail: null,
  activate: vi.fn(),
  deactivate: vi.fn(),
  reset: vi.fn(),
  pending: false,
};

describe("BuildingPage", () => {
  beforeEach(() => {
    resetSessionStoreForTests();
    mocks.useSiteChannels.mockReturnValue(CHANNELS);
    mocks.useSiteMetrics.mockReturnValue(METRICS);
    mocks.useSiteIncidents.mockReturnValue(INCIDENTS);
    mocks.useSirenTest.mockReturnValue(SIREN_IDLE);
    mocks.useSiteSoh.mockReturnValue(null);
  });

  it("ya no es un placeholder: monta canales, historial, salud e incidentes", () => {
    seedAuthenticated(ME_FIXTURES.building_admin);
    renderRoutesAt("/building/s-1");

    expect(screen.queryByText(/EN CONSTRUCCIÓN/)).toBeNull();
    expect(screen.getByTestId("channels-card")).toBeInTheDocument();
    expect(screen.getByTestId("history-card")).toBeInTheDocument();
    expect(screen.getByTestId("soh-card")).toBeInTheDocument();
    expect(screen.getByTestId("incidents-card")).toBeInTheDocument();
    expect(screen.getByTestId("multi-channel-strip")).toBeInTheDocument();
    expect(screen.getByTestId("history-chart")).toBeInTheDocument();
  });

  it("B-4: el subtítulo distingue cargar de fallar, con reintento real", async () => {
    seedAuthenticated(ME_FIXTURES.building_admin);
    mocks.getSite.mockResolvedValue({ data: undefined, response: { status: 500 } });
    renderRoutesAt("/building/s-1");
    expect(await screen.findByText(/SITIO NO DISPONIBLE/)).toBeInTheDocument();
    expect(screen.queryByText(/CARGANDO SITIO…/)).toBeNull();
    const calls = mocks.getSite.mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "REINTENTAR" }));
    await waitFor(() => expect(mocks.getSite.mock.calls.length).toBeGreaterThan(calls));
  });

  it("B-4: con el sitio cargado pinta su nombre (no el placeholder)", async () => {
    seedAuthenticated(ME_FIXTURES.building_admin);
    mocks.getSite.mockResolvedValue({
      data: { site_id: "s-1", name: "Planta Cholula", code: "CHO", lat: 19.06, lon: -98.3 },
      response: { status: 200 },
    });
    renderRoutesAt("/building/s-1");
    expect(await screen.findByText("Planta Cholula")).toBeInTheDocument();
  });

  it("sin frame de salud muestra S/D, nunca una salud inventada", () => {
    seedAuthenticated(ME_FIXTURES.building_admin);
    renderRoutesAt("/building/s-1");
    // Regla de oro 10: el heartbeat no ha llegado; no hay batería ni NTP que enseñar.
    expect(screen.getAllByText("S/D").length).toBe(3);
  });

  it("building_admin ve la prueba de sirena; inspector no", () => {
    seedAuthenticated(ME_FIXTURES.building_admin);
    renderRoutesAt("/building/s-1");
    expect(screen.getByTestId("siren-panel")).toBeInTheDocument();
  });

  it("inspector no puede tocar la sirena de un edificio ajeno", () => {
    // RBAC §2: inspector firma dictámenes, no acciona actuadores.
    seedAuthenticated(ME_FIXTURES.inspector);
    renderRoutesAt("/building/s-1");
    expect(screen.queryByTestId("siren-panel")).toBeNull();
  });

  it("propaga el flag de calibración a las dos vistas sísmicas", () => {
    seedAuthenticated(ME_FIXTURES.building_admin);
    renderRoutesAt("/building/s-1");
    // Uno en el strip (por traza) y otro en el historial.
    expect(screen.getAllByTestId("not-calibrated-badge").length).toBeGreaterThan(0);
    expect(screen.getByTestId("trace-EHZ")).toHaveTextContent("rel.");
  });

  it("sin canales muestra el estado vacío, no un strip plano", () => {
    seedAuthenticated(ME_FIXTURES.building_admin);
    mocks.useSiteChannels.mockReturnValue({ ...CHANNELS, channels: [] });
    renderRoutesAt("/building/s-1");
    expect(screen.getByText("SIN FEATURES EN LOS ÚLTIMOS 10 MIN")).toBeInTheDocument();
    expect(screen.queryByTestId("multi-channel-strip")).toBeNull();
  });

  it("un error de canales se muestra y se puede reintentar", () => {
    seedAuthenticated(ME_FIXTURES.building_admin);
    mocks.useSiteChannels.mockReturnValue({ ...CHANNELS, error: "boom" });
    renderRoutesAt("/building/s-1");
    expect(screen.getByText("boom")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "REINTENTAR" })).toBeInTheDocument();
  });

  it("lista los incidentes del sitio con su severidad", () => {
    seedAuthenticated(ME_FIXTURES.building_admin);
    renderRoutesAt("/building/s-1");
    expect(screen.getByText("CRÍTICO")).toBeInTheDocument();
    expect(screen.getByText("SASMEX")).toBeInTheDocument();
  });
});
