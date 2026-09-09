/**
 * [T-6.07] El splash decía lo mismo a los 0.3 s que a los 30.
 *
 * «INICIANDO CONSOLA SOC…» es verdad siempre, y por eso no informa de nada: no
 * distingue «va lento» de «se colgó», que es la única pregunta que se hace
 * quien lo mira. En una sala de operación esa duda se resuelve recargando a
 * ciegas — y recargar durante un arranque lento lo alarga.
 */
import { act, render, screen } from "@testing-library/react";
import { tokens, toNumber } from "@takab/design-tokens";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SplashScreen } from "./StatusScreens";

/** El umbral es del PAQUETE, no un número copiado aquí: si mañana se decide
 * que dos segundos es demasiado tarde, este test sigue midiendo lo correcto. */
const UMBRAL_MS = toNumber(tokens.wait.declare);

describe("SplashScreen · una espera que sigue esperando dice qué espera", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("se ANUNCIA, no solo se pinta", () => {
    render(<SplashScreen />);
    // Sin `role="status"` un lector de pantalla lee el rótulo una vez y calla:
    // quien no ve la pantalla no se entera de que sigue esperando.
    const panel = screen.getByRole("status");
    expect(panel).toHaveTextContent("INICIANDO CONSOLA SOC…");
    expect(panel).toHaveAttribute("aria-live", "polite");
  });

  it("antes del umbral NO alarma", () => {
    render(<SplashScreen />);
    act(() => vi.advanceTimersByTime(UMBRAL_MS - 500));
    expect(screen.queryByTestId("splash-tardando")).not.toBeInTheDocument();
  });

  it("pasado el umbral dice QUÉ espera y DESDE CUÁNDO", () => {
    render(<SplashScreen />);
    act(() => vi.advanceTimersByTime(UMBRAL_MS + 1_000));

    const aviso = screen.getByTestId("splash-tardando");
    expect(aviso).toHaveTextContent("ESTO ESTÁ TARDANDO");
    expect(aviso).toHaveTextContent("la sesión del operador (/me)");
    expect(aviso).toHaveTextContent(/desde hace \d+ s/);
  });

  it("el contador SIGUE corriendo: es la diferencia entre lento y colgado", () => {
    render(<SplashScreen />);
    act(() => vi.advanceTimersByTime(UMBRAL_MS + 1_000));
    const primero = leerSegundos();
    act(() => vi.advanceTimersByTime(5_000));
    expect(leerSegundos()).toBeGreaterThan(primero);
  });

  it("cada sitio declara SU espera: no es lo mismo `/me` que la vuelta de Cognito", () => {
    // Confundirlas manda a mirar el sitio equivocado — la API propia o el
    // proveedor de identidad son dos diagnósticos distintos.
    render(<SplashScreen espera="la vuelta de Cognito" />);
    act(() => vi.advanceTimersByTime(UMBRAL_MS + 1_000));
    expect(screen.getByTestId("splash-tardando")).toHaveTextContent("la vuelta de Cognito");
  });
});

function leerSegundos(): number {
  const texto = screen.getByTestId("splash-tardando").textContent ?? "";
  return Number(/desde hace (\d+) s/.exec(texto)?.[1] ?? "-1");
}
