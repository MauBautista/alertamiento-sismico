/**
 * T-2.123 · La consola con Postgres caído.
 *
 * `T-2.114` hizo que `GET /me` abriera sesión de base (de ahí sale el inmueble
 * del ocupante), así que dejó de ser claims puros: con Postgres caído `/me`
 * responde 5xx y la consola se quedaba sin arrancar. La decisión ratificada es
 * ARRANCAR EN DEGRADADO — el porqué está escrito en `DegradedSessionScreen.tsx`.
 *
 * Estos tests fijan las DOS mitades de la decisión, que tiran en direcciones
 * opuestas y por eso se prueban juntas:
 *
 *   1. Arranca (regla de oro 7): con la base caída hay pantalla, y la pantalla
 *      DECLARA exactamente lo que no sabe.
 *   2. No es una puerta trasera (regla de oro 5): sin `/me` no hay alcance, y
 *      sin alcance NINGUNA ruta llega a pintar un dato de tenant ni a pedirlo.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ getMe: vi.fn() }));

// `getMe` mockeado, `MeRequestError` real: el store discrimina por instancia+status.
vi.mock("../auth/me", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../auth/me")>();
  return { ...actual, getMe: mocks.getMe };
});

vi.mock("./navigation", () => ({ hardRedirect: vi.fn() }));

import App from "../App";
import { saveDevSession } from "../auth/devToken";
import { MeRequestError } from "../auth/me";
import { resetSessionStoreForTests, useSessionStore } from "../auth/session.store";
import { ALL_ROUTES, ME_FIXTURES, TENANT_ID } from "../test-utils/meFixtures";
import { renderRoutesAt, seedAuthenticated } from "../test-utils/renderRoutes";

const DEGRADED_TITLE = "CONSOLA EN MODO DEGRADADO";

/** URL real de cada clave de ruta (la paramétrica incluida). */
const URL_BY_ROUTE: Record<(typeof ALL_ROUTES)[number], string> = {
  "/console": "/console",
  "/fleet": "/fleet",
  "/triage": "/triage",
  "/tenants": "/tenants",
  "/audit": "/audit",
  "/building": "/building/S-001",
};

/** Encabezado que cada página pinta cuando SÍ hay alcance. En degradado no debe
 * aparecer ninguno: es la forma directa de decir "no se pintó la pantalla". */
const HEADING_BY_ROUTE: Record<(typeof ALL_ROUTES)[number], string> = {
  "/console": "Monitoreo en Vivo",
  "/fleet": "Flota Edge y Estado de Gabinetes",
  "/triage": "Evaluación Estructural Post-Sismo",
  "/tenants": "Matriz Multi-Tenant y Umbrales",
  "/audit": "Bitácora de Auditoría",
  "/building": "DASHBOARD EDIFICIO",
};

let fetchSpy: ReturnType<typeof vi.fn>;

function stubEnv(): void {
  vi.stubEnv("VITE_API_BASE_URL", "/api");
  vi.stubEnv("VITE_DEV_TOKEN_ENABLED", "true");
}

beforeEach(() => {
  window.sessionStorage.clear();
  mocks.getMe.mockReset();
  stubEnv();
  // Cualquier petición a la API en degradado es un fallo de esta ficha.
  fetchSpy = vi.fn().mockRejectedValue(new Error("la base está caída"));
  vi.stubGlobal("fetch", fetchSpy);
  resetSessionStoreForTests();
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("T-2.123 · arranque con la base de datos caída", () => {
  it("CRITERIO · arranca y declara que no puede establecer el alcance", async () => {
    saveDevSession({ idToken: "dev-tok", expiresAt: Date.now() + 60_000 });
    mocks.getMe.mockRejectedValue(new MeRequestError(503));

    render(<App />);

    // Arranca: hay pantalla, no un blanco ni un crash.
    expect(await screen.findByRole("heading", { name: DEGRADED_TITLE })).toBeInTheDocument();
    // Y declara QUÉ no sabe, en términos del operador.
    expect(screen.getByText(/no puede establecer el alcance de su operador/i)).toBeInTheDocument();
    // Con el detalle verificable de por qué (para soporte).
    expect(screen.getByText(/GET \/me falló \(503\)/)).toBeInTheDocument();
    // Y dice lo que SÍ sigue en pie, que es lo accionable en un incidente.
    expect(screen.getByText(/cada gabinete sigue detectando y accionando/i)).toBeInTheDocument();
  });

  it("no inventa alcance: `me` queda en null y no se pide ni un dato a la API", async () => {
    saveDevSession({ idToken: "dev-tok", expiresAt: Date.now() + 60_000 });
    mocks.getMe.mockRejectedValue(new MeRequestError(500));

    render(<App />);
    await screen.findByRole("heading", { name: DEGRADED_TITLE });

    expect(useSessionStore.getState().status).toBe("degraded");
    expect(useSessionStore.getState().me).toBeNull();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("un error de red (sin status HTTP) también arranca en degradado", async () => {
    saveDevSession({ idToken: "dev-tok", expiresAt: Date.now() + 60_000 });
    mocks.getMe.mockRejectedValue(new Error("ECONNREFUSED"));

    render(<App />);

    expect(await screen.findByRole("heading", { name: DEGRADED_TITLE })).toBeInTheDocument();
    expect(screen.getByText(/ECONNREFUSED/)).toBeInTheDocument();
  });

  it("REINTENTAR: con la base de vuelta la consola entra normal", async () => {
    saveDevSession({ idToken: "dev-tok", expiresAt: Date.now() + 60_000 });
    mocks.getMe.mockRejectedValue(new MeRequestError(503));

    render(<App />);
    await screen.findByRole("heading", { name: DEGRADED_TITLE });

    mocks.getMe.mockReset();
    mocks.getMe.mockResolvedValue(ME_FIXTURES.soc_operator);
    fireEvent.click(screen.getByRole("button", { name: "REINTENTAR" }));

    await waitFor(() => {
      expect(useSessionStore.getState().status).toBe("authenticated");
    });
    // El router vuelve a montarse (el degradado lo había desmontado entero).
    await waitFor(() => {
      expect(screen.queryByRole("heading", { name: DEGRADED_TITLE })).not.toBeInTheDocument();
    });
  });

  it("CERRAR SESIÓN en degradado deja la consola en el login, no colgada", async () => {
    saveDevSession({ idToken: "dev-tok", expiresAt: Date.now() + 60_000 });
    mocks.getMe.mockRejectedValue(new MeRequestError(503));

    render(<App />);
    await screen.findByRole("heading", { name: DEGRADED_TITLE });

    fireEvent.click(screen.getByRole("button", { name: "CERRAR SESIÓN" }));

    await waitFor(() => {
      expect(useSessionStore.getState().status).toBe("anonymous");
    });
    expect(window.sessionStorage.getItem("takab.dev.session")).toBeNull();
  });

  it("401 NO es degradado: la sesión se cierra de verdad (token vencido ≠ base caída)", async () => {
    saveDevSession({ idToken: "dev-tok", expiresAt: Date.now() + 60_000 });
    mocks.getMe.mockRejectedValue(new MeRequestError(401));

    render(<App />);

    await waitFor(() => {
      expect(useSessionStore.getState().status).toBe("anonymous");
    });
    expect(screen.queryByRole("heading", { name: DEGRADED_TITLE })).not.toBeInTheDocument();
    expect(window.sessionStorage.getItem("takab.dev.session")).toBeNull();
  });
});

describe("T-2.123 · el degradado NO es una puerta trasera (regla de oro 5)", () => {
  beforeEach(() => {
    useSessionStore.setState({
      status: "degraded",
      origin: "dev",
      idToken: "tok-test",
      me: null,
      error: "GET /me falló (503)",
    });
  });

  it.each(ALL_ROUTES)("deep-link a %s en degradado: declara, no pinta y no pide", (routeKey) => {
    const url = URL_BY_ROUTE[routeKey];
    const router = renderRoutesAt(url);

    // El muro de sesión responde IN-PLACE (la URL no cambia: nada de rebotar al
    // login, que diría "no estás dentro" cuando la verdad es "no se sabe").
    expect(router.state.location.pathname).toBe(url);
    expect(screen.getByRole("heading", { name: DEGRADED_TITLE })).toBeInTheDocument();
    // Ni el encabezado de la página, ni el armazón con su navegación.
    expect(
      screen.queryByRole("heading", { name: HEADING_BY_ROUTE[routeKey] }),
    ).not.toBeInTheDocument();
    // Ni una sola petición: sin alcance no hay a quién preguntarle por quién.
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("el alcance ya cargado se BORRA cuando /me deja de contestar", async () => {
    seedAuthenticated(ME_FIXTURES.soc_operator);
    expect(useSessionStore.getState().me).not.toBeNull();

    mocks.getMe.mockRejectedValue(new MeRequestError(503));
    await useSessionStore.getState().refreshMe();

    // Conservar el `me` viejo sería adivinar el alcance con un dato que ya no se
    // puede reverificar: es exactamente la brecha multi-tenant que se prohíbe.
    expect(useSessionStore.getState().status).toBe("degraded");
    expect(useSessionStore.getState().me).toBeNull();

    renderRoutesAt("/console");
    expect(screen.getByRole("heading", { name: DEGRADED_TITLE })).toBeInTheDocument();
    expect(screen.queryByText(TENANT_ID)).not.toBeInTheDocument();
    expect(screen.queryByText(/soc_operator/)).not.toBeInTheDocument();
  });

  it("la pantalla degradada no nombra tenant, rol ni estaciones", () => {
    renderRoutesAt("/fleet");

    const panel = screen.getByRole("heading", { name: DEGRADED_TITLE }).closest("div");
    const texto = panel?.textContent ?? "";
    expect(texto).not.toMatch(/ALCANCE ·/);
    expect(texto).not.toMatch(/ESTACION(ES)?\b/);
    expect(texto).not.toContain(TENANT_ID);
  });
});
