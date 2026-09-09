import { fireEvent, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resetSessionStoreForTests, useSessionStore } from "../auth/session.store";
import { ME_FIXTURES } from "../test-utils/meFixtures";
import { renderRoutesAt, seedAuthenticated } from "../test-utils/renderRoutes";
import { DEV_TENANT_DEFAULT } from "./LoginPage";

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
      tenant_id: DEV_TENANT_DEFAULT,
    });
  });

  it("el tenant dev por defecto es el de la flota sembrada", () => {
    // Un tenant sin sitios deja `/console` en el estado `empty` y el mapa no aparece.
    // El valor debe seguir al de `db/seeds/dev_fleet.sql`.
    expect(DEV_TENANT_DEFAULT).toBe("d0000000-0000-0000-0000-000000000001");
  });

  it("sin VITE_DEV_TOKEN_ENABLED no hay panel dev", () => {
    // Explícito (no ambiental): un web/.env local con la flag en true no debe
    // volver este test flaky — se aísla del entorno.
    vi.stubEnv("VITE_DEV_TOKEN_ENABLED", "");
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

  it("sin Cognito configurado la nota le habla al operador, no al que despliega", () => {
    // [T-6.07] Este test AFIRMABA el literal viejo («Cognito no configurado
    // (VITE_COGNITO_*)»), así que el copy y él cambian en el mismo commit. Lo
    // que se defiende ahora no es una frase, son las tres cosas que quien está
    // de turno necesita: que desde aquí no se entra, a quién avisar, y que el
    // edificio sigue protegido (reglas de oro 1 y 2).
    renderRoutesAt("/");
    expect(screen.queryByRole("button", { name: "ENTRAR CON COGNITO" })).not.toBeInTheDocument();
    const nota = screen.getByText(/no tiene identidad configurada/);
    expect(nota).toHaveTextContent(/Avise a quien la desplegó/);
    expect(nota).toHaveTextContent(/NO depende de esta pantalla/);
    // Y NINGUNA variable de build en el texto: ese detalle es del `title`, que
    // es donde lo busca quien desplegó y no se le pone delante a nadie más.
    expect(nota.textContent).not.toMatch(/VITE_/);
    expect(nota).toHaveAttribute("title", expect.stringContaining("VITE_COGNITO_AUTHORITY"));
  });

  it("tras una expiración la landing dice POR QUÉ se cerró la sesión", () => {
    // [T-6.07] `handleUnauthorized` limpiaba en silencio y el operador
    // reaparecía en un login idéntico al de un arranque en frío. La causa viaja
    // en un CAMPO (`endedReason`), no en un `SessionStatus` nuevo: el estado
    // sigue siendo `anonymous`, que es lo que es.
    useSessionStore.getState().handleUnauthorized();
    renderRoutesAt("/");

    const aviso = screen.getByTestId("login-sesion-cerrada");
    expect(aviso).toHaveTextContent(/SU SESIÓN SE CERRÓ/);
    // No se inventa la causa: un 401 puede ser expiración o revocación.
    expect(aviso).toHaveTextContent(/expiró o fue revocada/);
    // Anunciado, no solo pintado: quien usa lector de pantalla no ve el panel.
    expect(aviso).toHaveAttribute("role", "status");
  });

  it("un arranque en frío NO acusa a nadie de haber expirado", () => {
    // El aviso solo existe cuando hubo un episodio anterior; en un login normal
    // sería una alarma falsa, y una consola que alarma sin causa se ignora.
    renderRoutesAt("/");
    expect(screen.queryByTestId("login-sesion-cerrada")).not.toBeInTheDocument();
  });

  it("autenticado en / redirige al landing del rol (primera allowed_route)", () => {
    seedAuthenticated(ME_FIXTURES.soc_operator);
    const router = renderRoutesAt("/");
    expect(router.state.location.pathname).toBe("/console");
    expect(screen.getByRole("heading", { name: "Monitoreo en Vivo" })).toBeInTheDocument();
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
