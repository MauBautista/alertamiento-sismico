// DrillBanner (T-1.60 · reescrito en T-2.48): rotulado NO-real, precedencia de
// la alerta, gates de matriz y —lo que motivó la reescritura— los 4 estados
// obligatorios sobre `/drills/active`.
//
// El bug que se cierra aquí: el banner ignoraba `loading` y, si `/drills/active`
// fallaba con un simulacro VIVO, desaparecía en silencio. Un simulacro en curso
// que deja de anunciarse es indistinguible de una alerta real para quien está
// dentro del edificio.

import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ useActiveDrill: vi.fn() }));
vi.mock("./useActiveDrill", () => ({ useActiveDrill: mocks.useActiveDrill }));
vi.mock("./DrillHistory", () => ({ default: () => <div data-testid="drill-history" /> }));
vi.mock("./DrillModal", () => ({
  default: ({ onClose }: { onClose: () => void }) => (
    <div data-testid="drill-modal">
      <button type="button" onClick={onClose}>
        CERRAR
      </button>
    </div>
  ),
}));

import { resetSessionStoreForTests, useSessionStore } from "../../auth/session.store";
import { ME_FIXTURES } from "../../test-utils/meFixtures";
import { expectFourStates, type UiState } from "../../test-utils/states";
import DrillBanner from "./DrillBanner";
import type { ActiveDrillData } from "./useActiveDrill";

const NOW = Date.parse("2026-08-04T18:00:00Z");

function drillData(over: Partial<ActiveDrillData> = {}): ActiveDrillData {
  return {
    drill: null,
    scheduled: [],
    loading: false,
    readError: null,
    updatedAt: NOW - 5_000,
    refetch: vi.fn(),
    start: vi.fn(),
    stop: vi.fn(),
    cancel: vi.fn(),
    pending: false,
    error: null,
    ...over,
  };
}

const DRILL = {
  drill_id: "d-1",
  tenant_id: "t-1",
  initiated_by: "u-1",
  note: null,
  duration_s: 300,
  scheduled_at: null,
  started_at: "2026-08-04T17:58:00Z",
  stopped_at: null,
  stop_reason: null,
  active: true,
  sites: [
    {
      site_id: "s-1",
      site_name: "Sitio Dev",
      command_id: "c-1",
      command_status: "acked",
      ack: null,
      commandable: true,
    },
  ],
};

/** Agenda a las 18:05Z: dentro de la ventana de armado desde las 17:50Z. */
const AGENDA = {
  ...DRILL,
  drill_id: "ag-1",
  active: false,
  scheduled_at: "2026-08-04T18:05:00Z",
  started_at: "2026-08-04T12:00:00Z",
  sites: [
    {
      site_id: "s-1",
      site_name: "Sitio Dev",
      command_id: null,
      command_status: null,
      ack: null,
      commandable: true,
    },
  ],
};

beforeEach(() => {
  resetSessionStoreForTests();
  vi.clearAllMocks();
  vi.useFakeTimers();
  vi.setSystemTime(NOW);
});

afterEach(() => {
  vi.useRealTimers();
});

describe("DrillBanner", () => {
  it("con drill activo pinta el banner rotulado NO-real", () => {
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.soc_operator });
    mocks.useActiveDrill.mockReturnValue(drillData({ drill: DRILL }));
    render(<DrillBanner hasLiveIncident={false} />);
    const banner = screen.getByTestId("drill-banner");
    expect(banner).toHaveTextContent("SIMULACRO EN CURSO — ESTO NO ES UNA ALERTA REAL");
    expect(banner).toHaveTextContent("1 SITIO(S)");
    // soc_operator no puede terminarlo (gate drill_start).
    expect(screen.queryByRole("button", { name: "TERMINAR" })).toBeNull();
  });

  it("con incidente VIVO el banner se degrada a badge: lo real domina", () => {
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.tenant_admin });
    mocks.useActiveDrill.mockReturnValue(drillData({ drill: DRILL }));
    render(<DrillBanner hasLiveIncident={true} />);
    expect(screen.getByTestId("drill-badge")).toHaveTextContent("LA ALERTA REAL DOMINA");
    expect(screen.queryByTestId("drill-banner")).toBeNull();
  });

  it("sin drill: solo quien tiene drill_start ve el control de inicio", () => {
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.soc_operator });
    mocks.useActiveDrill.mockReturnValue(drillData());
    const { unmount } = render(<DrillBanner hasLiveIncident={false} />);
    expect(screen.queryByRole("button", { name: /INICIAR SIMULACRO/ })).toBeNull();
    unmount();

    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.tenant_admin });
    mocks.useActiveDrill.mockReturnValue(drillData());
    render(<DrillBanner hasLiveIncident={false} />);
    fireEvent.click(screen.getByRole("button", { name: /INICIAR SIMULACRO/ }));
    expect(screen.getByTestId("drill-modal")).toBeInTheDocument();
  });

  it("tenant_admin puede TERMINAR el drill activo", () => {
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.tenant_admin });
    const stop = vi.fn();
    mocks.useActiveDrill.mockReturnValue(drillData({ drill: DRILL, stop }));
    render(<DrillBanner hasLiveIncident={false} />);
    fireEvent.click(screen.getByRole("button", { name: "TERMINAR" }));
    expect(stop).toHaveBeenCalledWith("d-1");
  });

  // --- El bug que motivó la reescritura ------------------------------------

  it("si /drills/active FALLA con el simulacro vivo, el banner NO desaparece", () => {
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.soc_operator });
    mocks.useActiveDrill.mockReturnValue(
      drillData({ drill: DRILL, readError: "GET /drills/active falló (503)" }),
    );
    const { container } = render(<DrillBanner hasLiveIncident={false} />);
    // Sigue visible y rotulado NO-real…
    expect(screen.getByTestId("drill-banner")).toHaveTextContent("ESTO NO ES UNA ALERTA REAL");
    // …pero declarado como dato RETENIDO, jamás como lectura viva.
    expect(container.querySelector('[data-state="stale"]')).not.toBeNull();
    expect(screen.getByText(/DATOS RETENIDOS/)).toBeInTheDocument();
  });

  it("sin ningún dato conocido, el fallo se MUESTRA (no se calla)", () => {
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.soc_operator });
    const refetch = vi.fn();
    mocks.useActiveDrill.mockReturnValue(
      drillData({ readError: "GET /drills/active falló (503)", refetch }),
    );
    const { container } = render(<DrillBanner hasLiveIncident={false} />);
    expect(container.querySelector('[data-state="error"]')).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "REINTENTAR" }));
    expect(refetch).toHaveBeenCalled();
  });

  it("mientras carga NO afirma que no hay simulacro", () => {
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.soc_operator });
    mocks.useActiveDrill.mockReturnValue(drillData({ loading: true }));
    const { container } = render(<DrillBanner hasLiveIncident={false} />);
    expect(container.querySelector('[data-state="loading"]')).not.toBeNull();
    expect(screen.queryByTestId("drill-banner")).toBeNull();
  });

  it("materializa los 4 estados obligatorios (regla de oro 7)", () => {
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.soc_operator });
    const byState: Record<UiState, Partial<ActiveDrillData>> = {
      loading: { loading: true },
      error: { readError: "boom" },
      empty: {},
      stale: { drill: DRILL, readError: "boom" },
    };
    expectFourStates((state) => {
      mocks.useActiveDrill.mockReturnValue(drillData(byState[state]));
      return <DrillBanner hasLiveIncident={false} />;
    });
  });

  // --- Simulacro ARMADO ------------------------------------------------------

  it("a T−15 min aparece el banner armado; el disparo aún no está habilitado", () => {
    vi.setSystemTime(Date.parse("2026-08-04T17:55:00Z"));
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.tenant_admin });
    mocks.useActiveDrill.mockReturnValue(drillData({ scheduled: [AGENDA] }));
    render(<DrillBanner hasLiveIncident={false} />);
    const armed = screen.getByTestId("drill-armed");
    expect(armed).toHaveTextContent("SIMULACRO ARMADO");
    expect(armed).toHaveTextContent("18:05:00");
    expect(screen.getByRole("button", { name: "EJECUTAR AHORA" })).toBeDisabled();
  });

  it("fuera de la ventana de armado no hay banner", () => {
    vi.setSystemTime(Date.parse("2026-08-04T17:30:00Z"));
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.tenant_admin });
    mocks.useActiveDrill.mockReturnValue(drillData({ scheduled: [AGENDA] }));
    render(<DrillBanner hasLiveIncident={false} />);
    expect(screen.queryByTestId("drill-armed")).toBeNull();
  });

  it("a T−0 EJECUTAR AHORA queda precargado: un clic humano, con su agenda", () => {
    vi.setSystemTime(Date.parse("2026-08-04T18:06:00Z"));
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.tenant_admin });
    const start = vi.fn();
    mocks.useActiveDrill.mockReturnValue(drillData({ scheduled: [AGENDA], start }));
    render(<DrillBanner hasLiveIncident={false} />);
    const run = screen.getByRole("button", { name: "EJECUTAR AHORA" });
    expect(run).toBeEnabled();
    fireEvent.click(run);
    expect(start).toHaveBeenCalledWith({ fromScheduled: "ag-1" });
  });

  it("CANCELAR retira la agenda antes de que ocurra", () => {
    vi.setSystemTime(Date.parse("2026-08-04T17:55:00Z"));
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.tenant_admin });
    const cancel = vi.fn();
    mocks.useActiveDrill.mockReturnValue(drillData({ scheduled: [AGENDA], cancel }));
    render(<DrillBanner hasLiveIncident={false} />);
    fireEvent.click(screen.getByRole("button", { name: "CANCELAR" }));
    expect(cancel).toHaveBeenCalledWith("ag-1");
  });

  it("un rol sin drill_start VE el armado pero no puede tocarlo", () => {
    vi.setSystemTime(Date.parse("2026-08-04T17:55:00Z"));
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.soc_operator });
    mocks.useActiveDrill.mockReturnValue(drillData({ scheduled: [AGENDA] }));
    render(<DrillBanner hasLiveIncident={false} />);
    expect(screen.getByTestId("drill-armed")).toHaveTextContent("SIMULACRO ARMADO");
    expect(screen.queryByRole("button", { name: "EJECUTAR AHORA" })).toBeNull();
    expect(screen.queryByRole("button", { name: "CANCELAR" })).toBeNull();
  });

  it("el simulacro EN CURSO manda sobre el armado", () => {
    vi.setSystemTime(Date.parse("2026-08-04T17:55:00Z"));
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.tenant_admin });
    mocks.useActiveDrill.mockReturnValue(drillData({ drill: DRILL, scheduled: [AGENDA] }));
    render(<DrillBanner hasLiveIncident={false} />);
    expect(screen.getByTestId("drill-banner")).toBeInTheDocument();
    expect(screen.queryByTestId("drill-armed")).toBeNull();
  });

  it("el historial lo abre cualquier rol de consola (es evidencia, no una acción)", () => {
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.gov_operator });
    mocks.useActiveDrill.mockReturnValue(drillData());
    render(<DrillBanner hasLiveIncident={false} />);
    fireEvent.click(screen.getByRole("button", { name: "HISTORIAL" }));
    expect(screen.getByTestId("drill-history")).toBeInTheDocument();
  });

  it("un error de mutación se muestra en texto accionable", () => {
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.tenant_admin });
    mocks.useActiveDrill.mockReturnValue(
      drillData({ error: "el simulacro no arrancó (HTTP 409)" }),
    );
    render(<DrillBanner hasLiveIncident={false} />);
    expect(screen.getByRole("alert")).toHaveTextContent("HTTP 409");
  });
});
