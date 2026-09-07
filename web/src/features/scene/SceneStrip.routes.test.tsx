// [T-6.01] Criterio 1: con un simulacro, una ventana de mantenimiento o el modo
// demostración vivos, las SEIS rutas lo declaran en el primer frame.
//
// Se monta el árbol REAL de rutas (`renderRoutesAt`) con las fuentes de escena
// mockeadas: lo que se mide es que la franja está en cada ruta, no la escena
// (eso es `SceneStrip.test.tsx`). Las páginas de debajo caen a sus estados de
// error sin red, como en `routes.guards.test.tsx`, y no importa: la franja no
// depende de ellas — que es justo el punto.

import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

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

import { resetSessionStoreForTests } from "../../auth/session.store";
import { ALL_ROUTES, ME_FIXTURES } from "../../test-utils/meFixtures";
import { renderRoutesAt, seedAuthenticated } from "../../test-utils/renderRoutes";

const NOW = Date.now();

const URL_BY_ROUTE: Record<string, string> = {
  "/console": "/console",
  "/fleet": "/fleet",
  "/triage": "/triage",
  "/tenants": "/tenants",
  "/audit": "/audit",
  "/building": "/building/S-001",
};

const DRILL = {
  drill_id: "d-1",
  tenant_id: "t-1",
  initiated_by: "u-1",
  note: null,
  duration_s: 300,
  scheduled_at: null,
  started_at: new Date(NOW - 60_000).toISOString(),
  stopped_at: null,
  stop_reason: null,
  active: true,
  sites: [],
};

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
  opened_at: new Date(NOW - 60_000).toISOString(),
  starts_at: new Date(NOW - 60_000).toISOString(),
  ends_at: new Date(NOW + 1_740_000).toISOString(),
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

const INCIDENT = {
  incident_id: "abcdef12-0000-0000-0000-000000000000",
  tenant_id: "t-1",
  site_id: "s-1",
  event_id: "EVT-1",
  opened_at: new Date(NOW - 30_000).toISOString(),
  closed_at: null,
  severity: "critical",
  state: "open",
  trigger: "sasmex",
  max_pga_g: 0.1,
  max_pgv_cms: 1,
};

beforeEach(() => {
  resetSessionStoreForTests();
  seedAuthenticated(ME_FIXTURES.takab_superadmin);
  mocks.useLiveIncidents.mockReturnValue({
    incidents: [INCIDENT],
    loading: false,
    error: null,
    dataUpdatedAt: NOW,
    liveStatus: "ready",
    lastFrameAt: null,
    degraded: [],
    refetch: vi.fn(),
  });
  mocks.useMapState.mockReturnValue({
    sites: [],
    epicenters: [],
    loading: false,
    error: null,
    dataUpdatedAt: NOW,
    refetch: vi.fn(),
  });
  mocks.useActiveDrill.mockReturnValue({
    drill: DRILL,
    scheduled: [],
    loading: false,
    readError: null,
    updatedAt: NOW,
    refetch: vi.fn(),
    start: vi.fn(),
    stop: vi.fn(),
    cancel: vi.fn(),
    pending: false,
    error: null,
  });
  mocks.useMaintenanceWindows.mockReturnValue({
    items: [WINDOW],
    loading: false,
    readError: null,
    forbidden: false,
    updatedAt: NOW,
    refetch: vi.fn(),
    close: vi.fn(),
    open: vi.fn(),
    pending: false,
    openPending: false,
    error: null,
    openError: null,
  });
  mocks.useDemoMode.mockReturnValue({
    demo: {
      active: true,
      tenant_id: "t-1",
      enabled_by: "u-1",
      enabled_at: new Date(NOW - 60_000).toISOString(),
      expires_at: new Date(NOW + 3_600_000).toISOString(),
      remaining_s: 3600,
      note: "",
    },
    loading: false,
    readError: false,
    updatedAt: NOW,
    refetch: vi.fn(),
    encender: vi.fn(),
    apagar: vi.fn(),
    pending: false,
  });
});

describe("[T-6.01] la escena se declara en las seis rutas", () => {
  it.each([...ALL_ROUTES])(
    "%s pinta alerta, simulacro (degradado), mantenimiento y demo",
    (routeKey) => {
      renderRoutesAt(URL_BY_ROUTE[routeKey]);
      const franja = screen.getByTestId("scene-strip");
      expect(franja).toHaveAttribute("data-scene", "alert");
      if (routeKey === "/console") {
        // En el wall la alerta la declara su tarjeta anclada al escenario
        // (`AlertBanner`, ejercida en `ConsolePage.test.tsx` con el mapa vivo;
        // aquí el snapshot del mapa está vacío y el wall pinta su `empty`); la
        // línea de la franja es el eco para las otras cinco (ver `WALL_ROUTE`).
        expect(screen.queryByTestId("scene-alert")).toBeNull();
        expect(franja).toHaveAttribute("data-wall", "true");
      } else {
        expect(screen.getByTestId("scene-alert")).toHaveTextContent("ALERTA SÍSMICA · PROTÉJASE");
      }
      expect(screen.getByTestId("drill-badge")).toHaveTextContent("LA ALERTA REAL DOMINA");
      expect(screen.getByTestId("maintenance-banner")).toHaveTextContent(
        "VENTANA DE MANTENIMIENTO",
      );
      expect(screen.getByTestId("demo-mode-banner")).toHaveTextContent("NO SE AVISA A NADIE");
      // Y sólo UNA franja: la del shell. Ninguna página monta la suya.
      expect(screen.getAllByTestId("scene-strip")).toHaveLength(1);
    },
  );

  it("la franja va ANTES que la página en el DOM: se lee primero", () => {
    renderRoutesAt("/fleet");
    const main = document.querySelector(".soc-app > main.soc-main");
    expect(main?.children[0].classList.contains("soc-scene")).toBe(true);
  });
});
