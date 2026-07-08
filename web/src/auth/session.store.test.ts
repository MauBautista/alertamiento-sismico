import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  userManager: {
    getUser: vi.fn(),
    signinRedirect: vi.fn(),
    signinRedirectCallback: vi.fn(),
    signinSilent: vi.fn(),
    removeUser: vi.fn(),
    events: {
      addUserLoaded: vi.fn(),
      addAccessTokenExpired: vi.fn(),
      addSilentRenewError: vi.fn(),
    },
  },
  getMe: vi.fn(),
  hardRedirect: vi.fn(),
}));

// getMe mockeado, MeRequestError real (el store discrimina por instancia+status).
vi.mock("./me", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./me")>();
  return { ...actual, getMe: mocks.getMe };
});

// UserManager fake (jsdom no puede ejercitar PKCE); buildLogoutUrl queda REAL
// para asertar la URL exacta del /logout del Hosted UI.
vi.mock("./userManager", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./userManager")>();
  return {
    ...actual,
    cognitoConfigured: () => true,
    getUserManager: () => mocks.userManager,
  };
});

vi.mock("../app/navigation", () => ({ hardRedirect: mocks.hardRedirect }));

import { ME_FIXTURES, TENANT_ID } from "../test-utils/meFixtures";
import { saveDevSession } from "./devToken";
import { MeRequestError } from "./me";
import { resetSessionStoreForTests, useSessionStore } from "./session.store";

const DEV_STORAGE_KEY = "takab.dev.session";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("session.store", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    mocks.getMe.mockReset();
    mocks.hardRedirect.mockReset();
    for (const fn of Object.values(mocks.userManager)) {
      if (typeof fn === "function") {
        fn.mockReset();
      }
    }
    for (const fn of Object.values(mocks.userManager.events)) {
      fn.mockReset();
    }
    mocks.userManager.getUser.mockResolvedValue(null);
    mocks.userManager.removeUser.mockResolvedValue(undefined);
    mocks.userManager.signinRedirect.mockResolvedValue(undefined);

    vi.stubEnv("VITE_API_BASE_URL", "/api");
    vi.stubEnv("VITE_DEV_TOKEN_ENABLED", "true");
    vi.stubEnv(
      "VITE_COGNITO_AUTHORITY",
      "https://cognito-idp.us-east-2.amazonaws.com/us-east-2_TEST",
    );
    vi.stubEnv("VITE_COGNITO_CLIENT_ID", "client-abc");
    vi.stubEnv("VITE_COGNITO_DOMAIN", "https://takab-test.auth.us-east-2.amazoncognito.com");
    vi.stubEnv("VITE_COGNITO_POST_LOGOUT_URI", "http://localhost:5173/");

    resetSessionStoreForTests();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("bootstrap sin sesión previa ⇒ anonymous, sin llamar /me", async () => {
    await useSessionStore.getState().bootstrap();

    expect(useSessionStore.getState().status).toBe("anonymous");
    expect(mocks.getMe).not.toHaveBeenCalled();
  });

  it("bootstrap retoma una sesión dev guardada ⇒ authenticated + me", async () => {
    saveDevSession({ idToken: "dev-tok", expiresAt: Date.now() + 60_000 });
    mocks.getMe.mockResolvedValue(ME_FIXTURES.soc_operator);

    await useSessionStore.getState().bootstrap();

    const state = useSessionStore.getState();
    expect(state.status).toBe("authenticated");
    expect(state.origin).toBe("dev");
    expect(state.idToken).toBe("dev-tok");
    expect(state.me).toEqual(ME_FIXTURES.soc_operator);
  });

  it("bootstrap con usuario Cognito vigente ⇒ authenticated y eventos wired", async () => {
    mocks.userManager.getUser.mockResolvedValue({ id_token: "cog-tok", expired: false });
    mocks.getMe.mockResolvedValue(ME_FIXTURES.tenant_admin);

    await useSessionStore.getState().bootstrap();

    const state = useSessionStore.getState();
    expect(state.status).toBe("authenticated");
    expect(state.origin).toBe("cognito");
    expect(state.idToken).toBe("cog-tok");
    expect(mocks.userManager.events.addUserLoaded).toHaveBeenCalledTimes(1);
    expect(mocks.userManager.events.addAccessTokenExpired).toHaveBeenCalledTimes(1);
    expect(mocks.userManager.events.addSilentRenewError).toHaveBeenCalledTimes(1);
  });

  it("bootstrap es idempotente (latch StrictMode): un solo getUser", async () => {
    const { bootstrap } = useSessionStore.getState();
    await Promise.all([bootstrap(), bootstrap()]);

    expect(mocks.userManager.getUser).toHaveBeenCalledTimes(1);
  });

  it("/me 401 durante bootstrap ⇒ anonymous y limpia la sesión dev", async () => {
    saveDevSession({ idToken: "dev-tok", expiresAt: Date.now() + 60_000 });
    mocks.getMe.mockRejectedValue(new MeRequestError(401));

    await useSessionStore.getState().bootstrap();

    expect(useSessionStore.getState().status).toBe("anonymous");
    expect(window.sessionStorage.getItem(DEV_STORAGE_KEY)).toBeNull();
  });

  it("error de red en /me ⇒ status error, y refreshMe recupera", async () => {
    saveDevSession({ idToken: "dev-tok", expiresAt: Date.now() + 60_000 });
    mocks.getMe.mockRejectedValueOnce(new Error("ECONNREFUSED"));

    await useSessionStore.getState().bootstrap();

    let state = useSessionStore.getState();
    expect(state.status).toBe("error");
    expect(state.error).toContain("ECONNREFUSED");

    mocks.getMe.mockResolvedValueOnce(ME_FIXTURES.soc_operator);
    await useSessionStore.getState().refreshMe();

    state = useSessionStore.getState();
    expect(state.status).toBe("authenticated");
    expect(state.me).toEqual(ME_FIXTURES.soc_operator);
  });

  it("loginDev persiste la sesión y un bootstrap posterior la retoma", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        jsonResponse(200, { id_token: "dev-2", token_use: "id", expires_in: 3600 }),
      );
    vi.stubGlobal("fetch", fetchMock);
    mocks.getMe.mockResolvedValue(ME_FIXTURES.gov_operator);

    await useSessionStore.getState().loginDev({ role: "gov_operator", tenant_id: TENANT_ID });

    let state = useSessionStore.getState();
    expect(state.status).toBe("authenticated");
    expect(state.origin).toBe("dev");
    expect(state.idToken).toBe("dev-2");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/dev/token");
    expect(window.sessionStorage.getItem(DEV_STORAGE_KEY)).not.toBeNull();

    // "Recarga" de la app: estado en cero pero sessionStorage intacto.
    resetSessionStoreForTests();
    await useSessionStore.getState().bootstrap();

    state = useSessionStore.getState();
    expect(state.status).toBe("authenticated");
    expect(state.idToken).toBe("dev-2");
  });

  it("loginDev con /dev/token caído ⇒ propaga y queda anonymous", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(503, {})));

    await expect(
      useSessionStore.getState().loginDev({ role: "soc_operator", tenant_id: TENANT_ID }),
    ).rejects.toThrow("503");
    expect(useSessionStore.getState().status).toBe("anonymous");
  });

  it("logout dev ⇒ anonymous local, sin redirect ni removeUser", async () => {
    saveDevSession({ idToken: "dev-tok", expiresAt: Date.now() + 60_000 });
    mocks.getMe.mockResolvedValue(ME_FIXTURES.soc_operator);
    await useSessionStore.getState().bootstrap();

    await useSessionStore.getState().logout();

    const state = useSessionStore.getState();
    expect(state.status).toBe("anonymous");
    expect(state.idToken).toBeNull();
    expect(state.me).toBeNull();
    expect(window.sessionStorage.getItem(DEV_STORAGE_KEY)).toBeNull();
    expect(mocks.hardRedirect).not.toHaveBeenCalled();
    expect(mocks.userManager.removeUser).not.toHaveBeenCalled();
  });

  it("logout cognito ⇒ removeUser + redirect exacto al /logout del Hosted UI", async () => {
    mocks.userManager.getUser.mockResolvedValue({ id_token: "cog-tok", expired: false });
    mocks.getMe.mockResolvedValue(ME_FIXTURES.tenant_admin);
    await useSessionStore.getState().bootstrap();

    await useSessionStore.getState().logout();

    expect(mocks.userManager.removeUser).toHaveBeenCalledTimes(1);
    expect(mocks.hardRedirect).toHaveBeenCalledWith(
      "https://takab-test.auth.us-east-2.amazoncognito.com/logout" +
        "?client_id=client-abc&logout_uri=http%3A%2F%2Flocalhost%3A5173%2F",
    );
    expect(useSessionStore.getState().status).toBe("anonymous");
  });

  it("loginCognito dispara signinRedirect con returnTo en el state", async () => {
    await useSessionStore.getState().loginCognito("/triage");

    expect(mocks.userManager.signinRedirect).toHaveBeenCalledWith({
      state: { returnTo: "/triage" },
    });
    expect(useSessionStore.getState().status).toBe("authenticating");
  });

  it("completeCognitoCallback ⇒ authenticated + returnTo del state (one-shot)", async () => {
    mocks.userManager.signinRedirectCallback.mockResolvedValue({
      id_token: "cb-tok",
      state: { returnTo: "/fleet" },
    });
    mocks.getMe.mockResolvedValue(ME_FIXTURES.soc_operator);

    const result = await useSessionStore.getState().completeCognitoCallback();

    expect(result).toEqual({ returnTo: "/fleet" });
    const state = useSessionStore.getState();
    expect(state.status).toBe("authenticated");
    expect(state.origin).toBe("cognito");
    expect(state.idToken).toBe("cb-tok");

    // Latch: StrictMode re-monta el callback pero el intercambio OIDC es one-shot.
    await useSessionStore.getState().completeCognitoCallback();
    expect(mocks.userManager.signinRedirectCallback).toHaveBeenCalledTimes(1);
  });

  it("callback fallido ⇒ propaga el error y deja anonymous", async () => {
    mocks.userManager.signinRedirectCallback.mockRejectedValue(new Error("invalid state"));

    await expect(useSessionStore.getState().completeCognitoCallback()).rejects.toThrow(
      "invalid state",
    );
    expect(useSessionStore.getState().status).toBe("anonymous");
  });
});
