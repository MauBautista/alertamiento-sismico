import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useSessionStore } from "../../auth/session.store";
import { ME_FIXTURES } from "../../test-utils/meFixtures";
import { expectFourStates } from "../../test-utils/states";
import { anEvent, anIncident, aSite } from "./fixtures";
import { buildRows } from "./model";
import TriagePage from "./TriagePage";
import type { TriageData } from "./useTriage";
import type { IncidentDetailData, Resource } from "./useIncidentDetail";
import type { DictamenOut, EventDetailOut, EvidenceObject, IncidentActionOut } from "@takab/sdk";

const mocks = vi.hoisted(() => ({ useTriage: vi.fn(), useIncidentDetail: vi.fn() }));

vi.mock("./useTriage", () => ({
  useTriage: mocks.useTriage,
  TRIAGE_STALE_MS: 120_000,
}));
vi.mock("./useIncidentDetail", () => ({ useIncidentDetail: mocks.useIncidentDetail }));

const ROWS = buildRows([anIncident()], [anEvent()], [aSite()]);

function triageData(over: Partial<TriageData> = {}): TriageData {
  return {
    rows: ROWS,
    minNodesFor: () => 3,
    loading: false,
    error: null,
    dataUpdatedAt: Date.now(),
    refetch: vi.fn(),
    ...over,
  };
}

function res<T>(data: T | undefined, over: Partial<Resource<T>> = {}): Resource<T> {
  return { data, loading: false, error: null, disabled: false, ...over };
}

function detailData(over: Partial<IncidentDetailData> = {}): IncidentDetailData {
  return {
    dictamens: res<DictamenOut[]>([]),
    actions: res<IncidentActionOut[]>([]),
    evidence: res<EvidenceObject[]>([]),
    event: res<EventDetailOut>(undefined, { disabled: true }),
    refetch: vi.fn(),
    sign: vi.fn(),
    signing: false,
    signError: null,
    generatePdf: vi.fn(),
    pdfPending: false,
    downloadEvidence: vi.fn(),
    downloadPending: false,
    exportError: null,
    ...over,
  };
}

function seedRole(role: keyof typeof ME_FIXTURES): void {
  useSessionStore.setState({
    status: "authenticated",
    origin: "dev",
    idToken: "tok",
    me: ME_FIXTURES[role],
    error: null,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  seedRole("inspector");
  mocks.useIncidentDetail.mockReturnValue(detailData());
});

describe("TriagePage · regla de oro 7", () => {
  it("materializa los 4 estados obligatorios", () => {
    expectFourStates((state) => {
      mocks.useTriage.mockReturnValue(
        triageData({
          loading: state === "loading",
          error: state === "error" ? "GET /incidents falló (500)" : null,
          rows: state === "empty" ? [] : ROWS,
          dataUpdatedAt: state === "stale" ? Date.now() - 200_000 : Date.now(),
        }),
      );
      return <TriagePage />;
    });
  });
});

describe("TriagePage", () => {
  it("no cita ninguna norma: la etiqueta NOM-003-SCT del mockup era errónea", () => {
    mocks.useTriage.mockReturnValue(triageData());
    render(<TriagePage />);
    expect(screen.queryByText(/NOM-003/i)).toBeNull();
    expect(screen.getByText(/EVIDENCIA INMUTABLE/)).toBeTruthy();
  });

  it("no ofrece exportación por lotes (no existe endpoint)", () => {
    mocks.useTriage.mockReturnValue(triageData());
    render(<TriagePage />);
    expect(screen.queryByText(/EXPORTAR LOTE/i)).toBeNull();
  });

  it("no ofrece selector de rango: /incidents no filtra por fecha", () => {
    mocks.useTriage.mockReturnValue(triageData());
    render(<TriagePage />);
    expect(screen.queryByText(/ÚLT\. 7 DÍAS/)).toBeNull();
    expect(screen.queryByText(/ÚLT\. 90 DÍAS/)).toBeNull();
  });

  it("el buscador dice que busca por prefijo de event_id, no por epicentro", () => {
    mocks.useTriage.mockReturnValue(triageData());
    render(<TriagePage />);
    expect(screen.getByLabelText(/prefijo de EVENT_ID/i)).toBeTruthy();
  });

  it("muestra la cuenta de lo realmente cargado", () => {
    mocks.useTriage.mockReturnValue(triageData());
    render(<TriagePage />);
    expect(screen.getByText(/1 INCIDENTES CARGADOS/)).toBeTruthy();
  });

  it("selecciona la primera fila por defecto y monta el detalle", () => {
    mocks.useTriage.mockReturnValue(triageData());
    render(<TriagePage />);
    expect(mocks.useIncidentDetail).toHaveBeenCalledWith(ROWS[0].incident.incident_id, "evt-1");
  });

  it("sin filas no pide detalle de nada", () => {
    mocks.useTriage.mockReturnValue(triageData({ rows: [] }));
    render(<TriagePage />);
    expect(mocks.useIncidentDetail).toHaveBeenCalledWith(null, null);
  });
});

describe("TriagePage · gates de allowed_actions (server-driven)", () => {
  it("inspector: puede firmar y generar PDF", () => {
    seedRole("inspector");
    mocks.useTriage.mockReturnValue(triageData());
    mocks.useIncidentDetail.mockReturnValue(detailData({ dictamens: res([{ ...DICTAMEN }]) }));
    render(<TriagePage />);
    expect(screen.getByRole("button", { name: /FIRMAR DICTAMEN/ }).hasAttribute("disabled")).toBe(
      false,
    );
    expect(screen.getByRole("button", { name: /DICTAMEN PDF/ }).hasAttribute("disabled")).toBe(
      false,
    );
  });

  it("gov_operator tiene export pero NO generate_report: el PDF queda deshabilitado", () => {
    seedRole("gov_operator");
    mocks.useTriage.mockReturnValue(triageData());
    mocks.useIncidentDetail.mockReturnValue(detailData({ dictamens: res([{ ...DICTAMEN }]) }));
    render(<TriagePage />);
    const pdf = screen.getByRole("button", { name: /DICTAMEN PDF/ });
    expect(pdf.hasAttribute("disabled")).toBe(true);
    expect(pdf.getAttribute("title")).toMatch(/generate_report/);
  });

  it("takab_superadmin NO ve habilitada la firma (acto profesional del inspector)", () => {
    seedRole("takab_superadmin");
    mocks.useTriage.mockReturnValue(triageData());
    mocks.useIncidentDetail.mockReturnValue(detailData({ dictamens: res([{ ...DICTAMEN }]) }));
    render(<TriagePage />);
    expect(screen.getByRole("button", { name: /FIRMAR DICTAMEN/ }).hasAttribute("disabled")).toBe(
      true,
    );
  });

  it("soc_operator no exporta ni firma", () => {
    seedRole("soc_operator");
    mocks.useTriage.mockReturnValue(triageData());
    mocks.useIncidentDetail.mockReturnValue(detailData({ dictamens: res([{ ...DICTAMEN }]) }));
    render(<TriagePage />);
    expect(screen.getByRole("button", { name: /EXPORTAR miniSEED/ }).hasAttribute("disabled")).toBe(
      true,
    );
    expect(screen.getByRole("button", { name: /FIRMAR DICTAMEN/ }).hasAttribute("disabled")).toBe(
      true,
    );
  });
});

const DICTAMEN = {
  dictamen_id: "d-1",
  tenant_id: "t-1",
  incident_id: ROWS[0].incident.incident_id,
  status: "no_inhabit_inspect",
  basis: {},
  signed_by: null,
  supersedes_dictamen_id: null,
  created_at: "2026-07-08T10:41:00Z",
};

describe("TriagePage · ningún panel fabrica ausencia (regla de oro 7)", () => {
  const HEAD = res([{ ...DICTAMEN }]);

  function renderWith(over: Partial<IncidentDetailData>) {
    mocks.useTriage.mockReturnValue(triageData());
    mocks.useIncidentDetail.mockReturnValue(detailData({ dictamens: HEAD, ...over }));
    return render(<TriagePage />);
  }

  it("evidencia en vuelo: no dice '0 OBJETOS' ni 'SIN miniSEED'", () => {
    renderWith({ evidence: res<EvidenceObject[]>(undefined, { loading: true }) });
    expect(screen.getByText(/S\/D OBJETOS/)).toBeTruthy();
    expect(screen.queryByText(/SIN miniSEED ARCHIVADO/)).toBeNull();
  });

  it("evidencia fallida: la reporta y deshabilita el export con motivo real", () => {
    renderWith({
      evidence: res<EvidenceObject[]>(undefined, { error: "GET evidence falló (403)" }),
    });
    expect(screen.queryByText(/SIN miniSEED ARCHIVADO/)).toBeNull();
    const btn = screen.getByRole("button", { name: /EXPORTAR miniSEED/ });
    expect(btn.hasAttribute("disabled")).toBe(true);
    expect(btn.getAttribute("title")).toMatch(/No se pudo cargar la evidencia/);
  });

  it("bitácora fallida: NO afirma '0 ACCIONES REGISTRADAS'", () => {
    renderWith({
      actions: res<IncidentActionOut[]>(undefined, { error: "GET actions falló (500)" }),
    });
    expect(screen.queryByText(/0 ACCIONES REGISTRADAS/)).toBeNull();
    expect(screen.getByText(/S\/D ACCIONES REGISTRADAS/)).toBeTruthy();
    expect(screen.getByText(/bitácora no disponible/)).toBeTruthy();
  });

  it("bitácora vacía de verdad SÍ dice 0", () => {
    renderWith({ actions: res<IncidentActionOut[]>([]) });
    expect(screen.getByText(/0 ACCIONES REGISTRADAS/)).toBeTruthy();
  });

  it("dictamen en vuelo: el badge no afirma 'SIN DICTAMEN'", () => {
    mocks.useTriage.mockReturnValue(triageData());
    mocks.useIncidentDetail.mockReturnValue(
      detailData({ dictamens: res<DictamenOut[]>(undefined, { loading: true }) }),
    );
    render(<TriagePage />);
    expect(screen.queryByText("SIN DICTAMEN")).toBeNull();
    expect(screen.getByText(/CARGANDO DICTAMEN/)).toBeTruthy();
  });

  it("evento fallido: el quórum no dice 'incidente sin evento asociado'", () => {
    renderWith({
      event: res<EventDetailOut>(undefined, { error: "GET /events/{id} falló (500)" }),
    });
    expect(screen.queryByText(/SIN EVENTO SÍSMICO ASOCIADO/)).toBeNull();
    expect(screen.queryByText(/CUÓRUM CUMPLIDO/)).toBeNull();
  });
});
