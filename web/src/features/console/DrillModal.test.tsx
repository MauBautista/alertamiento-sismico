// DrillModal (T-2.48): a quién, cuánto, cuándo y por qué se hace el simulacro.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// [T-5.13] El mock del SDK tiene que traer TAMBIÉN las plantillas. Sin ellas la
// consulta falla y el modal pinta un segundo `role="alert"` — que no es un
// detalle de test: es el StateFrame haciendo su trabajo, y por eso los casos que
// buscaban «el» alert empezaron a encontrar dos.
const sdk = vi.hoisted(() => ({
  listSitesSitesGet: vi.fn(),
  listTemplatesDrillTemplatesGet: vi.fn(),
  createTemplateDrillTemplatesPost: vi.fn(),
  updateTemplateDrillTemplatesTemplateIdPut: vi.fn(),
  deleteTemplateDrillTemplatesTemplateIdDelete: vi.fn(),
  listTenantsTenantsGet: vi.fn(),
}));
vi.mock("@takab/sdk", () => sdk);

import { resetSessionStoreForTests, useSessionStore } from "../../auth/session.store";
import { ME_FIXTURES } from "../../test-utils/meFixtures";
import DrillModal from "./DrillModal";

/**
 * [A-094 · T-8.07] «INICIAR AHORA» vocea en edificios reales: es un
 * ConfirmButton (dos pasos). Un clic ARMA; el segundo emite.
 */
function iniciarAhora(): void {
  fireEvent.click(screen.getByRole("button", { name: "INICIAR AHORA" }));
  fireEvent.click(screen.getByRole("button", { name: /CLIC DE NUEVO PARA INICIAR/ }));
}

const SITES = [
  { site_id: "s-1", name: "Torre A", code: "TA", status: "active" },
  { site_id: "s-2", name: "Torre B", code: "TB", status: "active" },
];

/** Plantilla sana: sus dos sitios se pueden usar hoy. */
const PLANTILLA = {
  template_id: "t-1",
  tenant_id: "tn-1",
  name: "Macrosimulacro septiembre",
  duration_s: 900,
  note: "9:00 h",
  created_by: "u-1",
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
  todos_los_sitios: false,
  sitios_no_usables: 0,
  sites: [
    { site_id: "s-1", site_name: "Torre A", site_code: "TA", estado: "usable", motivo: null },
    { site_id: "s-2", site_name: "Torre B", site_code: "TB", estado: "usable", motivo: null },
  ],
};

/** La misma, con un edificio que ya no puede recibir el simulacro. */
const DEGRADADA = {
  ...PLANTILLA,
  template_id: "t-2",
  name: "Trimestral",
  sitios_no_usables: 1,
  sites: [
    PLANTILLA.sites[0],
    {
      site_id: "s-2",
      site_name: "Torre B",
      site_code: "TB",
      estado: "sin_gabinete",
      motivo: "el sitio no tiene gabinete comandable",
    },
  ],
};

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function renderModal(over: Partial<Parameters<typeof DrillModal>[0]> = {}) {
  const onSubmit = vi.fn();
  const onClose = vi.fn();
  render(
    <DrillModal pending={false} error={null} onSubmit={onSubmit} onClose={onClose} {...over} />,
    {
      wrapper,
    },
  );
  return { onSubmit, onClose };
}

beforeEach(() => {
  vi.clearAllMocks();
  resetSessionStoreForTests();
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.setSystemTime(Date.parse("2026-08-04T18:00:00Z"));
  sdk.listSitesSitesGet.mockResolvedValue({ data: SITES, response: { status: 200 } });
  sdk.listTemplatesDrillTemplatesGet.mockResolvedValue({
    data: { items: [] },
    response: { status: 200 },
  });
  sdk.createTemplateDrillTemplatesPost.mockResolvedValue({
    data: PLANTILLA,
    response: { status: 201 },
  });
  sdk.deleteTemplateDrillTemplatesTemplateIdDelete.mockResolvedValue({
    data: undefined,
    error: undefined,
    response: { status: 204 },
  });
});

afterEach(() => {
  vi.useRealTimers();
});

describe("DrillModal", () => {
  it("sin selección explícita manda site_ids null (el servidor resuelve comandables)", async () => {
    const { onSubmit } = renderModal();
    await waitFor(() => expect(screen.getByLabelText("Torre A")).toBeInTheDocument());
    iniciarAhora();
    expect(onSubmit).toHaveBeenCalledWith({
      siteIds: null,
      durationS: 300,
      note: null,
      scheduledAt: null,
      // Sin plantilla elegida no hay procedencia que declarar.
      fromTemplate: null,
    });
  });

  it("multiselección de sitios", async () => {
    const { onSubmit } = renderModal();
    await waitFor(() => expect(screen.getByLabelText("Torre A")).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText("Torre A"));
    fireEvent.click(screen.getByLabelText("Torre B"));
    fireEvent.click(screen.getByLabelText("Torre B")); // se deselecciona
    iniciarAhora();
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ siteIds: ["s-1"] }));
  });

  it("duración y nota viajan en la petición", async () => {
    const { onSubmit } = renderModal();
    await waitFor(() => expect(screen.getByLabelText("Torre A")).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText(/DURACIÓN/), { target: { value: "900" } });
    fireEvent.change(screen.getByLabelText(/NOTA/), { target: { value: "simulacro trimestral" } });
    iniciarAhora();
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ durationS: 900, note: "simulacro trimestral" }),
    );
  });

  it("en modo PROGRAMAR manda scheduled_at en UTC y no dispara nada", async () => {
    const { onSubmit } = renderModal();
    await waitFor(() => expect(screen.getByLabelText("Torre A")).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText("PROGRAMAR"));
    const when = new Date(Date.parse("2026-08-05T12:00:00Z"));
    // El input local se rellena con el valor que produce el mismo instante UTC.
    const local = new Date(when.getTime() - when.getTimezoneOffset() * 60_000)
      .toISOString()
      .slice(0, 16);
    fireEvent.change(screen.getByLabelText(/FECHA Y HORA/), { target: { value: local } });
    fireEvent.click(screen.getByRole("button", { name: "PROGRAMAR SIMULACRO" }));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ scheduledAt: "2026-08-05T12:00:00.000Z" }),
    );
  });

  it("una fecha pasada NO se envía: se rechaza con motivo", async () => {
    const { onSubmit } = renderModal();
    await waitFor(() => expect(screen.getByLabelText("Torre A")).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText("PROGRAMAR"));
    fireEvent.change(screen.getByLabelText(/FECHA Y HORA/), {
      target: { value: "2026-08-03T10:00" },
    });
    fireEvent.click(screen.getByRole("button", { name: "PROGRAMAR SIMULACRO" }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("FUTURO");
  });

  it("programar sin fecha tampoco envía nada", async () => {
    const { onSubmit } = renderModal();
    await waitFor(() => expect(screen.getByLabelText("Torre A")).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText("PROGRAMAR"));
    fireEvent.click(screen.getByRole("button", { name: "PROGRAMAR SIMULACRO" }));
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("si /sites falla lo dice: no inventa una lista vacía de sitios", async () => {
    sdk.listSitesSitesGet.mockResolvedValue({ data: undefined, response: { status: 500 } });
    renderModal();
    await waitFor(() => expect(screen.getByText(/GET \/sites falló/)).toBeInTheDocument());
    // Aun así se puede lanzar a todos los comandables: el servidor es la autoridad.
    expect(screen.getByRole("button", { name: "INICIAR AHORA" })).toBeEnabled();
  });

  it("rotula que un simulacro NO toca relés", async () => {
    renderModal();
    await waitFor(() => expect(screen.getByLabelText("Torre A")).toBeInTheDocument());
    expect(screen.getByTestId("drill-modal")).toHaveTextContent("CERO RELÉS");
  });

  it("mientras la mutación está en vuelo no se puede disparar dos veces", async () => {
    renderModal({ pending: true });
    await waitFor(() => expect(screen.getByLabelText("Torre A")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "INICIAR AHORA" })).toBeDisabled();
  });
});

// ── [T-5.13] Plantillas ─────────────────────────────────────────────────────
//
// El alta tenía cinco campos y ninguno era una plantilla: para el macrosimulacro
// de septiembre había que teclear los sitios, la duración y la nota cada vez.

describe("DrillModal · plantillas de simulacro [T-5.13]", () => {
  it("sin plantillas guardadas lo DICE, en vez de dejar el hueco", async () => {
    renderModal();
    await waitFor(() => expect(screen.getByLabelText("Torre A")).toBeInTheDocument());
    // `StateFrame` sustituye a la lista cuando está vacía: el `data-testid` no
    // existe, y ése es el punto — lo que se pinta es el motivo, no un hueco.
    expect(screen.queryByTestId("drill-templates")).not.toBeInTheDocument();
    expect(screen.getByText(/SIN PLANTILLAS GUARDADAS/)).toBeInTheDocument();
  });

  it("elegir una plantilla PRECARGA el formulario y declara su procedencia", async () => {
    sdk.listTemplatesDrillTemplatesGet.mockResolvedValue({
      data: { items: [PLANTILLA] },
      response: { status: 200 },
    });
    const { onSubmit } = renderModal();
    await waitFor(() =>
      expect(screen.getByLabelText("Macrosimulacro septiembre")).toBeInTheDocument(),
    );

    fireEvent.click(screen.getByLabelText("Macrosimulacro septiembre"));
    iniciarAhora();

    // Los valores se precargan para poder revisarlos, y `fromTemplate` viaja para
    // que el registro diga DE DÓNDE salió este simulacro.
    expect(onSubmit).toHaveBeenCalledWith({
      siteIds: ["s-1", "s-2"],
      durationS: 900,
      note: "9:00 h",
      scheduledAt: null,
      fromTemplate: "t-1",
    });
  });

  it("UNA PLANTILLA DEGRADADA NO SE LANZA EN SILENCIO", async () => {
    // **El criterio 3 de la ficha.** Sin esto el operador cree haber lanzado el
    // simulacro a dos torres cuando sonó en una, y no hay nada en pantalla que
    // lo desmienta.
    sdk.listTemplatesDrillTemplatesGet.mockResolvedValue({
      data: { items: [DEGRADADA] },
      response: { status: 200 },
    });
    renderModal();
    await waitFor(() => expect(screen.getByLabelText("Trimestral")).toBeInTheDocument());

    // Ya en la LISTA, antes de elegirla: quien la escoge está mirando ahí.
    expect(screen.getByTestId("drill-templates")).toHaveTextContent(
      "1 SITIO(S) NO UTILIZABLES HOY",
    );

    fireEvent.click(screen.getByLabelText("Trimestral"));
    const aviso = screen.getByTestId("drill-degradada");
    expect(aviso).toHaveTextContent("NO PUEDE USAR 1 DE SUS 2 SITIO(S)");
    // Con el MOTIVO, no un «no disponible» que no dice a quién llamar.
    expect(aviso).toHaveTextContent("TB");
    expect(aviso).toHaveTextContent("EL SITIO NO TIENE GABINETE COMANDABLE");
    // Y no bloquea: un edificio caído no puede dejar sin simulacro a los otros.
    expect(screen.getByRole("button", { name: "INICIAR AHORA" })).toBeEnabled();
  });

  it("una plantilla sana NO pinta el aviso de degradada", async () => {
    // La otra mitad: un aviso que saliera siempre no informa, decora.
    sdk.listTemplatesDrillTemplatesGet.mockResolvedValue({
      data: { items: [PLANTILLA] },
      response: { status: 200 },
    });
    renderModal();
    await waitFor(() =>
      expect(screen.getByLabelText("Macrosimulacro septiembre")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByLabelText("Macrosimulacro septiembre"));
    expect(screen.queryByTestId("drill-degradada")).not.toBeInTheDocument();
  });

  it("guardar como plantilla manda lo que hay en el formulario", async () => {
    renderModal();
    await waitFor(() => expect(screen.getByLabelText("Torre A")).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText("Torre A"));
    fireEvent.change(screen.getByLabelText(/DURACIÓN/), { target: { value: "900" } });
    fireEvent.change(screen.getByLabelText(/NOTA/), { target: { value: "9:00 h" } });
    fireEvent.change(screen.getByLabelText(/GUARDAR LO DE ABAJO/), {
      target: { value: "  Macrosimulacro septiembre  " },
    });
    fireEvent.click(screen.getByRole("button", { name: "GUARDAR" }));

    await waitFor(() => expect(sdk.createTemplateDrillTemplatesPost).toHaveBeenCalled());
    expect(sdk.createTemplateDrillTemplatesPost).toHaveBeenCalledWith({
      body: {
        name: "Macrosimulacro septiembre",
        site_ids: ["s-1"],
        duration_s: 900,
        note: "9:00 h",
      },
    });
  });

  it("guardar sin nombre no manda nada y dice por qué", async () => {
    renderModal();
    await waitFor(() => expect(screen.getByLabelText("Torre A")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "GUARDAR" }));
    expect(sdk.createTemplateDrillTemplatesPost).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("PONLE NOMBRE");
  });

  it("el nombre repetido se traduce, no se escupe un 409", async () => {
    sdk.createTemplateDrillTemplatesPost.mockResolvedValue({
      data: undefined,
      response: { status: 409 },
    });
    renderModal();
    await waitFor(() => expect(screen.getByLabelText("Torre A")).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText(/GUARDAR LO DE ABAJO/), { target: { value: "Repe" } });
    fireEvent.click(screen.getByRole("button", { name: "GUARDAR" }));

    await waitFor(() =>
      expect(screen.getByText("YA EXISTE UNA PLANTILLA CON ESE NOMBRE")).toBeInTheDocument(),
    );
  });

  it("borrar una plantilla la quita y suelta la selección", async () => {
    sdk.listTemplatesDrillTemplatesGet.mockResolvedValue({
      data: { items: [PLANTILLA] },
      response: { status: 200 },
    });
    const { onSubmit } = renderModal();
    await waitFor(() =>
      expect(screen.getByLabelText("Macrosimulacro septiembre")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByLabelText("Macrosimulacro septiembre"));
    // [A-094 · T-8.07] Borrar también es de dos pasos.
    fireEvent.click(screen.getByRole("button", { name: "BORRAR Macrosimulacro septiembre" }));
    fireEvent.click(screen.getByRole("button", { name: /CLIC DE NUEVO PARA BORRAR/ }));

    await waitFor(() =>
      expect(sdk.deleteTemplateDrillTemplatesTemplateIdDelete).toHaveBeenCalledWith({
        path: { template_id: "t-1" },
      }),
    );
    // Y el simulacro que se lance ya no puede citar una procedencia que se borró.
    iniciarAhora();
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ fromTemplate: null }));
  });
});

// ── [A-094 · T-8.07] Lo que vocea en edificios reales pide confirmación ─────────

describe("DrillModal · INICIAR AHORA y BORRAR piden confirmación [A-094]", () => {
  it("un clic en INICIAR AHORA ARMA, no emite; el segundo emite", async () => {
    const { onSubmit } = renderModal();
    await waitFor(() => expect(screen.getByLabelText("Torre A")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "INICIAR AHORA" }));
    expect(onSubmit).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /CLIC DE NUEVO PARA INICIAR/ }));
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it("PROGRAMAR no emite nada y sigue siendo de un clic", async () => {
    const { onSubmit } = renderModal();
    await waitFor(() => expect(screen.getByLabelText("Torre A")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("radio", { name: "PROGRAMAR" }));
    fireEvent.change(screen.getByLabelText(/FECHA Y HORA/), {
      target: { value: "2026-08-05T09:00" },
    });
    fireEvent.click(screen.getByRole("button", { name: "PROGRAMAR SIMULACRO" }));
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it("un clic en BORRAR no borra la plantilla", async () => {
    sdk.listTemplatesDrillTemplatesGet.mockResolvedValue({
      data: { items: [PLANTILLA] },
      response: { status: 200 },
    });
    renderModal();
    await waitFor(() =>
      expect(screen.getByLabelText("Macrosimulacro septiembre")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: "BORRAR Macrosimulacro septiembre" }));
    // La mutación sale en un tic posterior: se deja correr antes de afirmar.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });
    expect(sdk.deleteTemplateDrillTemplatesTemplateIdDelete).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /CLIC DE NUEVO PARA BORRAR/ })).toBeInTheDocument();
  });

  it("si el servidor NO arranca el simulacro, el botón no afirma nada", async () => {
    // El alta devuelve si arrancó (`useActiveDrill.start`); con `false` el botón
    // vuelve a reposo y el error lo pinta el modal.
    renderModal({ onSubmit: vi.fn(() => Promise.resolve(false)), error: "HTTP 400" });
    await waitFor(() => expect(screen.getByLabelText("Torre A")).toBeInTheDocument());
    iniciarAhora();
    expect(await screen.findByRole("button", { name: "INICIAR AHORA" })).toBeEnabled();
    expect(screen.queryByText("HECHO")).toBeNull();
    expect(screen.queryByText("EJECUTADO")).toBeNull();
  });
});

// ── [T-8.07] BORRAR espera al servidor ────────────────────────────────────────
//
// El `onConfirm` de BORRAR llamaba a `mutate` (void), así que el ConfirmButton
// pintaba «EJECUTADO» en verde antes de que respondiera el DELETE, y la plantilla
// se soltaba aunque el borrado fallara: el operador se quedaba creyendo que la
// había quitado, y lanzaba sin la procedencia de una plantilla que seguía viva.

describe("DrillModal · BORRAR plantilla espera al servidor [T-8.07]", () => {
  function conPlantilla(): void {
    sdk.listTemplatesDrillTemplatesGet.mockResolvedValue({
      data: { items: [PLANTILLA] },
      response: { status: 200 },
    });
  }

  function borrar(): void {
    fireEvent.click(screen.getByRole("button", { name: "BORRAR Macrosimulacro septiembre" }));
    fireEvent.click(screen.getByRole("button", { name: /CLIC DE NUEVO PARA BORRAR/ }));
  }

  it("con el DELETE en vuelo dice ENVIANDO…, no «EJECUTADO»", async () => {
    conPlantilla();
    let responder!: (value: unknown) => void;
    sdk.deleteTemplateDrillTemplatesTemplateIdDelete.mockReturnValue(
      new Promise((resolve) => {
        responder = resolve;
      }),
    );
    renderModal();
    await waitFor(() =>
      expect(screen.getByLabelText("Macrosimulacro septiembre")).toBeInTheDocument(),
    );
    borrar();
    await waitFor(() =>
      expect(sdk.deleteTemplateDrillTemplatesTemplateIdDelete).toHaveBeenCalledTimes(1),
    );
    expect(screen.getByRole("button", { name: /ENVIANDO/ })).toBeDisabled();
    expect(screen.queryByText("EJECUTADO")).toBeNull();
    await act(async () => {
      responder({ data: undefined, error: undefined, response: { status: 204 } });
      await vi.advanceTimersByTimeAsync(10);
    });
  });

  it("si el DELETE falla, la plantilla sigue elegida, el botón vuelve y el error se pinta", async () => {
    conPlantilla();
    sdk.deleteTemplateDrillTemplatesTemplateIdDelete.mockResolvedValue({
      data: undefined,
      error: { detail: "fallo interno" },
      response: { status: 500 },
    });
    const { onSubmit } = renderModal();
    await waitFor(() =>
      expect(screen.getByLabelText("Macrosimulacro septiembre")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByLabelText("Macrosimulacro septiembre"));
    borrar();

    expect(await screen.findByText(/DELETE \/DRILL-TEMPLATES FALLÓ \(500\)/)).toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: "BORRAR Macrosimulacro septiembre" }),
    ).toBeEnabled();
    expect(screen.queryByText("EJECUTADO")).toBeNull();
    // No se borró: la plantilla sigue elegida y el simulacro la cita.
    expect(screen.getByLabelText("Macrosimulacro septiembre")).toBeChecked();
    iniciarAhora();
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ fromTemplate: "t-1" }));
  });
});

// ── [A-016 · T-8.07] Un rol interno NOMBRA al cliente ─────────────────────────
//
// La consola decía «SIN SELECCIÓN ⇒ TODOS LOS SITIOS … DEL TENANT» a un rol que
// ve los gabinetes de TODOS los clientes: el superadmin que no marcaba nada
// mandaba el simulacro a cada edificio de la plataforma. Ahora elige el cliente,
// ve sólo sus sitios y sus plantillas, y sin selección no se lanza.

const SITIOS_DE_DOS_CLIENTES = [
  { site_id: "s-1", tenant_id: "tn-1", name: "Torre A", code: "TA", status: "active" },
  { site_id: "s-9", tenant_id: "tn-2", name: "Nave Z", code: "NZ", status: "active" },
];

const CLIENTES = [
  { tenant_id: "tn-1", name: "Hospital Uno", code: "HU" },
  { tenant_id: "tn-2", name: "Corporativo Dos", code: "CD" },
];

describe("DrillModal · rol interno [A-016]", () => {
  beforeEach(() => {
    useSessionStore.setState({
      status: "authenticated",
      idToken: "tok",
      me: ME_FIXTURES.takab_superadmin,
    });
    sdk.listSitesSitesGet.mockResolvedValue({
      data: SITIOS_DE_DOS_CLIENTES,
      response: { status: 200 },
    });
    sdk.listTenantsTenantsGet.mockResolvedValue({ data: CLIENTES, response: { status: 200 } });
  });

  it("sin cliente elegido no hay sitios que marcar ni simulacro que lanzar", async () => {
    const { onSubmit } = renderModal();
    const cliente = await screen.findByLabelText("CLIENTE");
    await waitFor(() =>
      expect(screen.getByRole("option", { name: "Hospital Uno" })).toBeInTheDocument(),
    );
    expect(cliente).toHaveValue("");
    expect(screen.queryByLabelText("Torre A")).toBeNull();
    expect(screen.queryByLabelText("Nave Z")).toBeNull();
    const iniciar = screen.getByRole("button", { name: "INICIAR AHORA" });
    expect(iniciar).toBeDisabled();
    expect(iniciar).toHaveAttribute("title", expect.stringContaining("CLIENTE"));
    // Y NUNCA dice «todos los sitios del tenant»: para este rol eso es la plataforma.
    expect(screen.getByTestId("drill-modal")).not.toHaveTextContent("DEL TENANT");
    fireEvent.click(iniciar);
    fireEvent.click(iniciar);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("elegido el cliente, sólo sus sitios; y sin marcar ninguno tampoco se lanza", async () => {
    const { onSubmit } = renderModal();
    await waitFor(() =>
      expect(screen.getByRole("option", { name: "Hospital Uno" })).toBeInTheDocument(),
    );
    fireEvent.change(screen.getByLabelText("CLIENTE"), { target: { value: "tn-1" } });
    expect(await screen.findByLabelText("Torre A")).toBeInTheDocument();
    expect(screen.queryByLabelText("Nave Z")).toBeNull();
    expect(screen.getByTestId("drill-cliente")).toHaveTextContent("HOSPITAL UNO");
    expect(screen.getByRole("button", { name: "INICIAR AHORA" })).toBeDisabled();

    fireEvent.click(screen.getByLabelText("Torre A"));
    iniciarAhora();
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ siteIds: ["s-1"] }));
  });

  it("cambiar de cliente suelta la selección del anterior", async () => {
    renderModal();
    await waitFor(() =>
      expect(screen.getByRole("option", { name: "Hospital Uno" })).toBeInTheDocument(),
    );
    fireEvent.change(screen.getByLabelText("CLIENTE"), { target: { value: "tn-1" } });
    fireEvent.click(await screen.findByLabelText("Torre A"));
    fireEvent.change(screen.getByLabelText("CLIENTE"), { target: { value: "tn-2" } });
    expect(await screen.findByLabelText("Nave Z")).not.toBeChecked();
    expect(screen.getByRole("button", { name: "INICIAR AHORA" })).toBeDisabled();
  });

  it("las plantillas son las DEL cliente, y una plantilla «todos» basta para lanzar", async () => {
    sdk.listTemplatesDrillTemplatesGet.mockResolvedValue({
      data: {
        items: [
          { ...PLANTILLA, tenant_id: "tn-1", sites: [], todos_los_sitios: true },
          { ...DEGRADADA, tenant_id: "tn-2" },
        ],
      },
      response: { status: 200 },
    });
    const { onSubmit } = renderModal();
    await waitFor(() =>
      expect(screen.getByRole("option", { name: "Hospital Uno" })).toBeInTheDocument(),
    );
    fireEvent.change(screen.getByLabelText("CLIENTE"), { target: { value: "tn-1" } });
    fireEvent.click(await screen.findByLabelText("Macrosimulacro septiembre"));
    expect(screen.queryByLabelText("Trimestral")).toBeNull();
    expect(screen.getByTestId("drill-modal")).toHaveTextContent(
      "TODOS LOS COMANDABLES DE HOSPITAL UNO",
    );
    iniciarAhora();
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ siteIds: null, fromTemplate: "t-1" }),
    );
  });

  it("no ofrece GUARDAR plantilla: se guardaría en el cliente de TAKAB, no en el elegido", async () => {
    // `POST /drill-templates` escribe en el tenant DEL TOKEN (el de TAKAB para un
    // interno): la plantilla no aparecería nunca bajo el cliente al que apunta.
    // Se deja de pedir en vez de fabricar una plantilla huérfana.
    renderModal();
    await waitFor(() =>
      expect(screen.getByRole("option", { name: "Hospital Uno" })).toBeInTheDocument(),
    );
    fireEvent.change(screen.getByLabelText("CLIENTE"), { target: { value: "tn-1" } });
    const guardar = screen.getByRole("button", { name: "GUARDAR" });
    expect(guardar).toBeDisabled();
    expect(guardar).toHaveAttribute("title", expect.stringContaining("TAKAB"));
    fireEvent.change(screen.getByLabelText(/GUARDAR LO DE ABAJO/), { target: { value: "X" } });
    fireEvent.click(guardar);
    expect(sdk.createTemplateDrillTemplatesPost).not.toHaveBeenCalled();
  });

  it("sin el catálogo de clientes no se inventa un nombre: se usa el identificador", async () => {
    sdk.listTenantsTenantsGet.mockResolvedValue({ data: undefined, response: { status: 503 } });
    renderModal();
    await waitFor(() => expect(screen.getByRole("option", { name: /tn-1/ })).toBeInTheDocument());
    expect(screen.getByTestId("drill-clientes-error")).toHaveTextContent("503");
  });
});

describe("DrillModal · rol de cliente [A-016]", () => {
  it("no pide cliente ni consulta el catálogo de clientes", async () => {
    useSessionStore.setState({
      status: "authenticated",
      idToken: "tok",
      me: ME_FIXTURES.tenant_admin,
    });
    renderModal();
    await waitFor(() => expect(screen.getByLabelText("Torre A")).toBeInTheDocument());
    expect(screen.queryByLabelText("CLIENTE")).toBeNull();
    expect(sdk.listTenantsTenantsGet).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "INICIAR AHORA" })).toBeEnabled();
  });
});
