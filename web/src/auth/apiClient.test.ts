import { beforeEach, describe, expect, it, vi } from "vitest";

// [T-8.03] UserManager fake: el 401 genérico con origen Cognito intenta UN
// `signinSilent` antes de cerrar, y aquí se cuenta cuántos.
const um = vi.hoisted(() => ({
  signinSilent: vi.fn(),
  removeUser: vi.fn(),
  revokeTokens: vi.fn(),
  getUser: vi.fn(),
  events: { addUserLoaded: vi.fn(), addAccessTokenExpired: vi.fn() },
}));
vi.mock("./userManager", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./userManager")>();
  return { ...actual, cognitoConfigured: () => true, getUserManager: () => um };
});

import { ME_FIXTURES } from "../test-utils/meFixtures";
import { configureApiClient } from "./apiClient";
import { getMe, MeRequestError } from "./me";
import { resetSessionStoreForTests, useSessionStore } from "./session.store";

// undici (fetch de vitest/jsdom) exige URL absoluta al construir Request, y el
// baseUrl se lee en configureApiClient(): ambos stubs ANTES de configurar.
vi.stubEnv("VITE_API_BASE_URL", "http://api.test");
const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);
configureApiClient();

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function capturedRequest(): Request {
  const [input, init] = fetchMock.mock.calls[0] as [RequestInfo | URL, RequestInit?];
  return input instanceof Request ? input : new Request(input, init);
}

describe("configureApiClient", () => {
  beforeEach(() => {
    fetchMock.mockReset();
    um.signinSilent.mockReset();
    um.removeUser.mockReset().mockResolvedValue(undefined);
    um.revokeTokens.mockReset().mockResolvedValue(undefined);
    window.sessionStorage.clear();
    resetSessionStoreForTests();
  });

  it("inyecta Authorization: Bearer <idToken> desde el store", async () => {
    useSessionStore.setState({
      status: "authenticated",
      origin: "dev",
      idToken: "tok-1",
      me: ME_FIXTURES.soc_operator,
    });
    fetchMock.mockResolvedValueOnce(jsonResponse(200, ME_FIXTURES.soc_operator));

    await expect(getMe()).resolves.toEqual(ME_FIXTURES.soc_operator);

    const request = capturedRequest();
    expect(new URL(request.url).pathname).toBe("/me");
    expect(request.headers.get("authorization")).toBe("Bearer tok-1");
  });

  it("no manda Authorization cuando no hay sesión", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, ME_FIXTURES.soc_operator));

    await getMe();

    expect(capturedRequest().headers.get("authorization")).toBeNull();
  });

  it("un 401 expulsa la sesión (handleUnauthorized) además de rechazar", async () => {
    useSessionStore.setState({
      status: "authenticated",
      origin: "dev",
      idToken: "tok-viejo",
      me: ME_FIXTURES.soc_operator,
    });
    fetchMock.mockResolvedValueOnce(jsonResponse(401, { detail: "token expirado" }));

    const err = await getMe().catch((e: unknown) => e);

    expect(err).toBeInstanceOf(MeRequestError);
    expect((err as MeRequestError).status).toBe(401);
    // [T-8.03] Antes de cerrar hay UN intento de renovar (asíncrono); una sesión
    // dev sin parámetros guardados no tiene con qué, así que termina cerrándose.
    await vi.waitFor(() => expect(useSessionStore.getState().status).toBe("anonymous"));
    const state = useSessionStore.getState();
    expect(state.idToken).toBeNull();
    expect(state.me).toBeNull();
    expect(state.endedReason).toBe("expired");
  });

  // --- [T-8.03 · D-38] el tope NO se renueva; el token vencido sí, una vez ---

  const TOPE = 'Bearer error="invalid_token", error_description="sesion_expirada"';

  function tope(): Response {
    return new Response(JSON.stringify({ detail: "sesion_expirada" }), {
      status: 401,
      headers: { "Content-Type": "application/json", "WWW-Authenticate": TOPE },
    });
  }

  function seedCognito(token = "t1"): void {
    useSessionStore.setState({
      status: "authenticated",
      origin: "cognito",
      idToken: token,
      me: ME_FIXTURES.soc_operator,
    });
  }

  it("401 del TOPE (cabecera) ⇒ fin 'max_age' SIN intentar renovar", async () => {
    seedCognito();
    fetchMock.mockResolvedValueOnce(tope());

    await getMe().catch(() => undefined);

    const state = useSessionStore.getState();
    expect(state.status).toBe("anonymous");
    expect(state.endedReason).toBe("max_age");
    // Cognito seguiría refrescando y la API rechazaría en bucle.
    expect(um.signinSilent).not.toHaveBeenCalled();
  });

  it("401 del TOPE solo en el cuerpo (sin cabecera) ⇒ también 'max_age'", async () => {
    seedCognito();
    fetchMock.mockResolvedValueOnce(jsonResponse(401, { detail: "sesion_expirada" }));

    await getMe().catch(() => undefined);

    await vi.waitFor(() => expect(useSessionStore.getState().endedReason).toBe("max_age"));
    expect(um.signinSilent).not.toHaveBeenCalled();
  });

  it("401 genérico con Cognito ⇒ UN signinSilent y la sesión sigue con el token nuevo", async () => {
    seedCognito("t1");
    um.signinSilent.mockResolvedValue({ id_token: "t2" });
    fetchMock.mockResolvedValue(jsonResponse(401, { detail: "token expirado" }));

    // Tres peticiones a la vez con el mismo token vencido: UNA renovación.
    await Promise.all([getMe(), getMe(), getMe()].map((p) => p.catch(() => undefined)));

    await vi.waitFor(() => expect(useSessionStore.getState().idToken).toBe("t2"));
    expect(um.signinSilent).toHaveBeenCalledTimes(1);
    expect(useSessionStore.getState().status).toBe("authenticated");
  });

  it("401 genérico con Cognito y la renovación falla ⇒ fin 'expired'", async () => {
    seedCognito("t1");
    um.signinSilent.mockRejectedValue(new Error("invalid_grant"));
    fetchMock.mockResolvedValueOnce(jsonResponse(401, { detail: "token expirado" }));

    await getMe().catch(() => undefined);

    await vi.waitFor(() => expect(useSessionStore.getState().status).toBe("anonymous"));
    expect(useSessionStore.getState().endedReason).toBe("expired");
    expect(um.signinSilent).toHaveBeenCalledTimes(1);
  });

  it("un 403 NO cierra la sesión (autorización fina del backend)", async () => {
    useSessionStore.setState({
      status: "authenticated",
      origin: "dev",
      idToken: "tok-1",
      me: ME_FIXTURES.soc_operator,
    });
    fetchMock.mockResolvedValueOnce(jsonResponse(403, { detail: "fuera de site_scope" }));

    await expect(getMe()).rejects.toBeInstanceOf(MeRequestError);

    const state = useSessionStore.getState();
    expect(state.status).toBe("authenticated");
    expect(state.idToken).toBe("tok-1");
  });
});
