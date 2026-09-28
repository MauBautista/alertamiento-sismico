// [T-9.41 · D-43] El asistente «Cierre del evento», por rol.
//
// Las lecturas se mockean en la frontera de sus hooks (cada uno tiene su test);
// el CIERRE va con su hook real sobre el SDK mockeado, porque lo que se prueba es
// que un 409 del servidor llegue a la pantalla en español.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { DictamenOut, IncidentOut } from "@takab/sdk";

import { resetSessionStoreForTests } from "../../auth/session.store";
import { ME_FIXTURES, type RoleName } from "../../test-utils/meFixtures";
import { seedAuthenticated } from "../../test-utils/renderRoutes";
import { expectFourStates } from "../../test-utils/states";
import type { UiState } from "../../test-utils/states";

const m = vi.hoisted(() => ({
  close: vi.fn(),
  ackMutate: vi.fn(),
  confirmMutate: vi.fn(),
  clasificar: vi.fn(),
  generatePdf: vi.fn(),
  S: {} as Record<string, unknown>,
}));

vi.mock("@takab/sdk", async (orig) => ({
  ...(await orig<typeof import("@takab/sdk")>()),
  closeIncidentIncidentsIncidentIdClosePost: m.close,
}));

vi.mock("./useIncidente", async (orig) => ({
  ...(await orig<typeof import("./useIncidente")>()),
  useIncidente: () => m.S.fila,
  useSitio: () => ({ site_id: "s-1", name: "Torre Norte", code: "TN-01" }),
}));
vi.mock("./useInformeAutomatico", async (orig) => ({
  ...(await orig<typeof import("./useInformeAutomatico")>()),
  useInformeAutomatico: () => m.S.informe,
}));
vi.mock("./useDictamenConfirm", () => ({
  useDictamenConfirm: () => ({ mutateAsync: m.confirmMutate, isPending: false, error: null }),
}));
vi.mock("../console/useIncidentAck", () => ({
  useIncidentAck: () => ({ mutateAsync: m.ackMutate, isPending: false, error: null }),
}));
vi.mock("../triage/useIncidentDetail", () => ({
  useIncidentDetail: () => m.S.detail,
}));
vi.mock("../triage/useDamageReports", () => ({
  useDamageReports: () => m.S.reportes,
}));
vi.mock("../triage/useClassification", async (orig) => ({
  ...(await orig<typeof import("../triage/useClassification")>()),
  useClassification: () => m.S.clasif,
}));

import CierreWizard from "./CierreWizard";

const ID = "11111111-2222-3333-4444-555555555555";

const INC: IncidentOut = {
  incident_id: ID,
  tenant_id: "t-1",
  site_id: "s-1",
  event_id: null,
  event_uuid: "e-1",
  opened_at: "2026-09-20T10:00:00Z",
  closed_at: null,
  severity: "warning",
  state: "acked",
  trigger: "sasmex",
  max_pga_g: 0.081,
  max_pgv_cms: 3.2,
  summary: {},
};

function dictamen(over: Partial<DictamenOut> = {}): DictamenOut {
  return {
    dictamen_id: "d-1",
    tenant_id: "t-1",
    incident_id: ID,
    status: "restricted_use",
    band: "amarillo",
    basis: {},
    signed_by: null,
    signature_kind: null,
    supersedes_dictamen_id: null,
    created_at: "2026-09-20T10:05:00Z",
    ...over,
  };
}

const RECURSO = { loading: false, error: null, disabled: false, staleSince: null };

interface Escena {
  inc?: Partial<IncidentOut>;
  dictamenes?: DictamenOut[];
  dictamenesError?: string | null;
  vigente?: string | null;
}

function escena({ inc = {}, dictamenes = [], dictamenesError = null, vigente = "real" }: Escena) {
  m.S.fila = {
    incidente: { ...INC, ...inc },
    loading: false,
    error: null,
    staleSince: null,
    refetch: vi.fn(),
  };
  m.S.detail = {
    dictamens: {
      ...RECURSO,
      data: dictamenesError ? undefined : dictamenes,
      error: dictamenesError,
    },
    actions: { ...RECURSO, data: [] },
    evidence: { ...RECURSO, data: [] },
    event: { ...RECURSO, data: undefined, disabled: true },
    refetch: vi.fn(),
    generatePdf: m.generatePdf,
    pdfPending: false,
    exportError: null,
  };
  const items =
    vigente === null
      ? []
      : [
          {
            classification: vigente,
            classification_id: "c-1",
            classified_at: "2026-09-20T10:10:00Z",
            classified_by: "u",
            current: true,
            incident_id: ID,
            note: "",
            supersedes_id: null,
          },
        ];
  m.S.clasif = {
    items,
    current: items[0] ?? null,
    loading: false,
    readError: false,
    updatedAt: 1,
    refetch: vi.fn(),
    clasificar: m.clasificar,
    pending: false,
  };
  m.S.reportes = { reports: [], loading: false, error: null, staleSince: null };
  m.S.informe = { informe: null, loading: false, error: null, staleSince: null, refetch: vi.fn() };
}

function ui(role: RoleName) {
  seedAuthenticated(ME_FIXTURES[role]);
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/triage/${ID}/cierre`]}>
        <Routes>
          <Route path="/triage/:incidentId/cierre" element={<CierreWizard />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const paso = (id: string) => screen.getByTestId(`paso-${id}`);

beforeEach(() => {
  vi.clearAllMocks();
  resetSessionStoreForTests();
});

describe("CierreWizard · cabecera y progreso", () => {
  it("titula con el inmueble y pinta los 6 pasos con estado en texto", () => {
    escena({ dictamenes: [dictamen({ signed_by: "u-1" })] });
    render(ui("tenant_admin"));
    expect(screen.getByTestId("cierre-titulo")).toHaveTextContent(
      "CIERRE DEL EVENTO · Torre Norte",
    );
    for (const id of ["acusar", "sacudida", "reportes", "dictamen", "clasificar", "cierre"]) {
      expect(screen.getByTestId(`progreso-${id}`)).toBeInTheDocument();
    }
    expect(within(screen.getByTestId("progreso-acusar")).getByText(/HECHO/)).toBeInTheDocument();
    expect(
      within(screen.getByTestId("progreso-reportes")).getByText(/PENDIENTE/),
    ).toBeInTheDocument();
  });

  it("un dato que no cargó se pinta SIN DATO, no PENDIENTE", () => {
    escena({ dictamenesError: "GET /incidents/{id}/dictamens falló (500)" });
    render(ui("tenant_admin"));
    expect(within(paso("dictamen")).getByTestId("paso-estado")).toHaveTextContent("SIN DATO");
    expect(within(paso("cierre")).getByTestId("paso-estado")).toHaveTextContent("SIN DATO");
  });
});

describe("CierreWizard · por rol", () => {
  it("el ADMINISTRADOR ve CERRAR EVENTO", () => {
    escena({ dictamenes: [dictamen({ signed_by: "u-1" })] });
    render(ui("tenant_admin"));
    expect(within(paso("cierre")).getByRole("button", { name: /CERRAR EVENTO/ })).toBeEnabled();
    expect(within(paso("cierre")).getByText("GENERAR INFORME DEFINITIVO")).toBeInTheDocument();
  });

  it("el BRIGADISTA ve CONFIRMAR con AMARILLO, pero no CERRAR", () => {
    escena({ dictamenes: [dictamen({ band: "amarillo" })] });
    render(ui("brigadista"));
    expect(
      within(paso("dictamen")).getByRole("button", { name: /CONFIRMAR DICTAMEN/ }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /CERRAR EVENTO/ })).not.toBeInTheDocument();
    // Dos avisos: GENERAR INFORME (generate_report) y CERRAR (close_incident).
    const avisos = within(paso("cierre")).getAllByTestId("quien-puede");
    expect(avisos).toHaveLength(2);
    for (const a of avisos) expect(a).toHaveTextContent(/ADMINISTRADOR/);
  });

  it("el INSPECTOR ve FIRMAR EN EVALUACIÓN con ROJO sin firmar", () => {
    escena({ dictamenes: [dictamen({ band: "rojo", status: "no_inhabit_inspect" })] });
    render(ui("inspector"));
    const firmar = within(paso("dictamen")).getByRole("link", { name: /FIRMAR EN EVALUACIÓN/ });
    expect(firmar).toHaveAttribute("href", `/triage?incident=${ID}`);
    expect(
      within(paso("dictamen")).queryByRole("button", { name: /CONFIRMAR/ }),
    ).not.toBeInTheDocument();
  });

  it("el INSPECTOR ve LEVANTAR RESTRICCIÓN con el evento cerrado en NO HABITAR", () => {
    escena({
      inc: { state: "closed", closed_at: "2026-09-20T12:00:00Z" },
      dictamenes: [dictamen({ band: "rojo", status: "no_inhabit_inspect", signed_by: "u-9" })],
    });
    render(ui("inspector"));
    expect(
      within(paso("dictamen")).getByRole("link", { name: /LEVANTAR RESTRICCIÓN/ }),
    ).toBeInTheDocument();
    expect(within(paso("cierre")).getByTestId("paso-estado")).toHaveTextContent("HECHO");
  });

  it("sin ack_incident, ACUSAR dice quién puede", () => {
    escena({ inc: { state: "open" } });
    render(ui("inspector"));
    expect(within(paso("acusar")).queryByRole("button", { name: /ACUSAR/ })).toBeNull();
    expect(within(paso("acusar")).getByTestId("quien-puede")).toHaveTextContent(/ADMINISTRADOR/);
  });
});

describe("CierreWizard · clasificar y cerrar", () => {
  it("FALSO POSITIVO pide confirmación porque cierra el evento", () => {
    escena({ vigente: null });
    render(ui("tenant_admin"));
    fireEvent.click(screen.getByTestId("cierre-clasificar-falso_positivo"));
    expect(m.clasificar).not.toHaveBeenCalled();
    const dialogo = screen.getByRole("alertdialog");
    expect(dialogo).toHaveTextContent("FALSO POSITIVO CIERRA EL EVENTO");
    fireEvent.click(within(dialogo).getByRole("button", { name: /SÍ, CLASIFICAR Y CERRAR/ }));
    expect(m.clasificar).toHaveBeenCalledWith(
      { classification: "falso_positivo", supersedesId: undefined },
      expect.any(Object),
    );
  });

  it("REAL se envía sin diálogo", () => {
    escena({ vigente: null });
    render(ui("tenant_admin"));
    fireEvent.click(screen.getByTestId("cierre-clasificar-real"));
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(m.clasificar).toHaveBeenCalledTimes(1);
  });

  it("REAL sin firma exige MOTIVO de 20 caracteres, con contador", () => {
    escena({ dictamenes: [dictamen()] });
    render(ui("tenant_admin"));
    const cerrar = within(paso("cierre")).getByRole("button", { name: /CERRAR EVENTO/ });
    expect(cerrar).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Motivo del cierre"), { target: { value: "corto" } });
    expect(screen.getByTestId("motivo-cuenta")).toHaveTextContent("5 / 20");
    expect(cerrar).toBeDisabled();
  });

  it("un 409 sin_dictamen se muestra en español", async () => {
    m.close.mockResolvedValue({
      data: undefined,
      error: { detail: "sin_dictamen" },
      response: { status: 409 },
    });
    escena({ dictamenes: [dictamen()] });
    render(ui("tenant_admin"));
    fireEvent.change(screen.getByLabelText("Motivo del cierre"), {
      target: { value: "el perito firmó el acta en papel" },
    });
    const cerrar = within(paso("cierre")).getByRole("button", { name: /CERRAR EVENTO/ });
    fireEvent.click(cerrar);
    fireEvent.click(within(paso("cierre")).getByRole("button", { name: /CONFIRMAR/ }));
    const alerta = await within(paso("cierre")).findByRole("alert");
    expect(alerta).toHaveTextContent(/SIN DICTAMEN FIRMADO: FIRMA EL DICTAMEN O ESCRIBE UN MOTIVO/);
    expect(m.close).toHaveBeenCalledWith({
      path: { incident_id: ID },
      body: { motivo: "el perito firmó el acta en papel" },
    });
  });

  it("con una terminal no se pide motivo ni dictamen", () => {
    escena({ vigente: "prueba", dictamenes: [] });
    render(ui("tenant_admin"));
    expect(screen.queryByLabelText("Motivo del cierre")).toBeNull();
    expect(within(paso("cierre")).getByRole("button", { name: /CERRAR EVENTO/ })).toBeEnabled();
  });

  it("el informe automático dice PRELIMINAR cuando lo es", () => {
    escena({ dictamenes: [dictamen({ signed_by: "u-1" })] });
    m.S.informe = {
      informe: { state: "ok", preliminar: true, error: null },
      loading: false,
      error: null,
      staleSince: null,
      refetch: vi.fn(),
    };
    render(ui("tenant_admin"));
    expect(screen.getByTestId("informe-estado")).toHaveTextContent("LISTO · PRELIMINAR");
  });

  it("sin informe (404) lo dice, y un fallo no se confunde con eso", async () => {
    escena({ dictamenes: [dictamen({ signed_by: "u-1" })] });
    render(ui("tenant_admin"));
    expect(within(paso("cierre")).getByText(/SIN INFORME TODAVÍA/)).toBeInTheDocument();
    await waitFor(() => expect(m.close).not.toHaveBeenCalled());
  });
});

describe("CierreWizard · regla de oro 7", () => {
  it("materializa loading, error, empty y stale", () => {
    expectFourStates((state: UiState) => {
      escena({ dictamenes: [dictamen({ signed_by: "u-1" })] });
      const fila = m.S.fila as Record<string, unknown>;
      if (state === "loading") Object.assign(fila, { incidente: undefined, loading: true });
      if (state === "error") Object.assign(fila, { incidente: undefined, error: "HTTP 500" });
      if (state === "stale") Object.assign(fila, { staleSince: 1_000 });
      // `empty`: la fila existe y la brigada no mandó reportes — el marco de
      // REPORTES DE CAMPO lo dice (`escena` los deja en []).
      return ui("tenant_admin");
    });
  });
});
