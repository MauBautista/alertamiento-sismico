import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { resetSessionStoreForTests, useSessionStore } from "../auth/session.store";
import { ME_FIXTURES } from "../test-utils/meFixtures";
import { renderRoutesAt, seedAuthenticated } from "../test-utils/renderRoutes";

describe("AuthCallbackPage", () => {
  beforeEach(() => {
    resetSessionStoreForTests();
  });

  it("éxito ⇒ navega al returnTo del state OIDC", async () => {
    const completeCognitoCallback = vi.fn().mockImplementation(() => {
      seedAuthenticated(ME_FIXTURES.soc_operator);
      return Promise.resolve({ returnTo: "/fleet" });
    });
    useSessionStore.setState({ completeCognitoCallback });

    const router = renderRoutesAt("/auth/callback");

    expect(
      await screen.findByRole("heading", { name: "Flota Edge y Estado de Gabinetes" }),
    ).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/fleet");
    expect(completeCognitoCallback).toHaveBeenCalledTimes(1);
  });

  it("éxito sin returnTo ⇒ navega al landing del rol", async () => {
    const completeCognitoCallback = vi.fn().mockImplementation(() => {
      seedAuthenticated(ME_FIXTURES.tenant_admin);
      return Promise.resolve({});
    });
    useSessionStore.setState({ completeCognitoCallback });

    const router = renderRoutesAt("/auth/callback");

    expect(await screen.findByRole("heading", { name: "CONSOLA C4I" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/console");
  });

  it("fallo ⇒ muestra el error y el link de vuelta al inicio", async () => {
    const completeCognitoCallback = vi
      .fn()
      .mockRejectedValue(new Error("No matching state found in storage"));
    useSessionStore.setState({ status: "anonymous", completeCognitoCallback });

    renderRoutesAt("/auth/callback");

    expect(await screen.findByRole("heading", { name: "ERROR DE LOGIN" })).toBeInTheDocument();
    expect(screen.getByText(/No matching state/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "VOLVER AL INICIO" })).toHaveAttribute("href", "/");
  });
});
