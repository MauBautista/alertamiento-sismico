// [T-5.02 · D-27] Banner del MODO DEMOSTRACIÓN.
//
// Lo que fija, y en este orden:
//  1. los CUATRO estados sobre `/demo-mode` (regla de oro 7). El caso que
//     importa: si la lectura falla con el modo PUESTO, el banner **no
//     desaparece** — un modo de supresión que deja de anunciarse es
//     indistinguible de un sistema que sí está avisando;
//  2. dice las dos cosas que hay que decir: que nadie recibe avisos, y que la
//     protección local del gabinete SIGUE ARMADA. La segunda evita la lectura
//     más peligrosa posible — que alguien crea que el edificio está desprotegido;
//  3. el botón de salir lo ve quien puede apagarlo, y solo ése.

import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ useDemoMode: vi.fn() }));
vi.mock("./useDemoMode", () => ({ useDemoMode: mocks.useDemoMode }));

import { resetSessionStoreForTests, useSessionStore } from "../../auth/session.store";
import { ME_FIXTURES } from "../../test-utils/meFixtures";
import { expectFourStates, type UiState } from "../../test-utils/states";
import DemoModeBanner, { restanteLegible } from "./DemoModeBanner";
import type { DemoModeData } from "./useDemoMode";

const NOW = Date.parse("2026-09-02T18:00:00Z");

function datos(over: Partial<DemoModeData> = {}): DemoModeData {
  return {
    demo: null,
    loading: false,
    readError: false,
    updatedAt: NOW - 5_000,
    refetch: vi.fn(),
    encender: vi.fn(),
    apagar: vi.fn(),
    pending: false,
    ...over,
  };
}

const ACTIVO = {
  active: true,
  tenant_id: "t-1",
  enabled_by: "u-1",
  enabled_at: "2026-09-02T17:00:00Z",
  expires_at: "2026-09-02T19:00:00Z",
  remaining_s: 3600,
  note: "demo con cliente",
};

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(NOW);
  resetSessionStoreForTests();
  useSessionStore.setState({ me: ME_FIXTURES.takab_superadmin });
  mocks.useDemoMode.mockReturnValue(datos());
});

afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe("DemoModeBanner", () => {
  it("apagado no pinta banner: cero ruido en el caso normal", () => {
    render(<DemoModeBanner />);
    expect(screen.queryByTestId("demo-mode-banner")).toBeNull();
  });

  it("encendido dice que NO se avisa a nadie NI se acciona nada", () => {
    mocks.useDemoMode.mockReturnValue(datos({ demo: ACTIVO }));
    render(<DemoModeBanner />);
    const caja = screen.getByTestId("demo-mode-banner");
    expect(caja).toHaveTextContent("MODO DEMOSTRACIÓN");
    expect(caja).toHaveTextContent("NO SE AVISA A NADIE NI SE ACCIONA NADA");
  });

  it("y dice que la protección del gabinete SIGUE ARMADA", () => {
    // La lectura peligrosa que este texto cierra: que alguien concluya que el
    // edificio está desprotegido mientras dura la demostración. No lo está — el
    // gabinete no sabe que este modo existe.
    mocks.useDemoMode.mockReturnValue(datos({ demo: ACTIVO }));
    render(<DemoModeBanner />);
    expect(screen.getByTestId("demo-mode-banner")).toHaveTextContent(
      "La protección local del gabinete sigue armada",
    );
  });

  it("pinta cuánto le queda: nadie tiene que restar dos horas UTC de cabeza", () => {
    mocks.useDemoMode.mockReturnValue(datos({ demo: ACTIVO }));
    render(<DemoModeBanner />);
    expect(screen.getByTestId("demo-mode-banner")).toHaveTextContent("TERMINA SOLO EN 1 h 00 m");
  });

  it("el botón de salir lo ve quien puede apagarlo", () => {
    mocks.useDemoMode.mockReturnValue(datos({ demo: ACTIVO }));
    render(<DemoModeBanner />);
    fireEvent.click(screen.getByTestId("demo-mode-off"));
    expect(mocks.useDemoMode.mock.results[0].value.apagar).toHaveBeenCalled();
  });

  it("quien NO puede apagarlo lo ve igual, pero sin botón", () => {
    // Ver el estado no es un privilegio: quien no lo encendió es justo quien se
    // va a preguntar por qué no le llegó un aviso.
    useSessionStore.setState({ me: ME_FIXTURES.soc_operator });
    mocks.useDemoMode.mockReturnValue(datos({ demo: ACTIVO }));
    render(<DemoModeBanner />);
    expect(screen.getByTestId("demo-mode-banner")).toBeInTheDocument();
    expect(screen.queryByTestId("demo-mode-off")).toBeNull();
  });

  it("declara los cuatro estados obligatorios (regla de oro 7)", () => {
    const byState: Record<UiState, Partial<DemoModeData>> = {
      loading: { loading: true },
      error: { readError: true },
      empty: {},
      // El caso que importa: lectura caída CON el modo puesto. El banner se
      // conserva y se rotula viejo; jamás desaparece en silencio.
      stale: { demo: ACTIVO, readError: true },
    };
    expectFourStates((state) => {
      mocks.useDemoMode.mockReturnValue(datos(byState[state]));
      return <DemoModeBanner />;
    });
  });
});

describe("restanteLegible", () => {
  it("no inventa precisión que nadie necesita", () => {
    expect(restanteLegible(7320)).toBe("2 h 02 m");
    expect(restanteLegible(600)).toBe("10 m");
    expect(restanteLegible(-5)).toBe("0 m");
  });
});
