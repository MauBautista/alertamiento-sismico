import { fireEvent, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resetSessionStoreForTests, useSessionStore } from "../auth/session.store";
import { ME_FIXTURES } from "../test-utils/meFixtures";
import { renderRoutesAt, seedAuthenticated } from "../test-utils/renderRoutes";

describe("LoginPage", () => {
  beforeEach(() => {
    resetSessionStoreForTests();
    useSessionStore.setState({ status: "anonymous" });
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("muestra el panel dev solo con VITE_DEV_TOKEN_ENABLED y llama loginDev", () => {
    vi.stubEnv("VITE_DEV_TOKEN_ENABLED", "true");
    const loginDev = vi.fn().mockResolvedValue(undefined);
    useSessionStore.setState({ loginDev });

    renderRoutesAt("/");

    fireEvent.change(screen.getByLabelText("ROL"), { target: { value: "gov_operator" } });
    fireEvent.click(screen.getByRole("button", { name: "ENTRAR COMO ROL" }));

    expect(loginDev).toHaveBeenCalledWith({
      role: "gov_operator",
      tenant_id: "11111111-1111-1111-1111-111111111111",
    });
  });

  it("sin VITE_DEV_TOKEN_ENABLED no hay panel dev", () => {
    renderRoutesAt("/");
    expect(screen.queryByText(/LOGIN DEV/)).not.toBeInTheDocument();
  });

  it("con Cognito configurado el botón llama loginCognito con el returnTo", () => {
    vi.stubEnv("VITE_COGNITO_AUTHORITY", "https://cognito-idp.us-east-2.amazonaws.com/x");
    vi.stubEnv("VITE_COGNITO_CLIENT_ID", "client-abc");
    const loginCognito = vi.fn().mockResolvedValue(undefined);
    useSessionStore.setState({ loginCognito });

    renderRoutesAt("/", { returnTo: "/fleet" });

    fireEvent.click(screen.getByRole("button", { name: "ENTRAR CON COGNITO" }));
    expect(loginCognito).toHaveBeenCalledWith("/fleet");
  });

  it("sin Cognito configurado muestra la nota en lugar del botón", () => {
    renderRoutesAt("/");
    expect(screen.queryByRole("button", { name: "ENTRAR CON COGNITO" })).not.toBeInTheDocument();
    expect(screen.getByText(/Cognito no configurado/)).toBeInTheDocument();
  });

  it("autenticado en / redirige al landing del rol (primera allowed_route)", () => {
    seedAuthenticated(ME_FIXTURES.soc_operator);
    const router = renderRoutesAt("/");
    expect(router.state.location.pathname).toBe("/console");
    expect(screen.getByRole("heading", { name: "CONSOLA C4I" })).toBeInTheDocument();
  });

  it("autenticado con returnTo honra el deep-link original", () => {
    seedAuthenticated(ME_FIXTURES.soc_operator);
    const router = renderRoutesAt("/", { returnTo: "/fleet" });
    expect(router.state.location.pathname).toBe("/fleet");
    expect(
      screen.getByRole("heading", { name: "Flota Edge y Estado de Gabinetes" }),
    ).toBeInTheDocument();
  });

  it("rol mobile-only autenticado ⇒ pantalla sin superficie web", () => {
    seedAuthenticated(ME_FIXTURES.occupant);
    const router = renderRoutesAt("/");
    expect(screen.getByText("SIN SUPERFICIE WEB")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/");
  });
});
