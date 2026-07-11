import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useIncidentDetail } from "./useIncidentDetail";

const mocks = vi.hoisted(() => ({
  listDictamensIncidentsIncidentIdDictamensGet: vi.fn(),
  listIncidentActionsIncidentsIncidentIdActionsGet: vi.fn(),
  listEvidenceIncidentsIncidentIdEvidenceGet: vi.fn(),
  getEventEventsEventIdGet: vi.fn(),
  signDictamenIncidentsIncidentIdDictamensPost: vi.fn(),
  generateReportIncidentsIncidentIdReportPost: vi.fn(),
  downloadEvidenceEvidenceEvidenceIdDownloadPost: vi.fn(),
  // La pestaña se RESERVA en el gesto y se navega cuando llega la URL.
  resolve: vi.fn(),
  cancel: vi.fn(),
  openPendingDownload: vi.fn(),
}));

vi.mock("@takab/sdk", () => mocks);
vi.mock("../../lib/download", () => ({
  openPendingDownload: mocks.openPendingDownload,
}));

const OK = (data: unknown) => ({ data, response: { status: 200 } });
const FAIL = (status: number) => ({ data: undefined, response: { status } });

const DICTAMEN = {
  dictamen_id: "d-1",
  tenant_id: "t-1",
  incident_id: "i-1",
  status: "inhabit_monitor",
  basis: {},
  signed_by: null,
  supersedes_dictamen_id: null,
  created_at: "2026-07-08T10:00:00Z",
};

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.openPendingDownload.mockReturnValue({
    opened: true,
    resolve: mocks.resolve,
    cancel: mocks.cancel,
  });
  mocks.listDictamensIncidentsIncidentIdDictamensGet.mockResolvedValue(OK({ items: [DICTAMEN] }));
  mocks.listIncidentActionsIncidentsIncidentIdActionsGet.mockResolvedValue(OK([]));
  mocks.listEvidenceIncidentsIncidentIdEvidenceGet.mockResolvedValue(OK({ items: [] }));
  mocks.getEventEventsEventIdGet.mockResolvedValue(OK({ event_id: "evt-1", quorum_votes: [] }));
});

describe("useIncidentDetail", () => {
  it("sin incidente seleccionado no pide nada", () => {
    renderHook(() => useIncidentDetail(null, null), { wrapper });
    expect(mocks.listDictamensIncidentsIncidentIdDictamensGet).not.toHaveBeenCalled();
    expect(mocks.getEventEventsEventIdGet).not.toHaveBeenCalled();
  });

  it("carga cadena, bitácora, evidencia y el evento con sus quorum_votes", async () => {
    const { result } = renderHook(() => useIncidentDetail("i-1", "evt-1"), { wrapper });
    await waitFor(() => expect(result.current.dictamens.data).toHaveLength(1));
    expect(result.current.event.data?.event_id).toBe("evt-1");
    expect(mocks.listDictamensIncidentsIncidentIdDictamensGet).toHaveBeenCalledWith({
      path: { incident_id: "i-1" },
    });
  });

  it("incidente sin event_id no pide el evento (no hay quórum que mostrar)", async () => {
    const { result } = renderHook(() => useIncidentDetail("i-1", null), { wrapper });
    await waitFor(() => expect(result.current.dictamens.data).toHaveLength(1));
    expect(mocks.getEventEventsEventIdGet).not.toHaveBeenCalled();
    expect(result.current.event.data).toBeUndefined();
    expect(result.current.event.disabled).toBe(true);
  });

  it("un 500 en la cadena se convierte en estado error", async () => {
    mocks.listDictamensIncidentsIncidentIdDictamensGet.mockResolvedValue(FAIL(500));
    const { result } = renderHook(() => useIncidentDetail("i-1", null), { wrapper });
    await waitFor(() => expect(result.current.dictamens.error).toMatch(/dictamens.*500/));
  });

  it("firmar inserta una versión nueva y refresca cadena y bitácora", async () => {
    mocks.signDictamenIncidentsIncidentIdDictamensPost.mockResolvedValue(
      OK({ ...DICTAMEN, dictamen_id: "d-2", signed_by: "u-1" }),
    );
    const { result } = renderHook(() => useIncidentDetail("i-1", null), { wrapper });
    await waitFor(() => expect(result.current.dictamens.data).toBeDefined());

    mocks.listDictamensIncidentsIncidentIdDictamensGet.mockClear();
    act(() => result.current.sign("restricted", null));

    await waitFor(() =>
      expect(mocks.signDictamenIncidentsIncidentIdDictamensPost).toHaveBeenCalledWith({
        path: { incident_id: "i-1" },
        body: { status: "restricted", notes: null },
      }),
    );
    await waitFor(() =>
      expect(mocks.listDictamensIncidentsIncidentIdDictamensGet).toHaveBeenCalled(),
    );
  });

  it("un 403 al firmar queda como signError, no tumba el panel", async () => {
    mocks.signDictamenIncidentsIncidentIdDictamensPost.mockResolvedValue(FAIL(403));
    const { result } = renderHook(() => useIncidentDetail("i-1", null), { wrapper });
    await waitFor(() => expect(result.current.dictamens.data).toBeDefined());
    act(() => result.current.sign("restricted", null));
    await waitFor(() => expect(result.current.signError).toMatch(/403/));
    expect(result.current.dictamens.error).toBeNull();
  });

  it("el PDF navega la pestaña RESERVADA en el gesto (el popup blocker no llega a verla)", async () => {
    mocks.generateReportIncidentsIncidentIdReportPost.mockResolvedValue(
      OK({ evidence_id: "e-1", url: "https://s3/report.pdf?sig=x", expires_in: 300 }),
    );
    const { result } = renderHook(() => useIncidentDetail("i-1", null), { wrapper });
    await waitFor(() => expect(result.current.dictamens.data).toBeDefined());
    act(() => result.current.generatePdf());
    // La pestaña se reserva ANTES de que salga la petición: si se abriera en el
    // onSuccess, el navegador ya habría consumido la activación del usuario.
    expect(mocks.openPendingDownload).toHaveBeenCalled();
    await waitFor(() => expect(mocks.resolve).toHaveBeenCalledWith("https://s3/report.pdf?sig=x"));
    expect(mocks.cancel).not.toHaveBeenCalled();
  });

  it("descargar evidencia abre su presigned GET", async () => {
    mocks.downloadEvidenceEvidenceEvidenceIdDownloadPost.mockResolvedValue(
      OK({ url: "https://s3/eq.mseed?sig=y", expires_in: 300 }),
    );
    const { result } = renderHook(() => useIncidentDetail("i-1", null), { wrapper });
    await waitFor(() => expect(result.current.dictamens.data).toBeDefined());
    act(() => result.current.downloadEvidence("e-9"));
    await waitFor(() =>
      expect(mocks.downloadEvidenceEvidenceEvidenceIdDownloadPost).toHaveBeenCalledWith({
        path: { evidence_id: "e-9" },
      }),
    );
    await waitFor(() => expect(mocks.resolve).toHaveBeenCalledWith("https://s3/eq.mseed?sig=y"));
  });

  it("un 503 al exportar se reporta y CIERRA la pestaña reservada (sin about:blank huérfano)", async () => {
    mocks.generateReportIncidentsIncidentIdReportPost.mockResolvedValue(FAIL(503));
    const { result } = renderHook(() => useIncidentDetail("i-1", null), { wrapper });
    await waitFor(() => expect(result.current.dictamens.data).toBeDefined());
    act(() => result.current.generatePdf());
    await waitFor(() => expect(result.current.exportError).toMatch(/503/));
    expect(mocks.resolve).not.toHaveBeenCalled();
    await waitFor(() => expect(mocks.cancel).toHaveBeenCalled());
  });
});

describe("useIncidentDetail · cada recurso lleva SU estado (regla de oro 7)", () => {
  it("un 403 en evidencia NO se presenta como 'sin evidencia': queda como error propio", async () => {
    mocks.listEvidenceIncidentsIncidentIdEvidenceGet.mockResolvedValue(FAIL(403));
    const { result } = renderHook(() => useIncidentDetail("i-1", null), { wrapper });
    await waitFor(() => expect(result.current.evidence.error).toMatch(/403/));
    expect(result.current.evidence.data).toBeUndefined();
    // …y no contamina el estado del dictamen, que sí cargó.
    expect(result.current.dictamens.data).toHaveLength(1);
    expect(result.current.dictamens.error).toBeNull();
  });

  it("un 500 en la bitácora NO se presenta como '0 acciones'", async () => {
    mocks.listIncidentActionsIncidentsIncidentIdActionsGet.mockResolvedValue(FAIL(500));
    const { result } = renderHook(() => useIncidentDetail("i-1", null), { wrapper });
    await waitFor(() => expect(result.current.actions.error).toMatch(/500/));
    expect(result.current.actions.data).toBeUndefined();
  });

  it("un 500 en el evento NO se presenta como 'incidente sin evento'", async () => {
    mocks.getEventEventsEventIdGet.mockResolvedValue(FAIL(500));
    const { result } = renderHook(() => useIncidentDetail("i-1", "evt-1"), { wrapper });
    await waitFor(() => expect(result.current.event.error).toMatch(/500/));
    expect(result.current.event.disabled).toBe(false);
  });

  it("sin evento asociado el recurso queda DISABLED, no en error", async () => {
    const { result } = renderHook(() => useIncidentDetail("i-1", null), { wrapper });
    await waitFor(() => expect(result.current.dictamens.data).toBeDefined());
    expect(result.current.event.disabled).toBe(true);
    expect(result.current.event.error).toBeNull();
    expect(result.current.event.loading).toBe(false);
  });

  it("refetch reintenta TODOS los recursos, no sólo la cadena", async () => {
    const { result } = renderHook(() => useIncidentDetail("i-1", "evt-1"), { wrapper });
    await waitFor(() => expect(result.current.dictamens.data).toBeDefined());
    vi.clearAllMocks();
    mocks.listDictamensIncidentsIncidentIdDictamensGet.mockResolvedValue(OK({ items: [DICTAMEN] }));
    mocks.listIncidentActionsIncidentsIncidentIdActionsGet.mockResolvedValue(OK([]));
    mocks.listEvidenceIncidentsIncidentIdEvidenceGet.mockResolvedValue(OK({ items: [] }));
    mocks.getEventEventsEventIdGet.mockResolvedValue(OK({ event_id: "evt-1", quorum_votes: [] }));

    act(() => result.current.refetch());
    await waitFor(() => {
      expect(mocks.listEvidenceIncidentsIncidentIdEvidenceGet).toHaveBeenCalled();
      expect(mocks.listIncidentActionsIncidentsIncidentIdActionsGet).toHaveBeenCalled();
      expect(mocks.getEventEventsEventIdGet).toHaveBeenCalled();
    });
  });
});
