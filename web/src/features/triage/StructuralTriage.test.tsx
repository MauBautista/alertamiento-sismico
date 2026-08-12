import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { DamageReportOut } from "@takab/sdk";

import StructuralTriage from "./StructuralTriage";
import { SIGNING_STALE_MS } from "./staleness";

const mocks = vi.hoisted(() => ({
  listDamageReportsIncidentsIncidentIdDamageReportsGet: vi.fn(),
  verifyEvidenceEvidenceEvidenceIdVerifyPost: vi.fn(),
}));
vi.mock("@takab/sdk", () => mocks);

const OK = (data: unknown) => ({ data, response: { status: 200 } });

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function report(over: Partial<DamageReportOut> = {}): DamageReportOut {
  return {
    report_id: "r-1",
    incident_id: "i-1",
    site_id: "s-1",
    zone_id: null,
    user_sub: "u-1",
    categories: [{ key: "structural", severity: "critical" }],
    people_at_risk: false,
    notes: "columna NE",
    evidence_ids: ["ev-abc12345"],
    ts_device: null,
    created_at: "2026-07-16T10:00:00Z",
    ...over,
  };
}

beforeEach(() => vi.clearAllMocks());

describe("StructuralTriage (T-2.10)", () => {
  it("lista reportes con personas en riesgo destacadas y su evidencia", async () => {
    mocks.listDamageReportsIncidentsIncidentIdDamageReportsGet.mockResolvedValue(
      OK([report({ report_id: "urgente", people_at_risk: true })]),
    );
    render(<StructuralTriage incidentId="i-1" />, { wrapper });
    await waitFor(() => expect(screen.getByTestId("report-urgente")).toBeInTheDocument());
    expect(screen.getByTestId("urgent-urgente")).toHaveTextContent("SOC NOTIFICADO");
    expect(screen.getByText(/Daño estructural · CRITICAL/)).toBeInTheDocument();
  });

  it("verificar hash íntegro ⇒ 'HASH VERIFICADO'", async () => {
    mocks.listDamageReportsIncidentsIncidentIdDamageReportsGet.mockResolvedValue(OK([report()]));
    mocks.verifyEvidenceEvidenceEvidenceIdVerifyPost.mockResolvedValue(
      OK({ evidence_id: "ev-abc12345", verified: true, expected_sha256: "x", actual_sha256: "x" }),
    );
    render(<StructuralTriage incidentId="i-1" />, { wrapper });
    await waitFor(() => screen.getByTestId("verify-ev-abc12345"));
    fireEvent.click(screen.getByTestId("verify-ev-abc12345"));
    await waitFor(() =>
      expect(screen.getByTestId("verify-ev-abc12345")).toHaveTextContent("HASH VERIFICADO"),
    );
  });

  it("hash alterado ⇒ 'HASH ALTERADO' (no finge integridad)", async () => {
    mocks.listDamageReportsIncidentsIncidentIdDamageReportsGet.mockResolvedValue(OK([report()]));
    mocks.verifyEvidenceEvidenceEvidenceIdVerifyPost.mockResolvedValue(
      OK({ evidence_id: "ev-abc12345", verified: false, expected_sha256: "x", actual_sha256: "y" }),
    );
    render(<StructuralTriage incidentId="i-1" />, { wrapper });
    await waitFor(() => screen.getByTestId("verify-ev-abc12345"));
    fireEvent.click(screen.getByTestId("verify-ev-abc12345"));
    await waitFor(() =>
      expect(screen.getByTestId("verify-ev-abc12345")).toHaveTextContent("HASH ALTERADO"),
    );
  });

  it("sin reportes ⇒ estado vacío honesto", async () => {
    mocks.listDamageReportsIncidentsIncidentIdDamageReportsGet.mockResolvedValue(OK([]));
    render(<StructuralTriage incidentId="i-1" />, { wrapper });
    await waitFor(() => expect(screen.getByText(/Sin reportes de daños/)).toBeInTheDocument());
  });
});

describe("StructuralTriage · el estado del edificio también envejece [T-2.82.a]", () => {
  afterEach(() => vi.useRealTimers());

  it("con la lista vieja lo dice, y sigue enseñando los reportes que llegaron", async () => {
    mocks.listDamageReportsIncidentsIncidentIdDamageReportsGet.mockResolvedValue(
      OK([report({ report_id: "r-viejo" })]),
    );
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { container } = render(<StructuralTriage incidentId="i-1" />, { wrapper });
    await waitFor(() => expect(screen.getByTestId("report-r-viejo")).toBeInTheDocument());
    expect(container.querySelector('[data-state="stale"]')).toBeNull();

    await act(async () => {
      vi.advanceTimersByTime(SIGNING_STALE_MS + 60_000);
    });

    expect(container.querySelector('[data-state="stale"]')).not.toBeNull();
    expect(screen.getByText(/DATOS RETENIDOS/)).toBeInTheDocument();
    expect(screen.getByTestId("report-r-viejo")).toBeInTheDocument();
  });

  it("«sin reportes de daños» viejo se FECHA: puede ser que nadie haya podido mandarlos", async () => {
    // Son los únicos datos de esta pantalla que siguen llegando durante la
    // emergencia. Afirmar en presente que el edificio no tiene daños reportados,
    // cuando lo que ocurre es que hace un cuarto de hora que no se confirma, es
    // el modo de fallo que la regla de oro 7 nombra por su nombre.
    mocks.listDamageReportsIncidentsIncidentIdDamageReportsGet.mockResolvedValue(OK([]));
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<StructuralTriage incidentId="i-1" />, { wrapper });
    await waitFor(() => expect(screen.getByText(/Sin reportes de daños/)).toBeInTheDocument());

    await act(async () => {
      vi.advanceTimersByTime(SIGNING_STALE_MS + 60_000);
    });

    const panel = screen.getByTestId("structural-triage");
    expect(panel).toHaveTextContent("Sin reportes de daños para este incidente.");
    expect(panel).toHaveTextContent("desde entonces no se ha podido confirmar");
  });
});
