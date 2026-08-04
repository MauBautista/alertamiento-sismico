import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { SiteOut } from "@takab/sdk";

import { resetSessionStoreForTests, useSessionStore } from "../../auth/session.store";
import { ME_FIXTURES } from "../../test-utils/meFixtures";

const mocks = vi.hoisted(() => ({
  listSitesSitesGet: vi.fn(),
  listGatewaysFleetGatewaysGet: vi.fn(),
  listRuleSetsRuleSetsGet: vi.fn(),
  createSiteSitesPost: vi.fn(),
  updateSiteSitesSiteIdPut: vi.fn(),
  retireSiteSitesSiteIdRetirePost: vi.fn(),
  getRetireCodeStateTenantsTenantIdRetireCodeGet: vi.fn(),
  createGatewayFleetGatewaysPost: vi.fn(),
  createSensorSensorsPost: vi.fn(),
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
  tenant_id: "t-1",
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

function renderAdmin() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <FleetAdmin />
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

  it("crear una estación envía lat/lon y NO envía tenant_id", async () => {
    mocks.createSiteSitesPost.mockResolvedValue({ data: SITE, response: { status: 201 } });
    renderAdmin();
    await screen.findByTestId("site-row-CHL-A");

    fireEvent.click(screen.getByRole("button", { name: "NUEVA ESTACIÓN" }));
    fireEvent.change(screen.getByLabelText("CÓDIGO"), { target: { value: "NUEVA" } });
    fireEvent.change(screen.getByLabelText("NOMBRE"), { target: { value: "Torre Norte" } });
    fireEvent.click(screen.getByRole("button", { name: "CREAR ESTACIÓN" }));

    await waitFor(() => expect(mocks.createSiteSitesPost).toHaveBeenCalledTimes(1));
    const body = mocks.createSiteSitesPost.mock.calls[0][0].body;
    expect(body).toMatchObject({ code: "NUEVA", name: "Torre Norte", lat: 19.04, lon: -98.2 });
    // El tenant lo resuelve el servidor desde los claims: mandarlo sería una invitación.
    expect(body).not.toHaveProperty("tenant_id");
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
