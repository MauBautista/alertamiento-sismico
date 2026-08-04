// DrillHistory (T-2.48): el registro de cumplimiento con acuse POR SITIO.
//
// La aserción que gobierna el archivo: `SIN GABINETE COMANDABLE` no puede
// contarse como `SIN ACUSE`. Con 3 sitios apuntados, 1 acusado y 1 sin gabinete,
// escribir "1/3 ACUSADOS" afirmaría que dos edificios ignoraron el simulacro.

import { render, screen, within, fireEvent } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ useDrills: vi.fn() }));
vi.mock("./useDrills", () => ({ useDrills: mocks.useDrills, DRILL_PAGE_SIZE: 25 }));

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

beforeEach(() => {
  vi.clearAllMocks();
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
});
