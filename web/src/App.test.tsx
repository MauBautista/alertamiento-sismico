import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import App from "./App";
import { resetSessionStoreForTests } from "./auth/session.store";

describe("App", () => {
  beforeEach(() => {
    resetSessionStoreForTests();
  });

  it("arranca y aterriza en el login público al quedar anonymous", async () => {
    render(<App />);
    // Sin sesión previa ni Cognito configurado, bootstrap resuelve a anonymous
    // de forma síncrona (el splash de booting se cubre en routes.guards.test).
    expect(await screen.findByRole("heading", { name: "CONSOLA SOC" })).toBeInTheDocument();
  });
});
