// [T-8.03 · D-38 · A-039] El aviso previo al tope de la sesión.
//
// Un operador SOC cuyo turno cruza la hora 24 tendría que teclear contraseña y
// código en el peor momento posible (en plena emergencia, si coincide). El aviso
// le da la hora exacta con 60 minutos de margen para RENOVAR en un momento
// tranquilo. No hay prórroga: renovar ES volver a entrar.
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resetSessionStoreForTests, useSessionStore } from "../auth/session.store";
import { ME_FIXTURES } from "../test-utils/meFixtures";
import SessionExpiryBanner, { AVISO_PREVIO_MS } from "./SessionExpiryBanner";

// 2026-09-22 12:00 en Ciudad de México (UTC−6, sin horario de verano desde 2022).
const AHORA = Date.parse("2026-09-22T18:00:00Z");
const MIN = 60_000;

function sembrar(extra: Partial<ReturnType<typeof useSessionStore.getState>>): void {
  useSessionStore.setState({
    status: "authenticated",
    origin: "dev",
    idToken: "t",
    me: ME_FIXTURES.soc_operator,
    ...extra,
  });
}

describe("SessionExpiryBanner", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date", "setInterval", "clearInterval"] });
    vi.setSystemTime(AHORA);
    resetSessionStoreForTests();
  });

  afterEach(() => {
    vi.useRealTimers();
    resetSessionStoreForTests();
  });

  it("el margen es de 60 minutos", () => {
    expect(AVISO_PREVIO_MS).toBe(60 * MIN);
  });

  it("sin dato del plazo NO pinta nada: no se inventa cuándo termina", () => {
    sembrar({ sessionExpiresAt: null, loginAt: null, sessionMaxAgeS: null });
    const { container } = render(<SessionExpiryBanner />);
    expect(container).toBeEmptyDOMElement();
  });

  it("con el plazo a más de 60 min tampoco (no es ruido de todo el turno)", () => {
    sembrar({ sessionExpiresAt: AHORA + 61 * MIN });
    const { container } = render(<SessionExpiryBanner />);
    expect(container).toBeEmptyDOMElement();
  });

  it("dentro de la última hora dice la HORA exacta, en la hora de la sala (CST)", () => {
    sembrar({ sessionExpiresAt: AHORA + 45 * MIN });
    render(<SessionExpiryBanner />);

    const aviso = screen.getByTestId("session-expiry-banner");
    // 18:45Z = 12:45 en Ciudad de México.
    expect(aviso).toHaveTextContent("SU SESIÓN TERMINA A LAS 12:45 CST");
    expect(aviso).toHaveAttribute("role", "status");
    expect(screen.getByRole("button", { name: "RENOVAR AHORA" })).toBeInTheDocument();
  });

  it("RENOVAR AHORA cierra la sesión para volver a entrar — no hay prórroga", () => {
    const logout = vi.fn().mockResolvedValue(undefined);
    sembrar({ sessionExpiresAt: AHORA + 10 * MIN, logout });
    render(<SessionExpiryBanner />);

    fireEvent.click(screen.getByRole("button", { name: "RENOVAR AHORA" }));

    expect(logout).toHaveBeenCalledTimes(1);
  });

  it("aparece SOLO al cruzar la marca de 60 min, con el reloj compartido", () => {
    sembrar({ sessionExpiresAt: AHORA + 61 * MIN });
    render(<SessionExpiryBanner />);
    expect(screen.queryByTestId("session-expiry-banner")).not.toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(2 * MIN);
    });

    expect(screen.getByTestId("session-expiry-banner")).toHaveTextContent("13:01");
  });

  it("manda el plazo EFECTIVO: si la marca del login vence antes que el servidor, esa hora", () => {
    // El servidor dice 13:30 (auth_time movido por un refresco); la marca del
    // login + 24 h cae a las 12:20. La hora que se anuncia es la que va a pasar.
    sembrar({
      sessionExpiresAt: AHORA + 90 * MIN,
      loginAt: AHORA + 20 * MIN - 86_400_000,
      sessionMaxAgeS: 86_400,
    });
    render(<SessionExpiryBanner />);

    expect(screen.getByTestId("session-expiry-banner")).toHaveTextContent("12:20");
  });

  it("con el plazo ya cumplido no pinta: quien cierra es el store, no el aviso", () => {
    sembrar({ sessionExpiresAt: AHORA - 1 });
    const { container } = render(<SessionExpiryBanner />);
    expect(container).toBeEmptyDOMElement();
  });
});
