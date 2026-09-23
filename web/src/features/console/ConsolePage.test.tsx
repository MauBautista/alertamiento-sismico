import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter, RouterProvider, createMemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { MapSiteState } from "@takab/sdk";

import { resetSessionStoreForTests, useSessionStore } from "../../auth/session.store";
import { ME_FIXTURES } from "../../test-utils/meFixtures";
import { expectFourStates, type UiState } from "../../test-utils/states";
import type { IncidentActionsData } from "./useIncidentActions";
import type { LiveIncident, LiveIncidentsData } from "./useLiveIncidents";
import type { MapStateData } from "./useMapState";
import type { ShakemapOut } from "./shakemap";
import type { ShakemapData } from "./useShakemap";
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
  useShakemap: vi.fn(),
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
vi.mock("./useShakemap", () => ({ useShakemap: mocks.useShakemap }));
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
// [T-8.07] El picker real es MapLibre: el modal de REUBICAR se monta con un stub.
vi.mock("../fleet/MapPointPicker", () => ({
  default: () => <div data-testid="picker-stub" />,
}));
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

/** [T-7.24] El mapa de la sacudida del incidente enfocado. Inerte por defecto. */
function shakemapData(over: Partial<ShakemapData> = {}): ShakemapData {
  return { data: null, loading: false, error: false, updatedAt: 0, refetch: vi.fn(), ...over };
}

const SHAKEMAP: ShakemapOut = {
  incident_id: "i-1",
  estado: "completo",
  calculado_en: "2026-09-14T10:41:30Z",
  ley: "ATTEN-LAW v1",
  cobertura_km: 25,
  epicentro: null,
  // El contrato los declara SIEMPRE presentes (vacíos incluidos): un fixture que
  // omita uno dejaría de parecerse a lo que la nube manda de verdad.
  fuera_de_alcance: [],
  observado: { type: "FeatureCollection", features: [] },
  modelado: null,
};

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
          demo_mode_on: false,
          demo_mode_off: false,
          classify_incident: false,
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
    mocks.useShakemap.mockReturnValue(shakemapData());
  });

  // [T-7.24] EL CAMINO COMPLETO DEL MAPA DE LA SACUDIDA. `mapPanelAlimentado`
  // vigila que la prop se ESCRIBA; esto vigila que lo que se escribe sea el
  // snapshot del incidente enfocado y no un hueco.
  describe("[T-7.24] el mapa de la sacudida llega al panel", () => {
    function propsDelMapa(): Record<string, unknown> {
      const llamadas = mocks.MapPanel.mock.calls;
      expect(llamadas.length, "MapPanel no se montó").toBeGreaterThan(0);
      return llamadas[llamadas.length - 1][0] as Record<string, unknown>;
    }

    it("se consulta el mapa DEL INCIDENTE enfocado y se le pasa al panel", () => {
      mocks.useShakemap.mockReturnValue(shakemapData({ data: SHAKEMAP }));
      render(page());
      expect(mocks.useShakemap).toHaveBeenCalledWith("i-1");
      expect(propsDelMapa()["shakemap"]).toBe(SHAKEMAP);
      expect(propsDelMapa()["shakemapError"]).toBe(false);
    });

    it("el error y la espera de la consulta LLEGAN al panel; no se quedan en el hook", () => {
      // Sin esto el panel no puede declarar ninguno de los dos y los dos se ven
      // como «este incidente no tiene mapa» (regla de oro 7).
      mocks.useShakemap.mockReturnValue(shakemapData({ error: true }));
      const { unmount } = render(page());
      expect(propsDelMapa()["shakemapError"]).toBe(true);
      expect(propsDelMapa()["shakemap"]).toBeUndefined();
      unmount();

      mocks.useShakemap.mockReturnValue(shakemapData({ loading: true }));
      render(page());
      expect(propsDelMapa()["shakemapLoading"]).toBe(true);
    });

    it("sin incidente enfocado no se consulta ningún mapa", () => {
      mocks.useLiveIncidents.mockReturnValue(incidentsData({ incidents: [] }));
      render(page());
      expect(mocks.useShakemap).toHaveBeenCalledWith(null);
    });
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

  it("[A-063] un umbral local que la RED corroboró es alerta en el muro, como en el teléfono", () => {
    mocks.useMapState.mockReturnValue(
      mapData({
        epicenters: [
          {
            event_id: "EVT-1041",
            source: "quorum",
            detected_at: "2026-07-08T10:41:30Z",
            lat: 19.06,
            lon: -98.3,
            depth_km: null,
            magnitude: null,
            node_count: 3,
          },
        ],
      }),
    );
    render(page());
    const tarjeta = screen.getByTestId("alert-banner");
    expect(tarjeta).toHaveAttribute("data-kind", "alert");
    expect(tarjeta).toHaveAttribute("data-authorizes", "true");
    expect(tarjeta).not.toHaveTextContent("SOLO AVISO, SIN ACTUACIÓN");
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
    // [T-8.07] Es una mutación de verdad: la petición sale en el siguiente tic,
    // no dentro del clic.
    await waitFor(() =>
      expect(mocks.ackIncidentIncidentsIncidentIdAckPost).toHaveBeenCalledWith({
        path: { incident_id: "i-1" },
      }),
    );
  });

  // [A-011 · T-8.07] El acuse se lanzaba SIN esperar respuesta: el cliente
  // hey-api no lanza con un 4xx, así que un 409 «ya no está abierto» o un 403 se
  // tragaban, y el botón pintaba «EJECUTADO» igual.
  it("[A-011] un acuse que el servidor RECHAZA no se pinta como hecho: dice qué pasó", async () => {
    mocks.ackIncidentIncidentsIncidentIdAckPost.mockResolvedValue({
      data: undefined,
      error: { detail: "el incidente ya no está abierto" },
      response: { status: 409 },
    });
    render(page());
    fireEvent.click(screen.getByRole("button", { name: /CONFIRMAR ACUSE/ }));
    fireEvent.click(await screen.findByRole("button", { name: /CLIC DE NUEVO PARA ACUSAR/ }));
    const error = await screen.findByTestId("ack-error");
    expect(error).toHaveAttribute("role", "alert");
    expect(error).toHaveTextContent("409");
    expect(error).toHaveTextContent("el incidente ya no está abierto");
    expect(screen.queryByText("ACUSADO", { selector: "button *" })).toBeNull();
    expect(screen.queryByText("EJECUTADO")).toBeNull();
    // Y el botón vuelve a reposo: se puede reintentar.
    expect(await screen.findByRole("button", { name: /CONFIRMAR ACUSE/ })).toBeEnabled();
  });

  it("[A-011] ACUSADO solo tras la respuesta 2xx; en vuelo, ENVIANDO… y sin doble envío", async () => {
    let responder!: (v: unknown) => void;
    mocks.ackIncidentIncidentsIncidentIdAckPost.mockReturnValue(
      new Promise((resolve) => {
        responder = resolve;
      }),
    );
    render(page());
    fireEvent.click(screen.getByRole("button", { name: /CONFIRMAR ACUSE/ }));
    fireEvent.click(await screen.findByRole("button", { name: /CLIC DE NUEVO PARA ACUSAR/ }));
    const enVuelo = await screen.findByRole("button", { name: /ENVIANDO/ });
    expect(enVuelo).toBeDisabled();
    fireEvent.click(enVuelo);
    expect(mocks.ackIncidentIncidentsIncidentIdAckPost).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("ACUSADO", { selector: "button *" })).toBeNull();
    await act(async () => {
      responder({ data: { incident_id: "i-1", state: "acked" }, response: { status: 200 } });
      await Promise.resolve();
    });
    expect(await screen.findByText("ACUSADO", { selector: "button *" })).toBeInTheDocument();
    expect(screen.queryByTestId("ack-error")).toBeNull();
  });

  it("[T-6.06] el vacío culpa al ALCANCE cuando el servidor lo está imponiendo", () => {
    // El defecto que esto cierra solo se ve el día del apply de `T-2.89`: un
    // operador con cero estaciones asignadas leía «SIN SITIOS VISIBLES EN EL
    // TENANT» sobre un cliente con veintiuna — falso, y encima le mandaba a
    // preguntar por su cliente en vez de a pedir el alta de sus estaciones.
    useSessionStore.setState({
      me: {
        ...useSessionStore.getState().me!,
        site_scope: [],
        console_scope_enforced: true,
      },
    });
    mocks.useMapState.mockReturnValue(mapData({ sites: [] }));
    render(page());
    expect(screen.getByText(/SU CUENTA NO TIENE ESTACIONES ASIGNADAS/)).toBeInTheDocument();
    expect(screen.queryByText(/EN EL TENANT/)).toBeNull();
  });

  it("[T-6.06] con alcance impuesto y estaciones, el vacío dice CUÁNTAS", () => {
    useSessionStore.setState({
      me: {
        ...useSessionStore.getState().me!,
        site_scope: ["s-1", "s-2"],
        console_scope_enforced: true,
      },
    });
    mocks.useMapState.mockReturnValue(mapData({ sites: [] }));
    render(page());
    expect(
      screen.getByText("SIN SITIOS VISIBLES EN SU ALCANCE (2 ESTACIONES)"),
    ).toBeInTheDocument();
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

/**
 * [T-7.05 · C-1] La otra mitad de la partición de la columna derecha.
 *
 * La regla `.soc-stage[data-alert="true"]` de `soc.css` resta la reserva de la
 * alerta al tope de las leyendas, y `src/styles/layoutInvariants.test.ts` vigila esa
 * aritmética. Pero sólo lee el TEXTO de la hoja: si el atributo no se emite —o se
 * emite con otro valor, o colgado de otro elemento— la regla no se enciende NUNCA y
 * la tarjeta vuelve a caer encima de la botonera de CAPAS (74 160 px² medidos por el
 * censo de T-7.04) sin que una sola aserción se entere. Es exactamente el agujero
 * que T-2.64.c dejó abierto con `data-detail` y que este fichero cerró.
 *
 * El bicondicional es lo que se afirma: el atributo y la tarjeta montada salen de la
 * MISMA condición (`critical`, ConsolePage.tsx), y las dos divergencias posibles son
 * daño real — reserva puesta sin tarjeta (las leyendas pierden 240 px de banda para
 * nada) o tarjeta sin reserva (vuelve el solape de C-1).
 */
describe("costura marcado↔hoja: el interruptor `data-alert` (T-7.05)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetSessionStoreForTests();
    useSessionStore.setState({ status: "authenticated", idToken: "tok" });
    mocks.useLiveIncidents.mockReturnValue(incidentsData());
    mocks.useMapState.mockReturnValue(mapData());
    mocks.useSiteFeatures.mockReturnValue(featuresData());
    mocks.useIncidentActions.mockReturnValue(actionsData());
  });

  function stage(container: HTMLElement): HTMLElement {
    const el = container.querySelector<HTMLElement>(".soc-stage");
    if (el === null) throw new Error("no hay .soc-stage en el árbol renderizado");
    return el;
  }

  function expectReservaYTarjetaDeAcuerdo(container: HTMLElement): void {
    const emitido = stage(container).getAttribute("data-alert");
    const montada = screen.queryByTestId("alert-banner") !== null;
    expect(
      emitido,
      'el escenario no emite `data-alert`: la regla `.soc-stage[data-alert="true"]` no se enciende nunca',
    ).not.toBeNull();
    expect(
      emitido,
      montada
        ? "hay tarjeta de alerta y las leyendas NO le restan su banda: vuelve el solape de C-1"
        : "el escenario reserva la banda de la alerta sin tarjeta que meter dentro: 240 px de leyendas a cambio de nada",
    ).toBe(montada ? "true" : "false");
  }

  it("con incidente crítico el escenario declara la reserva: `true`", () => {
    const { container } = render(page());
    expect(screen.getByTestId("alert-banner")).toBeInTheDocument();
    expect(stage(container).getAttribute("data-alert")).toBe("true");
    expectReservaYTarjetaDeAcuerdo(container);
  });

  it("sin incidente que abra escena de alerta, las leyendas recuperan su columna", () => {
    mocks.useLiveIncidents.mockReturnValue(incidentsData({ incidents: [] }));
    const { container } = render(page());
    expect(screen.queryByTestId("alert-banner")).toBeNull();
    expect(stage(container).getAttribute("data-alert")).toBe("false");
    expectReservaYTarjetaDeAcuerdo(container);
  });

  it("un incidente que NO define escena de alerta tampoco reserva banda", () => {
    // `sceneAlert` elige el incidente crítico abierto: un `warning` no viste la
    // tarjeta y por tanto no puede robarle alto a las leyendas.
    mocks.useLiveIncidents.mockReturnValue(
      incidentsData({ incidents: [{ ...INCIDENT, severity: "warning" }] }),
    );
    const { container } = render(page());
    expectReservaYTarjetaDeAcuerdo(container);
    expect(stage(container).getAttribute("data-alert")).toBe("false");
  });

  it("el marcado casa con el selector LITERAL de la hoja", () => {
    const { container } = render(page());
    // Escrito igual que en `soc.css`. Un `data-alert="on"`, o el atributo en el
    // `.soc-wall` en vez de en el escenario, dejaría la regla (0,2,0) sin aplicar
    // y ni el test del valor ni el de la hoja lo verían.
    expect(
      container.querySelector('.soc-stage[data-alert="true"] > .soc-stage__overlays > .soc-alert'),
      'el marcado no satisface `.soc-stage[data-alert="true"] > .soc-stage__overlays`',
    ).not.toBeNull();
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
          demo_mode_on: false,
          demo_mode_off: false,
          classify_incident: false,
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
    const router = createMemoryRouter(
      [
        { path: "/console", element: <ConsolePage /> },
        { path: "/triage", element: <div data-testid="triage-probe" /> },
      ],
      { initialEntries: ["/console"] },
    );
    render(
      <QueryClientProvider client={client}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: /SOLICITAR DICTAMEN TÉCNICO/ }));
    fireEvent.click(await screen.findByRole("button", { name: /CLIC DE NUEVO PARA SOLICITAR/ }));

    expect(await screen.findByTestId("triage-probe")).toBeInTheDocument();
    expect(mocks.requestDictamenIncidentsIncidentIdDictamenRequestPost).toHaveBeenCalledWith(
      expect.objectContaining({ path: { incident_id: "i-1" } }),
    );
    // [T-6.14] Y se lleva PUESTO el camino de vuelta. Solicitar el dictamen
    // salta de pantalla y tira el riel, el mapa y el filtro; sin este `volver`,
    // el operador termina en triage y regresa a una consola en blanco que tiene
    // que volver a armar a mano. El sitio es el del incidente por el que se
    // saltó: es el que estaba mirando.
    expect(router.state.location.search).toContain("incident=i-1");
    expect(router.state.location.search).toContain("volver=s-1");
  });

  it("`?sitio=` devuelve el riel abierto en ESE sitio", () => {
    // La otra mitad del viaje: la vuelta desde triage es un enlace normal, y
    // esta página tiene que saber leerlo. Sin esto, «volver» aterrizaría en la
    // consola con el riel cerrado y el operador tendría que buscar su estación
    // en el mapa otra vez.
    mocks.useLiveIncidents.mockReturnValue(incidentsData({ incidents: [] }));
    mocks.useMapState.mockReturnValue(mapData());
    mocks.useSiteFeatures.mockReturnValue(featuresData());
    mocks.useIncidentActions.mockReturnValue(actionsData());

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter initialEntries={["/console?sitio=s-1"]}>
        <QueryClientProvider client={client}>
          <ConsolePage />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    const panel = screen.getByTestId("detail-panel");
    expect(panel).toBeInTheDocument();
    expect(panel).toHaveTextContent("Planta Cholula");
  });

  it("sin `?sitio=` el riel sigue naciendo cerrado", () => {
    // El deep-link no puede convertirse en el comportamiento por defecto: el
    // wall es un mapa, y un cajón abierto de arranque le come 380 px.
    mocks.useLiveIncidents.mockReturnValue(incidentsData({ incidents: [] }));
    mocks.useMapState.mockReturnValue(mapData());
    mocks.useSiteFeatures.mockReturnValue(featuresData());
    mocks.useIncidentActions.mockReturnValue(actionsData());
    render(page());
    expect(screen.queryByTestId("detail-panel")).not.toBeInTheDocument();
  });
});

// [A-012 · T-8.07] La selección de la cola era por SITIO: el clic en una fila
// guardaba el `site_id` y el incidente enfocado salía de `find` por sitio — el
// PRIMERO. Con dos abiertos en el mismo edificio (pánico + sísmico) la segunda
// fila no se podía elegir y el acuse, la reubicación y el dictamen caían en la
// primera.
describe("[A-012 · T-8.07] la selección de la cola es por INCIDENTE", () => {
  const SEGUNDO: LiveIncident = {
    ...INCIDENT,
    incident_id: "i-2",
    severity: "warning",
    trigger: "panic",
    event_id: null,
    max_pga_g: 0.05,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    // El rol principal de la consola, con la /me DERIVADA de la matriz: acusa,
    // reubica y pide dictamen.
    resetSessionStoreForTests();
    useSessionStore.setState({
      status: "authenticated",
      idToken: "tok",
      me: ME_FIXTURES.soc_operator,
    });
    mocks.useLiveIncidents.mockReturnValue(incidentsData({ incidents: [INCIDENT, SEGUNDO] }));
    mocks.useMapState.mockReturnValue(mapData());
    mocks.useSiteFeatures.mockReturnValue(featuresData());
    mocks.useIncidentActions.mockReturnValue(actionsData());
    mocks.useShakemap.mockReturnValue(shakemapData());
    mocks.ackIncidentIncidentsIncidentIdAckPost.mockResolvedValue({
      data: { incident_id: "i-2", state: "acked" },
      response: { status: 200 },
    });
    mocks.requestDictamenIncidentsIncidentIdDictamenRequestPost.mockResolvedValue({
      data: { action_id: "a-9", incident_id: "i-2", kind: "dictamen_request" },
      response: { status: 201 },
    });
  });

  function elegirSegundo(): HTMLElement {
    const fila = screen.getByText("0.050g").closest("tr") as HTMLElement;
    fireEvent.click(fila);
    return fila;
  }

  it("la segunda fila del MISMO sitio se puede elegir", () => {
    render(page());
    const fila = elegirSegundo();
    expect(fila).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("0.150g").closest("tr")).toHaveAttribute("aria-selected", "false");
  });

  it("el acuse cae en el incidente ELEGIDO, no en el primero del sitio", async () => {
    render(page());
    elegirSegundo();
    fireEvent.click(screen.getByRole("button", { name: /CONFIRMAR ACUSE/ }));
    fireEvent.click(await screen.findByRole("button", { name: /CLIC DE NUEVO PARA ACUSAR/ }));
    await waitFor(() =>
      expect(mocks.ackIncidentIncidentsIncidentIdAckPost).toHaveBeenCalledWith({
        path: { incident_id: "i-2" },
      }),
    );
  });

  it("REUBICAR abre el modal del incidente ELEGIDO", () => {
    render(page());
    elegirSegundo();
    fireEvent.click(screen.getByRole("button", { name: /REUBICAR EPICENTRO/ }));
    const dialogo = screen.getByRole("dialog", { name: "REUBICAR EPICENTRO" });
    expect(dialogo).toHaveTextContent("i-2");
    expect(dialogo).not.toHaveTextContent("i-1");
  });

  it("SOLICITAR DICTAMEN va por el incidente ELEGIDO", async () => {
    render(page());
    elegirSegundo();
    fireEvent.click(screen.getByRole("button", { name: /SOLICITAR DICTAMEN TÉCNICO/ }));
    fireEvent.click(await screen.findByRole("button", { name: /CLIC DE NUEVO PARA SOLICITAR/ }));
    await waitFor(() =>
      expect(mocks.requestDictamenIncidentsIncidentIdDictamenRequestPost).toHaveBeenCalledWith(
        expect.objectContaining({ path: { incident_id: "i-2" } }),
      ),
    );
  });

  it("el panel de detalle habla del incidente ELEGIDO", () => {
    render(page());
    elegirSegundo();
    expect(mocks.useIncidentActions).toHaveBeenLastCalledWith("i-2");
  });
});

// [A-013 · T-8.07] El Modal le robaba el foco al campo CADA SEGUNDO en /console:
// el wall se redibuja con `useNow(1000)` y le pasa al modal un `onClose` nuevo en
// cada tic. Se mide sobre la página de verdad, con su reloj.
describe("[A-013 · T-8.07] se puede teclear en un modal de la consola", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetSessionStoreForTests();
    useSessionStore.setState({
      status: "authenticated",
      idToken: "tok",
      me: ME_FIXTURES.soc_operator,
    });
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mocks.useLiveIncidents.mockReturnValue(incidentsData());
    mocks.useMapState.mockReturnValue(mapData());
    mocks.useSiteFeatures.mockReturnValue(featuresData());
    mocks.useIncidentActions.mockReturnValue(actionsData());
    mocks.useShakemap.mockReturnValue(shakemapData());
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("la NOTA de REUBICAR conserva el foco aunque el wall se redibuje", () => {
    render(page());
    fireEvent.click(screen.getByRole("button", { name: /REUBICAR EPICENTRO/ }));
    const nota = screen.getByLabelText(/NOTA \(OPCIONAL/);
    nota.focus();
    expect(nota).toHaveFocus();
    act(() => {
      vi.advanceTimersByTime(3_000);
    });
    expect(nota).toHaveFocus();
  });
});
