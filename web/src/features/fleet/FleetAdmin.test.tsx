import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { SiteOut } from "@takab/sdk";

import { resetSessionStoreForTests, useSessionStore } from "../../auth/session.store";
import { ME_FIXTURES, TENANT_ID } from "../../test-utils/meFixtures";

const mocks = vi.hoisted(() => ({
  listSitesSitesGet: vi.fn(),
  // [T-6.03] El alta pregunta en qué clientes puede escribir (y el nombre del propio).
  listTenantsTenantsGet: vi.fn(),
  listGatewaysFleetGatewaysGet: vi.fn(),
  listRuleSetsRuleSetsGet: vi.fn(),
  createSiteSitesPost: vi.fn(),
  updateSiteSitesSiteIdPut: vi.fn(),
  retireSiteSitesSiteIdRetirePost: vi.fn(),
  getRetireCodeStateTenantsTenantIdRetireCodeGet: vi.fn(),
  createGatewayFleetGatewaysPost: vi.fn(),
  createSensorSensorsPost: vi.fn(),
  listEnrollmentCodesSitesSiteIdEnrollmentCodesGet: vi.fn(),
  createEnrollmentCodeSitesSiteIdEnrollmentCodesPost: vi.fn(),
  deactivateEnrollmentCodeSitesSiteIdEnrollmentCodesCodeDelete: vi.fn(),
}));

vi.mock("@takab/sdk", () => mocks);
// El picker monta MapLibre, que jsdom no soporta; su comportamiento se prueba aparte.
vi.mock("./MapPointPicker", () => ({
  default: ({ value }: { value: { lat: number; lon: number } }) => (
    <div data-testid="map-point-picker">{`${value.lat},${value.lon}`}</div>
  ),
}));

import FleetAdmin from "./FleetAdmin";

const SITE: SiteOut = {
  site_id: "s-1",
  // [T-6.03] El del tenant_admin sembrado: la tabla y el rótulo buscan su NOMBRE por id.
  tenant_id: TENANT_ID,
  code: "CHL-A",
  name: "Planta Cholula",
  timezone: "America/Mexico_City",
  criticality: "high",
  lat: 19.06,
  lon: -98.3,
  address: null,
  building_type: null,
  status: "active",
  row_version: "8421",
  created_at: "2026-01-01T00:00:00Z",
};

const GATEWAY_ROW = {
  gateway_id: "g-new",
  tenant_id: "t-1",
  site_id: "s-1",
  serial: "TKB-0007",
  fw_version: null,
  iot_thing: "gw-dev-0007",
  status: "provisioned",
  has_wr1: true,
  equipment: {
    siren: true,
    strobe: true,
    gas_valve: true,
    elevator: true,
    door_retainer: true,
  },
  installed_at: null,
  row_version: "1",
};

/** Clientes visibles: para tenant_admin la RLS devuelve sólo el suyo; el superadmin ve dos. */
const TENANT_OWN = {
  tenant_id: ME_FIXTURES.tenant_admin.tenant_id,
  code: "IDV",
  name: "Industrias del Valle",
  isolation_mode: "logical",
  vertical: null,
  visibility: "private",
  status: "active",
  plan_code: "mvp",
  row_version: "1",
  created_at: "2026-01-01T00:00:00Z",
};
const TENANT_OTHER = { ...TENANT_OWN, tenant_id: "t-hosp", code: "HOSP-1", name: "Hospital Uno" };

// [T-6.03] `FleetAdmin` lee `?tenant=&nueva=` de la URL: hace falta un router.
function renderAdmin(path = "/fleet") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <FleetAdmin />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("FleetAdmin", () => {
  beforeEach(() => {
    resetSessionStoreForTests();
    vi.clearAllMocks();
    mocks.listSitesSitesGet.mockResolvedValue({ data: [SITE], response: { status: 200 } });
    mocks.listGatewaysFleetGatewaysGet.mockResolvedValue({ data: [], response: { status: 200 } });
    mocks.listRuleSetsRuleSetsGet.mockResolvedValue({
      data: { items: [] },
      response: { status: 200 },
    });
    // [T-2.36] El diálogo consulta si el cliente tiene código configurado.
    mocks.getRetireCodeStateTenantsTenantIdRetireCodeGet.mockResolvedValue({
      data: { tenant_id: "t-1", configured: true, version: 1, rotated_at: "2026-08-03T00:00:00Z" },
      response: { status: 200 },
    });
    mocks.listTenantsTenantsGet.mockResolvedValue({
      data: [TENANT_OWN],
      response: { status: 200 },
    });
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.tenant_admin });
  });

  it("sin manage_fleet la superficie de escritura no existe", async () => {
    // soc_operator ve la flota pero no la administra. Pintarle un botón que siempre
    // daría 403 es exactamente lo que prohíbe la regla de oro 7.
    useSessionStore.setState({ me: ME_FIXTURES.soc_operator });
    renderAdmin();
    expect(screen.queryByTestId("fleet-admin")).toBeNull();
  });

  it("takab_support tampoco: lee la flota, no la mueve", () => {
    useSessionStore.setState({ me: ME_FIXTURES.takab_support });
    renderAdmin();
    expect(screen.queryByTestId("fleet-admin")).toBeNull();
  });

  it("tenant_admin lista sus estaciones con su ubicación", async () => {
    renderAdmin();
    expect(await screen.findByTestId("site-row-CHL-A")).toBeInTheDocument();
    expect(screen.getByText("19.0600°N · 98.3000°W")).toBeInTheDocument();
  });

  it("tenant_admin: crear una estación envía lat/lon, NO envía tenant_id y el rótulo dice su cliente", async () => {
    mocks.createSiteSitesPost.mockResolvedValue({ data: SITE, response: { status: 201 } });
    renderAdmin();
    await screen.findByTestId("site-row-CHL-A");

    fireEvent.click(screen.getByRole("button", { name: "NUEVA ESTACIÓN" }));
    // [T-6.03] Declara SIEMPRE en qué cliente escribe, y un rol de cliente no elige.
    expect(await screen.findByText("Industrias del Valle")).toBeInTheDocument();
    expect(screen.getByTestId("site-form-target")).toHaveTextContent("ESCRIBIENDO EN");
    expect(screen.queryByTestId("site-form-tenant")).toBeNull();
    fireEvent.change(screen.getByLabelText("CÓDIGO"), { target: { value: "NUEVA" } });
    fireEvent.change(screen.getByLabelText("NOMBRE"), { target: { value: "Torre Norte" } });
    fireEvent.click(screen.getByRole("button", { name: "CREAR ESTACIÓN" }));

    await waitFor(() => expect(mocks.createSiteSitesPost).toHaveBeenCalledTimes(1));
    const body = mocks.createSiteSitesPost.mock.calls[0][0].body;
    expect(body).toMatchObject({ code: "NUEVA", name: "Torre Norte", lat: 19.04, lon: -98.2 });
    // El tenant lo resuelve el servidor desde los claims: mandarlo sería una invitación.
    expect(body).not.toHaveProperty("tenant_id");
  });

  // [T-6.03] El defecto U-06, medido en vivo el 2026-09-07: el superadmin recibía un
  // 400 «tenant_id es obligatorio para roles internos TAKAB» que la consola traducía
  // como «NO COINCIDE · el identificador…» (el mensaje del retiro). No podía crear
  // un sitio, y nada le decía por qué.
  it("superadmin: elige el cliente y ese tenant_id viaja en el cuerpo", async () => {
    useSessionStore.setState({ me: ME_FIXTURES.takab_superadmin });
    mocks.listTenantsTenantsGet.mockResolvedValue({
      data: [TENANT_OWN, TENANT_OTHER],
      response: { status: 200 },
    });
    mocks.createSiteSitesPost.mockResolvedValue({ data: SITE, response: { status: 201 } });
    renderAdmin();
    await screen.findByTestId("site-row-CHL-A");
    expect(screen.getByText("ESTACIONES · TODOS LOS CLIENTES")).toBeInTheDocument();
    // Y la tabla dice de quién es cada fila.
    expect(await screen.findByTestId("site-tenant-CHL-A")).toHaveTextContent(
      "Industrias del Valle",
    );

    fireEvent.click(screen.getByRole("button", { name: "NUEVA ESTACIÓN" }));
    fireEvent.change(screen.getByLabelText("CÓDIGO"), { target: { value: "NUEVA" } });
    fireEvent.change(screen.getByLabelText("NOMBRE"), { target: { value: "Torre Norte" } });
    const submit = screen.getByRole("button", { name: "CREAR ESTACIÓN" });
    expect(submit).toBeDisabled(); // sin cliente no hay alta: sería el 400
    const selector = await screen.findByTestId("site-form-tenant");
    await waitFor(() => expect(selector).not.toBeDisabled());
    fireEvent.change(selector, { target: { value: "t-hosp" } });
    expect(screen.getByTestId("site-form-target")).toHaveTextContent(
      "ESCRIBIENDO EN · Hospital Uno",
    );
    fireEvent.click(submit);

    await waitFor(() => expect(mocks.createSiteSitesPost).toHaveBeenCalledTimes(1));
    expect(mocks.createSiteSitesPost.mock.calls[0][0].body).toMatchObject({
      code: "NUEVA",
      tenant_id: "t-hosp",
    });
  });

  it("superadmin: llegar con ?tenant=&nueva=1 abre el alta ya apuntada al cliente", async () => {
    useSessionStore.setState({ me: ME_FIXTURES.takab_superadmin });
    mocks.listTenantsTenantsGet.mockResolvedValue({
      data: [TENANT_OWN, TENANT_OTHER],
      response: { status: 200 },
    });
    renderAdmin("/fleet?tenant=t-hosp&nueva=1");
    expect(await screen.findByTestId("site-form")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByTestId("site-form-target")).toHaveTextContent("Hospital Uno"),
    );
    expect(screen.getByTestId("site-form-tenant")).toHaveValue("t-hosp");
  });

  it("un 400 del alta ya no se disfraza de retiro: llega el detail del servidor", async () => {
    mocks.createSiteSitesPost.mockResolvedValue({
      data: undefined,
      error: { detail: "tenant_id es obligatorio para roles internos TAKAB" },
      response: { status: 400 },
    });
    renderAdmin();
    await screen.findByTestId("site-row-CHL-A");
    fireEvent.click(screen.getByRole("button", { name: "NUEVA ESTACIÓN" }));
    fireEvent.change(screen.getByLabelText("CÓDIGO"), { target: { value: "X" } });
    fireEvent.change(screen.getByLabelText("NOMBRE"), { target: { value: "X" } });
    fireEvent.click(screen.getByRole("button", { name: "CREAR ESTACIÓN" }));

    const error = await screen.findByTestId("site-form-error");
    expect(error).toHaveTextContent(/PETICIÓN RECHAZADA/);
    expect(error).toHaveTextContent(/tenant_id es obligatorio para roles internos TAKAB/);
    expect(error).not.toHaveTextContent(/NO COINCIDE/);
  });

  it("editar envía base_row_version para que el servidor detecte el lost update", async () => {
    mocks.updateSiteSitesSiteIdPut.mockResolvedValue({ data: SITE, response: { status: 200 } });
    renderAdmin();
    await screen.findByTestId("site-row-CHL-A");

    fireEvent.click(screen.getByRole("button", { name: "EDITAR" }));
    fireEvent.change(screen.getByLabelText("NOMBRE"), { target: { value: "Planta Cholula B" } });
    fireEvent.click(screen.getByRole("button", { name: "GUARDAR CAMBIOS" }));

    await waitFor(() => expect(mocks.updateSiteSitesSiteIdPut).toHaveBeenCalledTimes(1));
    const call = mocks.updateSiteSitesSiteIdPut.mock.calls[0][0];
    expect(call.path).toEqual({ site_id: "s-1" });
    expect(call.body.base_row_version).toBe("8421");
  });

  it("un 409 se explica en castellano, no como 'algo salió mal'", async () => {
    mocks.createSiteSitesPost.mockResolvedValue({ data: undefined, response: { status: 409 } });
    renderAdmin();
    await screen.findByTestId("site-row-CHL-A");

    fireEvent.click(screen.getByRole("button", { name: "NUEVA ESTACIÓN" }));
    fireEvent.change(screen.getByLabelText("CÓDIGO"), { target: { value: "DUP" } });
    fireEvent.change(screen.getByLabelText("NOMBRE"), { target: { value: "Duplicada" } });
    fireEvent.click(screen.getByRole("button", { name: "CREAR ESTACIÓN" }));

    const error = await screen.findByTestId("site-form-error");
    expect(error).toHaveTextContent(/CONFLICTO/);
    expect(error).toHaveTextContent(/Recarga y reintenta/);
  });

  // [T-2.36] El retiro dejó de ser un doble clic armado: exige teclear el `code` de
  // la estación Y el código de retiro del cliente. Retirar apaga la protección de un
  // edificio; la fricción es deliberada.
  it("retirar exige el código de la estación y el del cliente", async () => {
    mocks.retireSiteSitesSiteIdRetirePost.mockResolvedValue({
      data: { ...SITE, status: "retired" },
      response: { status: 200 },
    });
    renderAdmin();
    await screen.findByTestId("site-row-CHL-A");

    fireEvent.click(screen.getByRole("button", { name: /^RETIRAR$/ }));
    const dialog = await screen.findByTestId("retire-dialog");
    expect(mocks.retireSiteSitesSiteIdRetirePost).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText(/Escribe el código/i), {
      target: { value: "CHL-A" },
    });
    fireEvent.change(screen.getByLabelText(/Código de retiro del cliente/i), {
      target: { value: "SECRETO" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: /RETIRAR ESTACIÓN/ }));

    await waitFor(() => expect(mocks.retireSiteSitesSiteIdRetirePost).toHaveBeenCalledTimes(1));
    expect(mocks.retireSiteSitesSiteIdRetirePost).toHaveBeenCalledWith({
      path: { site_id: "s-1" },
      body: { confirm_code: "CHL-A", retire_code: "SECRETO" },
    });
  });

  it("el 429 del retiro se rotula con el bloqueo, no con 'algo salió mal'", async () => {
    mocks.retireSiteSitesSiteIdRetirePost.mockResolvedValue({
      data: undefined,
      response: { status: 429 },
    });
    renderAdmin();
    await screen.findByTestId("site-row-CHL-A");

    fireEvent.click(screen.getByRole("button", { name: /^RETIRAR$/ }));
    const dialog = await screen.findByTestId("retire-dialog");
    fireEvent.change(screen.getByLabelText(/Escribe el código/i), {
      target: { value: "CHL-A" },
    });
    fireEvent.change(screen.getByLabelText(/Código de retiro del cliente/i), {
      target: { value: "MAL" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: /RETIRAR ESTACIÓN/ }));

    expect(await screen.findByTestId("retire-error")).toHaveTextContent(/DEMASIADOS INTENTOS/);
  });

  // [T-2.37] Este test CONGELABA el defecto: afirmaba que el alta nunca manda
  // `iot_thing`. Sin él, el worker de config sync excluye al gabinete y ningún
  // gabinete creado desde la consola recibía jamás configuración firmada, sin que
  // la consola ofreciera forma alguna de vincularlo después.
  it("el alta de gabinete manda el iot_thing cuando el operador lo escribe", async () => {
    mocks.createGatewayFleetGatewaysPost.mockResolvedValue({
      data: { ...GATEWAY_ROW, iot_thing: "gw-dev-0007" },
      response: { status: 201 },
    });
    renderAdmin();
    await screen.findByTestId("site-row-CHL-A");

    fireEvent.click(screen.getByRole("button", { name: "HARDWARE" }));
    fireEvent.change(screen.getByLabelText("SERIAL DEL GABINETE"), {
      target: { value: "TKB-0007" },
    });
    fireEvent.change(screen.getByLabelText(/IOT THING/), {
      target: { value: " gw-dev-0007 " },
    });
    fireEvent.click(screen.getByRole("button", { name: "AÑADIR GABINETE" }));

    await waitFor(() => expect(mocks.createGatewayFleetGatewaysPost).toHaveBeenCalledTimes(1));
    const body = mocks.createGatewayFleetGatewaysPost.mock.calls[0][0].body;
    expect(body).toEqual({
      site_id: "s-1",
      serial: "TKB-0007",
      iot_thing: "gw-dev-0007",
      has_wr1: true,
      // [T-2.31] El alta declara el equipamiento (default todo instalado).
      equipment: {
        siren: true,
        strobe: true,
        gas_valve: true,
        elevator: true,
        door_retainer: true,
      },
    });
    // El tenant lo sigue heredando del sitio: jamás viaja en el cuerpo.
    expect(body).not.toHaveProperty("tenant_id");
  });

  it("sin iot_thing manda null y el acuse lo declara NO SINCRONIZABLE", async () => {
    mocks.createGatewayFleetGatewaysPost.mockResolvedValue({
      data: { ...GATEWAY_ROW, iot_thing: null },
      response: { status: 201 },
    });
    renderAdmin();
    await screen.findByTestId("site-row-CHL-A");

    fireEvent.click(screen.getByRole("button", { name: "HARDWARE" }));
    fireEvent.change(screen.getByLabelText("SERIAL DEL GABINETE"), {
      target: { value: "TKB-0007" },
    });
    fireEvent.click(screen.getByRole("button", { name: "AÑADIR GABINETE" }));

    await waitFor(() => expect(mocks.createGatewayFleetGatewaysPost).toHaveBeenCalledTimes(1));
    expect(mocks.createGatewayFleetGatewaysPost.mock.calls[0][0].body.iot_thing).toBeNull();
    expect(await screen.findByTestId("acuse-unsyncable")).toBeInTheDocument();
  });

  // El otro camino de los duplicados: al pulsar no cambiaba NADA en pantalla, así que
  // el operador volvía a pulsar. Con un dígito distinto en el serial, nacía un
  // gabinete gemelo en el mismo sitio y con el mismo rótulo.
  it("tras el alta el formulario se cierra y aparece el acuse con los UUID del edge.env", async () => {
    mocks.createGatewayFleetGatewaysPost.mockResolvedValue({
      data: GATEWAY_ROW,
      response: { status: 201 },
    });
    renderAdmin();
    await screen.findByTestId("site-row-CHL-A");

    fireEvent.click(screen.getByRole("button", { name: "HARDWARE" }));
    fireEvent.change(screen.getByLabelText("SERIAL DEL GABINETE"), {
      target: { value: "TKB-0007" },
    });
    fireEvent.click(screen.getByRole("button", { name: "AÑADIR GABINETE" }));

    const acuse = await screen.findByTestId("gateway-acuse");
    expect(screen.queryByTestId("hardware-form")).not.toBeInTheDocument();
    expect(acuse).toHaveTextContent("TAKAB_EDGE_GATEWAY_ID");
    expect(acuse).toHaveTextContent(GATEWAY_ROW.gateway_id);
    expect(acuse).toHaveTextContent(GATEWAY_ROW.tenant_id);
  });

  it("[T-2.31] desmarcar actuadores del sitio viaja en equipment", async () => {
    mocks.createGatewayFleetGatewaysPost.mockResolvedValue({
      data: {},
      response: { status: 201 },
    });
    renderAdmin();
    await screen.findByTestId("site-row-CHL-A");

    fireEvent.click(screen.getByRole("button", { name: "HARDWARE" }));
    fireEvent.change(screen.getByLabelText("SERIAL DEL GABINETE"), {
      target: { value: "TKB-0008" },
    });
    fireEvent.click(screen.getByLabelText("VÁLVULA DE GAS"));
    fireEvent.click(screen.getByLabelText("ASCENSORES"));
    fireEvent.click(screen.getByRole("button", { name: "AÑADIR GABINETE" }));

    await waitFor(() => expect(mocks.createGatewayFleetGatewaysPost).toHaveBeenCalledTimes(1));
    const body = mocks.createGatewayFleetGatewaysPost.mock.calls[0][0].body;
    expect(body.equipment).toEqual({
      siren: true,
      strobe: true,
      gas_valve: false,
      elevator: false,
      door_retainer: true,
    });
  });

  it("un sensor sin procedencia declarada se crea SIN CALIBRAR (null, no cadena vacía)", async () => {
    mocks.createSensorSensorsPost.mockResolvedValue({ data: {}, response: { status: 201 } });
    renderAdmin();
    await screen.findByTestId("site-row-CHL-A");

    fireEvent.click(screen.getByRole("button", { name: "HARDWARE" }));
    fireEvent.click(screen.getByRole("button", { name: "AÑADIR SENSOR" }));

    await waitFor(() => expect(mocks.createSensorSensorsPost).toHaveBeenCalledTimes(1));
    const body = mocks.createSensorSensorsPost.mock.calls[0][0].body;
    expect(body.calibration_source).toBeNull();
    expect(body).toMatchObject({ site_id: "s-1", kind: "structural", model: "RS4D" });
  });

  it("declarar la procedencia la envía tal cual", async () => {
    mocks.createSensorSensorsPost.mockResolvedValue({ data: {}, response: { status: 201 } });
    renderAdmin();
    await screen.findByTestId("site-row-CHL-A");

    fireEvent.click(screen.getByRole("button", { name: "HARDWARE" }));
    fireEvent.change(screen.getByLabelText("PROCEDENCIA DE LA CALIBRACIÓN"), {
      target: { value: "stationxml:AM.R4F74" },
    });
    fireEvent.click(screen.getByRole("button", { name: "AÑADIR SENSOR" }));

    await waitFor(() => expect(mocks.createSensorSensorsPost).toHaveBeenCalledTimes(1));
    expect(mocks.createSensorSensorsPost.mock.calls[0][0].body.calibration_source).toBe(
      "stationxml:AM.R4F74",
    );
  });

  it("sin estaciones invita a crear la primera, no deja al operador atascado", async () => {
    mocks.listSitesSitesGet.mockResolvedValue({ data: [], response: { status: 200 } });
    renderAdmin();
    expect(await screen.findByText("SIN ESTACIONES · CREA LA PRIMERA")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "NUEVA ESTACIÓN" })).toBeInTheDocument();
  });
});

describe("FleetAdmin · códigos de alta por estación (T-2.53)", () => {
  beforeEach(() => {
    resetSessionStoreForTests();
    vi.clearAllMocks();
    mocks.listSitesSitesGet.mockResolvedValue({ data: [SITE], response: { status: 200 } });
    mocks.listGatewaysFleetGatewaysGet.mockResolvedValue({ data: [], response: { status: 200 } });
    mocks.listRuleSetsRuleSetsGet.mockResolvedValue({
      data: { items: [] },
      response: { status: 200 },
    });
    mocks.getRetireCodeStateTenantsTenantIdRetireCodeGet.mockResolvedValue({
      data: { tenant_id: "t-1", configured: true, version: 1, rotated_at: null },
      response: { status: 200 },
    });
    mocks.listEnrollmentCodesSitesSiteIdEnrollmentCodesGet.mockResolvedValue({
      data: [],
      response: { status: 200 },
    });
    mocks.listTenantsTenantsGet.mockResolvedValue({
      data: [TENANT_OWN],
      response: { status: 200 },
    });
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.tenant_admin });
  });

  it("con enrollment_manage aparece el botón CÓDIGOS en cada estación", async () => {
    renderAdmin();
    const row = await screen.findByTestId("site-row-CHL-A");
    expect(within(row).getByRole("button", { name: "CÓDIGOS" })).toBeInTheDocument();
  });

  it("abre la tarjeta de la estación y vuelve sin perder el listado", async () => {
    renderAdmin();
    const row = await screen.findByTestId("site-row-CHL-A");
    fireEvent.click(within(row).getByRole("button", { name: "CÓDIGOS" }));
    expect(await screen.findByTestId("enrollment-codes")).toBeInTheDocument();
    expect(screen.getByText(/Planta Cholula/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "VOLVER" }));
    expect(await screen.findByTestId("site-row-CHL-A")).toBeInTheDocument();
  });

  it("sin enrollment_manage el botón no se pinta (gate propio, no heredado)", async () => {
    // `manage_fleet` y `enrollment_manage` coinciden hoy en los roles web, pero el
    // control cuelga de SU acción: derivarlo de la otra sería una coincidencia.
    useSessionStore.setState({
      me: {
        ...ME_FIXTURES.tenant_admin,
        allowed_actions: { ...ME_FIXTURES.tenant_admin.allowed_actions, enrollment_manage: false },
      },
    });
    renderAdmin();
    const row = await screen.findByTestId("site-row-CHL-A");
    expect(within(row).queryByRole("button", { name: "CÓDIGOS" })).toBeNull();
  });

  it("[T-6.04] la fila de una estación simulada lleva la cinta DEMO", async () => {
    mocks.listSitesSitesGet.mockResolvedValue({
      data: [{ ...SITE, code: "site-sim-001", name: "Sitio Sim 001 Puebla" }],
      response: { status: 200 },
    });
    renderAdmin();
    expect(await screen.findByTestId("site-row-site-sim-001")).toBeInTheDocument();
    expect(screen.getByTestId("site-demo")).toHaveTextContent("DEMO");
  });
});
