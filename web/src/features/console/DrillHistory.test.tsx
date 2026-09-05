// DrillHistory (T-2.48): el registro de cumplimiento con acuse POR SITIO.
//
// La aserción que gobierna el archivo: `SIN GABINETE COMANDABLE` no puede
// contarse como `SIN ACUSE`. Con 3 sitios apuntados, 1 acusado y 1 sin gabinete,
// escribir "1/3 ACUSADOS" afirmaría que dos edificios ignoraron el simulacro.

import { render, screen, within, fireEvent } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  useDrills: vi.fn(),
  useDrillReport: vi.fn(),
  openPendingDownload: vi.fn(),
}));
vi.mock("./useDrills", () => ({
  useDrills: mocks.useDrills,
  useDrillReport: mocks.useDrillReport,
  DRILL_PAGE_SIZE: 25,
}));
vi.mock("../../lib/download", () => ({ openPendingDownload: mocks.openPendingDownload }));

import { resetSessionStoreForTests, useSessionStore } from "../../auth/session.store";
import { ME_FIXTURES } from "../../test-utils/meFixtures";
import { expectFourStates, type UiState } from "../../test-utils/states";
import DrillHistory from "./DrillHistory";
import type { DrillHistoryData } from "./useDrills";

function historyData(over: Partial<DrillHistoryData> = {}): DrillHistoryData {
  return {
    items: [],
    loading: false,
    error: null,
    updatedAt: Date.parse("2026-08-04T18:00:00Z"),
    hasMore: false,
    loadingMore: false,
    loadMore: vi.fn(),
    refetch: vi.fn(),
    ...over,
  };
}

function site(over: Record<string, unknown> = {}) {
  return {
    site_id: "s-1",
    site_name: "Torre A",
    command_id: "c-1",
    command_status: "acked",
    ack: { ok: true },
    commandable: true,
    acked_at: "2026-08-04T18:01:12Z",
    ack_latency_s: 72,
    ...over,
  };
}

const RAN = {
  drill_id: "d-1",
  tenant_id: "t-1",
  initiated_by: "u-1",
  note: "simulacro trimestral",
  duration_s: 300,
  started_at: "2026-08-04T18:00:00Z",
  stopped_at: null,
  stop_reason: null,
  scheduled_at: null,
  active: false,
  sites: [
    site(),
    site({
      site_id: "s-2",
      site_name: "Torre B",
      command_id: "c-2",
      command_status: "pending",
      ack: null,
    }),
    site({
      site_id: "s-3",
      site_name: "Bodega",
      command_id: null,
      command_status: null,
      ack: null,
      commandable: false,
    }),
  ],
};

function exportar(over: Record<string, unknown> = {}) {
  return { exportar: vi.fn(), pendingId: null, error: null, ...over };
}

beforeEach(() => {
  resetSessionStoreForTests();
  useSessionStore.setState({ me: ME_FIXTURES.tenant_admin });
  vi.clearAllMocks();
  mocks.useDrillReport.mockReturnValue(exportar());
  mocks.openPendingDownload.mockReturnValue({
    resolve: vi.fn(),
    cancel: vi.fn(),
    opened: true,
  });
});

describe("DrillHistory", () => {
  it("N/M ACUSADOS excluye del denominador a los sitios sin gabinete", () => {
    mocks.useDrills.mockReturnValue(historyData({ items: [RAN] }));
    render(<DrillHistory onClose={vi.fn()} />);
    const row = screen.getByTestId("drill-row-d-1");
    expect(row).toHaveTextContent("1/2 ACUSADOS");
    expect(row).toHaveTextContent("1 SIN GABINETE COMANDABLE");
    expect(row).not.toHaveTextContent("1/3 ACUSADOS");
  });

  it("el detalle por sitio rotula cada causa por separado", () => {
    mocks.useDrills.mockReturnValue(historyData({ items: [RAN] }));
    render(<DrillHistory onClose={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /DETALLE/ }));
    const sites = within(screen.getByTestId("drill-sites-d-1"));
    expect(sites.getByText("Torre A").closest("li")).toHaveTextContent("ACUSADO");
    expect(sites.getByText("Torre B").closest("li")).toHaveTextContent("SIN ACUSE");
    const bodega = sites.getByText("Bodega").closest("li");
    expect(bodega).toHaveTextContent("SIN GABINETE COMANDABLE");
    // Y jamás con el rótulo del que sí tenía a quién responderle.
    expect(bodega).not.toHaveTextContent("SIN ACUSE");
  });

  it("distingue EJECUTADO, PROGRAMADO y CANCELADO", () => {
    const agenda = {
      ...RAN,
      drill_id: "ag-1",
      scheduled_at: "2026-08-09T18:00:00Z",
      sites: [site({ command_id: null, command_status: null, ack: null })],
    };
    const cancelled = {
      ...agenda,
      drill_id: "ag-2",
      stopped_at: "2026-08-05T10:00:00Z",
      stop_reason: "cancelled",
    };
    mocks.useDrills.mockReturnValue(historyData({ items: [RAN, agenda, cancelled] }));
    render(<DrillHistory onClose={vi.fn()} />);
    expect(screen.getByTestId("drill-row-d-1")).toHaveTextContent("EJECUTADO");
    expect(screen.getByTestId("drill-row-ag-1")).toHaveTextContent("PROGRAMADO");
    expect(screen.getByTestId("drill-row-ag-2")).toHaveTextContent("CANCELADO");
    // Una agenda pendiente NO reporta acuses: todavía no ha ocurrido.
    expect(screen.getByTestId("drill-row-ag-1")).not.toHaveTextContent("ACUSADOS");
  });

  it("CARGAR MÁS pagina por keyset", () => {
    const loadMore = vi.fn();
    mocks.useDrills.mockReturnValue(historyData({ items: [RAN], hasMore: true, loadMore }));
    render(<DrillHistory onClose={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "CARGAR MÁS" }));
    expect(loadMore).toHaveBeenCalled();
  });

  it("sin más páginas no ofrece CARGAR MÁS", () => {
    mocks.useDrills.mockReturnValue(historyData({ items: [RAN] }));
    render(<DrillHistory onClose={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "CARGAR MÁS" })).toBeNull();
  });

  it("materializa los 4 estados obligatorios", () => {
    const byState: Record<UiState, Partial<DrillHistoryData>> = {
      loading: { loading: true },
      error: { error: "GET /drills falló (500)" },
      empty: { items: [] },
      // Con páginas cargadas un fallo NO borra el historial: se conserva y se
      // declara retenido.
      stale: { items: [RAN], error: "GET /drills falló (500)" },
    };
    expectFourStates((state) => {
      mocks.useDrills.mockReturnValue(historyData(byState[state]));
      return <DrillHistory onClose={vi.fn()} />;
    });
  });
  // ── [T-5.14] El instante del acuse ────────────────────────────────────────

  it("cada sitio que acusó enseña CUÁNDO y CUÁNTO tardó", () => {
    mocks.useDrills.mockReturnValue(historyData({ items: [RAN] }));
    render(<DrillHistory onClose={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /DETALLE/ }));
    const torreA = within(screen.getByTestId("drill-sites-d-1")).getByText("Torre A").closest("li");
    expect(torreA).toHaveTextContent("+1:12");
    // El sello absoluto va al minuto, como todos los de la consola. El segundo
    // vive en la latencia (`+1:12`) y en el PDF, que es la evidencia citable:
    // meter aquí un formato de reloj distinto al del resto de la pantalla
    // costaría más de lo que da.
    expect(torreA).toHaveTextContent("2026-08-04 · 18:01 UTC");
  });

  it("el que NO acusó no enseña un «+0:00» que diría lo contrario", () => {
    mocks.useDrills.mockReturnValue(historyData({ items: [RAN] }));
    render(<DrillHistory onClose={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /DETALLE/ }));
    const sites = within(screen.getByTestId("drill-sites-d-1"));
    for (const nombre of ["Torre B", "Bodega"]) {
      const li = sites.getByText(nombre).closest("li");
      expect(li).not.toHaveTextContent("+0:00");
      expect(li?.querySelector("[data-testid^='drill-lat-']")).toBeNull();
    }
  });

  it("el resumen trae la mediana de los que acusaron", () => {
    mocks.useDrills.mockReturnValue(historyData({ items: [RAN] }));
    render(<DrillHistory onClose={vi.fn()} />);
    expect(screen.getByTestId("drill-row-d-1")).toHaveTextContent("MEDIANA +1:12");
  });

  it("sin un solo acuse la mediana dice S/D, jamás 0:00", () => {
    const nadie = {
      ...RAN,
      drill_id: "d-9",
      sites: [site({ command_status: "pending", ack: null, acked_at: null, ack_latency_s: null })],
    };
    mocks.useDrills.mockReturnValue(historyData({ items: [nadie] }));
    render(<DrillHistory onClose={vi.fn()} />);
    const row = screen.getByTestId("drill-row-d-9");
    expect(row).toHaveTextContent("MEDIANA S/D");
    expect(row).not.toHaveTextContent("+0:00");
  });

  // ── [T-5.14] La exportación ───────────────────────────────────────────────

  it("EXPORTAR reserva la pestaña DENTRO del gesto y pide el reporte", () => {
    const e = exportar();
    mocks.useDrillReport.mockReturnValue(e);
    mocks.useDrills.mockReturnValue(historyData({ items: [RAN] }));
    render(<DrillHistory onClose={vi.fn()} />);
    fireEvent.click(screen.getByTestId("drill-export-d-1"));
    // La pestaña se abre en el onClick, no en el onSuccess: pasada la activación
    // transitoria el navegador la bloquea EN SILENCIO (ver lib/download.ts).
    expect(mocks.openPendingDownload).toHaveBeenCalled();
    expect(e.exportar).toHaveBeenCalledWith("d-1", expect.objectContaining({ opened: true }));
  });

  it("una AGENDA no se exporta: no hay acuses que reportar", () => {
    const agenda = { ...RAN, drill_id: "ag-1", scheduled_at: "2026-08-09T18:00:00Z" };
    mocks.useDrills.mockReturnValue(historyData({ items: [agenda] }));
    render(<DrillHistory onClose={vi.fn()} />);
    expect(screen.queryByTestId("drill-export-ag-1")).toBeNull();
  });

  it("quien no puede iniciar simulacros tampoco genera su evidencia", () => {
    // Generar INSCRIBE una evidencia inmutable: es acto del dueño del tenant.
    // `gov_operator` la descarga después por `export`, como el dictamen.
    useSessionStore.setState({ me: ME_FIXTURES.gov_operator });
    mocks.useDrills.mockReturnValue(historyData({ items: [RAN] }));
    render(<DrillHistory onClose={vi.fn()} />);
    expect(screen.queryByTestId("drill-export-d-1")).toBeNull();
  });

  it("mientras genera lo dice y no deja pulsar dos veces", () => {
    mocks.useDrillReport.mockReturnValue(exportar({ pendingId: "d-1" }));
    mocks.useDrills.mockReturnValue(historyData({ items: [RAN] }));
    render(<DrillHistory onClose={vi.fn()} />);
    const b = screen.getByTestId("drill-export-d-1");
    expect(b).toBeDisabled();
    expect(b).toHaveTextContent("GENERANDO");
  });

  it("si la generación falla lo dice en voz alta: la pestaña se quedó vacía", () => {
    mocks.useDrillReport.mockReturnValue(
      exportar({ error: "POST /drills/d-1/report falló (503)" }),
    );
    mocks.useDrills.mockReturnValue(historyData({ items: [RAN] }));
    render(<DrillHistory onClose={vi.fn()} />);
    expect(screen.getByRole("alert")).toHaveTextContent("503");
  });
});
