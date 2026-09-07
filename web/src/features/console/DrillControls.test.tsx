// [T-6.01] La tira de acciones del simulacro, que se queda en /console.
//
// Lo que se mide: los gates de matriz (INICIAR sólo con `drill_start`), que el
// historial lo abre cualquiera (es evidencia, no una acción), que el fallo de
// INICIAR se pinta junto al botón, y que mientras no se sabe si hay simulacro
// no se ofrece arrancar otro. El BANNER ya no es de aquí: `features/scene`.

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

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
import DrillControls from "./DrillControls";
import type { ActiveDrillData } from "./useActiveDrill";

function drillData(over: Partial<ActiveDrillData> = {}): ActiveDrillData {
  return {
    drill: null,
    scheduled: [],
    loading: false,
    readError: null,
    updatedAt: 0,
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
  sites: [],
};

beforeEach(() => {
  resetSessionStoreForTests();
  vi.clearAllMocks();
  mocks.useActiveDrill.mockReturnValue(drillData());
});

describe("DrillControls", () => {
  it("sin drill: solo quien tiene drill_start ve el control de inicio", () => {
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.soc_operator });
    const { unmount } = render(<DrillControls />);
    expect(screen.queryByRole("button", { name: /INICIAR SIMULACRO/ })).toBeNull();
    unmount();

    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.tenant_admin });
    render(<DrillControls />);
    fireEvent.click(screen.getByRole("button", { name: /INICIAR SIMULACRO/ }));
    expect(screen.getByTestId("drill-modal")).toBeInTheDocument();
  });

  it("con un simulacro EN CURSO no se ofrece arrancar otro", () => {
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.tenant_admin });
    mocks.useActiveDrill.mockReturnValue(drillData({ drill: DRILL }));
    render(<DrillControls />);
    expect(screen.queryByRole("button", { name: /INICIAR SIMULACRO/ })).toBeNull();
    // El botón de TERMINAR vive en el banner del shell, no aquí.
    expect(screen.queryByRole("button", { name: "TERMINAR" })).toBeNull();
  });

  it("mientras no se sabe si hay uno en curso, tampoco", () => {
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.tenant_admin });
    mocks.useActiveDrill.mockReturnValue(drillData({ loading: true }));
    render(<DrillControls />);
    expect(screen.queryByRole("button", { name: /INICIAR SIMULACRO/ })).toBeNull();
  });

  it("el historial lo abre cualquier rol de consola (es evidencia, no una acción)", () => {
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.gov_operator });
    render(<DrillControls />);
    fireEvent.click(screen.getByRole("button", { name: "HISTORIAL" }));
    expect(screen.getByTestId("drill-history")).toBeInTheDocument();
  });

  it("un error de INICIAR se muestra en texto accionable, junto al botón", () => {
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.tenant_admin });
    mocks.useActiveDrill.mockReturnValue(
      drillData({ error: "el simulacro no arrancó (HTTP 409)" }),
    );
    render(<DrillControls />);
    expect(screen.getByRole("alert")).toHaveTextContent("HTTP 409");
  });

  it("el fallo de TERMINAR no se duplica aquí: con drill vivo lo pinta el banner del shell", () => {
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.tenant_admin });
    mocks.useActiveDrill.mockReturnValue(
      drillData({ drill: DRILL, error: "el simulacro no se detuvo (HTTP 502)" }),
    );
    render(<DrillControls />);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("la tira NO pasa por un marco: `drill-idle` tiene que existir en todo estado", () => {
    // El e2e de T-1.62 mide `drill-idle` (< 60 px); dentro de un StateFrame
    // desaparecería en `loading` y el operador se quedaría sin HISTORIAL.
    useSessionStore.setState({ status: "authenticated", me: ME_FIXTURES.soc_operator });
    mocks.useActiveDrill.mockReturnValue(drillData({ loading: true }));
    render(<DrillControls />);
    expect(screen.getByTestId("drill-idle")).toBeInTheDocument();
  });
});
