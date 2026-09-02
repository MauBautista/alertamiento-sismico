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

// [T-2.08] Mock PARCIAL: bms/groupActions ahora también sale de @takab/sdk
// (compartido con el móvil) y el DetailPanel lo usa de verdad.
vi.mock("@takab/sdk", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@takab/sdk")>()),
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
// [T-2.48] El stub declara el contrato COMPLETO a propósito: con `readError`
// ausente (`undefined`) el banner leería "no sé si hay simulacro" y el estado
// del stub dejaría de ser inerte.
vi.mock("./useActiveDrill", () => ({
  useActiveDrill: () => ({
    drill: null,
    scheduled: [],
    loading: false,
    readError: null,
    updatedAt: 0,
    refetch: () => undefined,
    start: () => undefined,
    stop: () => undefined,
    cancel: () => undefined,
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
  code: "site-cholula-a",
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
    // [T-2.129] Canal sano por defecto: la degradación es la excepción y se pide.
    degraded: [],
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
          manage_retire_code: false,
          manage_users: false,
          // Acciones de la superficie móvil (T-2.03): inertes en la consola.
          panel_read: false,
          checkin_submit: false,
          damage_report_submit: false,
          dictamen_read: false,
          enrollment_manage: false,
          evidence_upload: false,
          manual_activate: false,
          panic_vote: false,
          roster_read: false,
          siren_silence: false,
          maintenance_window: false,
          platform_maintenance_window: false,
          deploy_firmware: false,
          manage_privacy_notice: false,
          manage_privacy_erasure: false,
          cctv_read: false,
          cctv_video: false,
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
    // [T-5.03] El banner dice lo que dice el `trigger` del fixture (`local_threshold`),
    // no un titular fijo. Hasta hoy este test —como el de `AlertBanner`— afirmaba
    // «ALERTA SÍSMICA · PROTÉJASE» para un umbral instrumental: la misma mentira,
    // encodada por segunda vez en una prueba distinta. El `data-trigger` ata la
    // aserción al fixture para que no puedan volver a separarse en silencio.
    expect(screen.getByRole("alert")).toHaveAttribute("data-trigger", "local_threshold");
    expect(screen.getByRole("alert")).toHaveTextContent("AVISO SÍSMICO · UMBRAL INSTRUMENTAL");
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

// ---- T-2.50: estadísticas del wall ----------------------------------------
describe("ConsolePage · KPIs y filtro (T-2.50)", () => {
  const CAIDA: MapSiteState = { ...SITE, site_id: "s-down", link_state: "SIN ENLACE" };
  const VIVA: MapSiteState = { ...SITE, site_id: "s-up", link_state: "OPERATIVO" };

  beforeEach(() => {
    vi.clearAllMocks();
    resetSessionStoreForTests();
    useSessionStore.setState({ status: "authenticated", idToken: "tok" });
    mocks.useLiveIncidents.mockReturnValue(incidentsData({ incidents: [] }));
    mocks.useMapState.mockReturnValue(mapData({ sites: [VIVA, CAIDA] }));
    mocks.useSiteFeatures.mockReturnValue(featuresData());
    mocks.useIncidentActions.mockReturnValue(actionsData());
  });

  it("la tira de KPIs cuenta sobre el TOTAL y declara cuántas se muestran", () => {
    render(page());
    expect(screen.getByTestId("kpi-strip")).toBeInTheDocument();
    expect(screen.getByTestId("kpi-showing")).toHaveTextContent("MOSTRANDO 2 DE 2");
  });

  it("OCULTAR SIN ENLACE quita la estación del MAPA pero NO del semáforo", () => {
    render(page());
    const sitesOf = (call: number): MapSiteState[] =>
      (mocks.MapPanel.mock.calls[call][0] as unknown as { sites: MapSiteState[] }).sites;
    expect(sitesOf(0).map((s) => s.site_id)).toEqual(["s-up", "s-down"]);

    fireEvent.click(screen.getByTestId("hide-no-link"));
    const last = mocks.MapPanel.mock.calls.length - 1;
    expect(sitesOf(last).map((s) => s.site_id)).toEqual(["s-up"]);
    // El semáforo sigue contando las dos: el filtro no puede esconder el problema.
    expect(screen.getByTestId("kpi-showing")).toHaveTextContent("MOSTRANDO 1 DE 2");
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

/**
 * [T-2.64.c / F3] La costura entre el MARCADO y la HOJA.
 *
 * La corrección que le devolvió 408 px de mapa a la consola está partida en dos
 * mitades: la regla `.soc-shell[data-detail="open"]` de `soc.css` y el atributo
 * que la enciende, que vive en UN solo sitio (`ConsolePage.tsx:184`).
 * `src/styles/layoutInvariants.test.ts` vigila la primera, pero solo lee el TEXTO
 * de la hoja: nunca renderiza el componente. Nadie assertaba la segunda — el
 * auditor borró la línea del atributo y los 1159 tests de web siguieron VERDES.
 *
 * Sin atributo, `.soc-shell` se queda en una sola columna y `<DetailPanel>`
 * —hijo DIRECTO del shell— cae fuera de su pista: el resultado es peor que el
 * bug original, que al menos reservaba la columna.
 *
 * `cssContract.test.ts` no lo cubre y no puede: cruza marcado↔hoja por
 * `className`, y los atributos `data-*` quedan fuera de ese contrato.
 */
describe("costura marcado↔hoja: el interruptor `data-detail` (T-2.64.c)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetSessionStoreForTests();
    useSessionStore.setState({ status: "authenticated", idToken: "tok" });
    mocks.useLiveIncidents.mockReturnValue(incidentsData());
    mocks.useMapState.mockReturnValue(mapData());
    mocks.useSiteFeatures.mockReturnValue(featuresData());
    mocks.useIncidentActions.mockReturnValue(actionsData());
  });

  function shell(container: HTMLElement): HTMLElement {
    const el = container.querySelector<HTMLElement>(".soc-shell");
    if (el === null) throw new Error("no hay .soc-shell en el árbol renderizado");
    return el;
  }

  /**
   * La reja y el panel salen de UNA sola condición (`detailVisible`,
   * ConsolePage.tsx:135). Este BICONDICIONAL es lo que caza que vuelvan a
   * separarse: no comprueba un valor concreto, comprueba que los dos consumidores
   * digan lo mismo. Las dos divergencias posibles son daño real —pista abierta
   * sin panel dentro (408 px de mapa regalados) o panel montado sin pista (cae
   * fuera de la reja)— y se afirma en los TRES estados alcanzables de la página.
   */
  function expectRejaYPanelDeAcuerdo(container: HTMLElement): void {
    const emitido = shell(container).getAttribute("data-detail");
    const montado = screen.queryByTestId("detail-panel") !== null;
    expect(
      emitido,
      'el shell no emite `data-detail`: la regla `.soc-shell[data-detail="open"]` no se enciende nunca',
    ).not.toBeNull();
    expect(
      emitido,
      montado
        ? "hay <DetailPanel> montado pero la reja no abrió su pista: el panel cae fuera de la columna"
        : "la reja abre la pista del detalle sin panel que meter dentro: 408 px de mapa regalados",
    ).toBe(montado ? "open" : "closed");
  }

  it("por defecto NO hay panel y el shell lo declara: `closed`", () => {
    const { container } = render(page());
    expect(screen.queryByTestId("detail-panel")).toBeNull();
    expect(shell(container).getAttribute("data-detail")).toBe("closed");
    expectRejaYPanelDeAcuerdo(container);
  });

  it("enfocar un sitio abre la pista, y cerrar el panel la devuelve", () => {
    const { container } = render(page());
    fireEvent.click(screen.getByText("pick-site"));
    expect(screen.getByTestId("detail-panel")).toBeInTheDocument();
    expect(shell(container).getAttribute("data-detail")).toBe("open");
    expectRejaYPanelDeAcuerdo(container);

    fireEvent.click(screen.getByRole("button", { name: "Cerrar" }));
    expect(shell(container).getAttribute("data-detail")).toBe("closed");
    expectRejaYPanelDeAcuerdo(container);
  });

  it("el shell abierto casa con el selector LITERAL de la hoja y el panel es hijo DIRECTO", () => {
    const { container } = render(page());
    fireEvent.click(screen.getByText("pick-site"));
    // El selector va escrito igual que en `soc.css` (base y ambas @media). Un
    // `data-detail="opened"`, o el atributo colgado de otro elemento, dejaría la
    // regla (0,2,0) sin aplicar y la segunda pista no se abriría jamás — y el
    // test del valor por sí solo no lo vería.
    expect(
      container.querySelector('.soc-shell[data-detail="open"] > .soc-detail'),
      'el marcado no satisface `.soc-shell[data-detail="open"] > .soc-detail`',
    ).not.toBeNull();
    // Hijo DIRECTO, no descendiente: envolver el panel en un <div> lo sacaría de
    // la reja (y de `.soc-shell > .soc-detail`, que bajo 1280 lo convierte en
    // cajón fijo) sin que ninguna aserción de valor se enterara.
    expect(screen.getByTestId("detail-panel").parentElement).toBe(shell(container));
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
          manage_retire_code: false,
          manage_users: false,
          // Acciones de la superficie móvil (T-2.03): inertes en la consola.
          panel_read: false,
          checkin_submit: false,
          damage_report_submit: false,
          dictamen_read: false,
          enrollment_manage: false,
          evidence_upload: false,
          manual_activate: false,
          panic_vote: false,
          roster_read: false,
          siren_silence: false,
          maintenance_window: false,
          platform_maintenance_window: false,
          deploy_firmware: false,
          manage_privacy_notice: false,
          manage_privacy_erasure: false,
          cctv_read: false,
          cctv_video: false,
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
