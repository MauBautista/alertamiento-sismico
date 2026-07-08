import { beforeEach, describe, expect, it, vi } from "vitest";

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
    const state = useSessionStore.getState();
    expect(state.status).toBe("anonymous");
    expect(state.idToken).toBeNull();
    expect(state.me).toBeNull();
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
