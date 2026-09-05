// DrillModal (T-2.48): a quién, cuánto, cuándo y por qué se hace el simulacro.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
}));
vi.mock("@takab/sdk", () => sdk);

import DrillModal from "./DrillModal";

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
    fireEvent.click(screen.getByRole("button", { name: "INICIAR AHORA" }));
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
    fireEvent.click(screen.getByRole("button", { name: "INICIAR AHORA" }));
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ siteIds: ["s-1"] }));
  });

  it("duración y nota viajan en la petición", async () => {
    const { onSubmit } = renderModal();
    await waitFor(() => expect(screen.getByLabelText("Torre A")).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText(/DURACIÓN/), { target: { value: "900" } });
    fireEvent.change(screen.getByLabelText(/NOTA/), { target: { value: "simulacro trimestral" } });
    fireEvent.click(screen.getByRole("button", { name: "INICIAR AHORA" }));
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
    fireEvent.click(screen.getByRole("button", { name: "INICIAR AHORA" }));

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
    fireEvent.click(screen.getByRole("button", { name: "BORRAR Macrosimulacro septiembre" }));

    await waitFor(() =>
      expect(sdk.deleteTemplateDrillTemplatesTemplateIdDelete).toHaveBeenCalledWith({
        path: { template_id: "t-1" },
      }),
    );
    // Y el simulacro que se lance ya no puede citar una procedencia que se borró.
    fireEvent.click(screen.getByRole("button", { name: "INICIAR AHORA" }));
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ fromTemplate: null }));
  });
});
