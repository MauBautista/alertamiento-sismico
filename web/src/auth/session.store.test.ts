import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  userManager: {
    getUser: vi.fn(),
    signinRedirect: vi.fn(),
    signinRedirectCallback: vi.fn(),
    signinSilent: vi.fn(),
    removeUser: vi.fn(),
    revokeTokens: vi.fn(),
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
import { resetSessionStoreForTests, selectSessionDeadline, useSessionStore } from "./session.store";

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
    window.localStorage.clear();
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
    mocks.userManager.revokeTokens.mockResolvedValue(undefined);
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
    // [T-8.03] `addSilentRenewError` ya NO se cablea. Cerraba la sesión en el
    // primer fallo de la renovación automática —un parpadeo de red a los 59
    // min—, con el token aún válido un minuto más y, desde esta ficha, revocando
    // el refresh: contraseña y código por un corte de wifi. El token vencido lo
    // recogen tres caminos que reintentan UNA vez antes de cerrar: el
    // `accessTokenExpired`, el 401 del REST y el 4401 del canal live.
    expect(mocks.userManager.events.addSilentRenewError).not.toHaveBeenCalled();
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

  // [T-6.07] Un 401 echaba al operador SIN DECIRLO: volvía a un login idéntico
  // al de un arranque en frío. La causa se guarda para que la landing la diga,
  // y se guarda en un CAMPO —el estado sigue siendo `anonymous`, que es lo que
  // es— porque el censo de más abajo exige productor real por cada miembro de
  // `SessionStatus` y una causa no es un estado.
  it("/me 401 ⇒ queda registrado POR QUÉ, para que la landing lo diga", async () => {
    saveDevSession({ idToken: "dev-tok", expiresAt: Date.now() + 60_000 });
    mocks.getMe.mockRejectedValue(new MeRequestError(401));

    await useSessionStore.getState().bootstrap();

    expect(useSessionStore.getState().endedReason).toBe("expired");
  });

  it("entrar otra vez CIERRA el episodio: la causa no sobrevive a la sesión nueva", async () => {
    saveDevSession({ idToken: "dev-tok", expiresAt: Date.now() + 60_000 });
    mocks.getMe.mockRejectedValueOnce(new MeRequestError(401));
    await useSessionStore.getState().bootstrap();
    expect(useSessionStore.getState().endedReason).toBe("expired");

    mocks.getMe.mockResolvedValueOnce(ME_FIXTURES.soc_operator);
    await useSessionStore.getState().refreshMe();

    // Sin esto, «SU SESIÓN SE CERRÓ» reaparecería meses después, en el siguiente
    // logout deliberado, culpando de una expiración que ya nadie recuerda.
    expect(useSessionStore.getState().status).toBe("authenticated");
    expect(useSessionStore.getState().endedReason).toBeNull();
  });

  it("un arranque en frío no acusa expiración de nada", async () => {
    mocks.getMe.mockResolvedValue(ME_FIXTURES.soc_operator);
    await useSessionStore.getState().bootstrap();

    expect(useSessionStore.getState().endedReason).toBeNull();
  });

  // [T-2.123] Un /me que no contesta por algo que NO es 401 (5xx de Postgres
  // caído, red) es "alcance desconocido", no "sesión cerrada": la consola
  // arranca en degradado y lo declara. Ver app/DegradedSessionScreen.tsx.
  it("error de red en /me ⇒ status degraded, y refreshMe recupera", async () => {
    saveDevSession({ idToken: "dev-tok", expiresAt: Date.now() + 60_000 });
    mocks.getMe.mockRejectedValueOnce(new Error("ECONNREFUSED"));

    await useSessionStore.getState().bootstrap();

    let state = useSessionStore.getState();
    expect(state.status).toBe("degraded");
    expect(state.error).toContain("ECONNREFUSED");
    // El token sigue siendo bueno: la sesión NO se quema por una caída de base.
    expect(state.idToken).toBe("dev-tok");
    expect(window.sessionStorage.getItem(DEV_STORAGE_KEY)).not.toBeNull();

    mocks.getMe.mockResolvedValueOnce(ME_FIXTURES.soc_operator);
    await useSessionStore.getState().refreshMe();

    state = useSessionStore.getState();
    expect(state.status).toBe("authenticated");
    expect(state.me).toEqual(ME_FIXTURES.soc_operator);
  });

  it("un /me caído tras haber cargado alcance lo BORRA (no se adivina el viejo)", async () => {
    saveDevSession({ idToken: "dev-tok", expiresAt: Date.now() + 60_000 });
    mocks.getMe.mockResolvedValueOnce(ME_FIXTURES.soc_operator);
    await useSessionStore.getState().bootstrap();
    expect(useSessionStore.getState().me).not.toBeNull();

    mocks.getMe.mockRejectedValueOnce(new MeRequestError(503));
    await useSessionStore.getState().refreshMe();

    const state = useSessionStore.getState();
    expect(state.status).toBe("degraded");
    expect(state.me).toBeNull();
  });

  it("reintentar desde el degradado NO pasa por booting (no remonta el router)", async () => {
    saveDevSession({ idToken: "dev-tok", expiresAt: Date.now() + 60_000 });
    mocks.getMe.mockRejectedValueOnce(new MeRequestError(503));
    await useSessionStore.getState().bootstrap();

    const vistos: string[] = [];
    const unsub = useSessionStore.subscribe((s) => vistos.push(s.status));
    mocks.getMe.mockRejectedValueOnce(new MeRequestError(503));
    await useSessionStore.getState().refreshMe();
    unsub();

    expect(vistos).not.toContain("booting");
    expect(useSessionStore.getState().status).toBe("degraded");
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

// ---------------------------------------------------------------------------
// [T-8.03 · D-38] LA SESIÓN SOBREVIVE AL TOKEN Y MUERE EN EL TOPE
// ---------------------------------------------------------------------------
//
// Dos cosas que se tratan AL REVÉS:
//   · el token vencido (60 min) se RENUEVA — una vez — y la sesión sigue;
//   · el tope de la sesión (24 h / 30 días desde el login, `sesion_expirada`)
//     NO se renueva: Cognito seguiría refrescando y la API rechazaría en bucle.
describe("[T-8.03] la sesión sobrevive al token y muere en el tope", () => {
  const T0 = Date.parse("2026-09-22T08:00:00Z");
  const H = 3_600_000;

  function fakeJwt(payload: Record<string, unknown>): string {
    const b64 = (o: unknown) =>
      btoa(String.fromCharCode(...new TextEncoder().encode(JSON.stringify(o))))
        .replace(/\+/g, "-")
        .replace(/\//g, "_")
        .replace(/=+$/, "");
    return `${b64({ alg: "RS256" })}.${b64(payload)}.firma`;
  }

  function meCon(expiresAt: number | null, maxAgeS: number | null) {
    return {
      ...ME_FIXTURES.soc_operator,
      session_expires_at: expiresAt === null ? null : new Date(expiresAt).toISOString(),
      session_max_age_s: maxAgeS,
    };
  }

  function grabarVentana(loginAt: number, maxAgeS: number | null): void {
    window.localStorage.setItem("takab.session.window", JSON.stringify({ loginAt, maxAgeS }));
  }

  beforeEach(() => {
    window.sessionStorage.clear();
    window.localStorage.clear();
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
    mocks.userManager.revokeTokens.mockResolvedValue(undefined);
    vi.stubEnv("VITE_API_BASE_URL", "/api");
    vi.stubEnv("VITE_DEV_TOKEN_ENABLED", "true");
    vi.stubEnv("VITE_COGNITO_DOMAIN", "https://takab-test.auth.us-east-2.amazoncognito.com");
    vi.stubEnv("VITE_COGNITO_CLIENT_ID", "client-abc");
    vi.stubEnv("VITE_COGNITO_POST_LOGOUT_URI", "http://localhost:5173/");
    resetSessionStoreForTests();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    resetSessionStoreForTests();
  });

  // --- A-033 · el arranque ya no tira una sesión con refresh vivo ------------

  it("arranque con el token VENCIDO pero refresh vivo ⇒ renueva antes de declararse anónimo", async () => {
    mocks.userManager.getUser.mockResolvedValue({
      id_token: "viejo",
      expired: true,
      refresh_token: "r-1",
    });
    mocks.userManager.signinSilent.mockResolvedValue({ id_token: "nuevo", expired: false });
    mocks.getMe.mockResolvedValue(ME_FIXTURES.soc_operator);

    await useSessionStore.getState().bootstrap();

    expect(mocks.userManager.signinSilent).toHaveBeenCalledTimes(1);
    const state = useSessionStore.getState();
    expect(state.status).toBe("authenticated");
    expect(state.idToken).toBe("nuevo");
  });

  it("…y si esa renovación falla ⇒ anónimo, diciendo que la sesión se cerró", async () => {
    mocks.userManager.getUser.mockResolvedValue({
      id_token: "viejo",
      expired: true,
      refresh_token: "r-1",
    });
    mocks.userManager.signinSilent.mockRejectedValue(new Error("invalid_grant"));

    await useSessionStore.getState().bootstrap();

    const state = useSessionStore.getState();
    expect(state.status).toBe("anonymous");
    expect(state.endedReason).toBe("expired");
    expect(mocks.getMe).not.toHaveBeenCalled();
    await vi.waitFor(() => expect(mocks.userManager.removeUser).toHaveBeenCalled());
  });

  it("vencido y SIN refresh ⇒ anónimo sin intentar nada (como antes)", async () => {
    mocks.userManager.getUser.mockResolvedValue({ id_token: "viejo", expired: true });

    await useSessionStore.getState().bootstrap();

    expect(mocks.userManager.signinSilent).not.toHaveBeenCalled();
    expect(useSessionStore.getState().status).toBe("anonymous");
  });

  it("con el cinturón ya cumplido NI SIQUIERA renueva: fin por tope", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(T0 + 25 * H);
    grabarVentana(T0, 86_400);
    mocks.userManager.getUser.mockResolvedValue({
      id_token: "viejo",
      expired: true,
      refresh_token: "r-1",
    });

    await useSessionStore.getState().bootstrap();

    expect(mocks.userManager.signinSilent).not.toHaveBeenCalled();
    expect(mocks.getMe).not.toHaveBeenCalled();
    const state = useSessionStore.getState();
    expect(state.status).toBe("anonymous");
    expect(state.endedReason).toBe("max_age");
    // La landing necesita saber CUÁNTO duraba para decirlo.
    expect(state.sessionMaxAgeS).toBe(86_400);
  });

  // --- A-034 · el tope se distingue del 401 genérico -------------------------

  it("/me dice `sesion_expirada` ⇒ fin por TOPE, sin renovar, y el refresh se revoca", async () => {
    grabarVentana(T0, 86_400);
    mocks.userManager.getUser.mockResolvedValue({ id_token: "cog", expired: false });
    mocks.getMe.mockRejectedValue(new MeRequestError(401, true));

    await useSessionStore.getState().bootstrap();

    const state = useSessionStore.getState();
    expect(state.status).toBe("anonymous");
    expect(state.endedReason).toBe("max_age");
    expect(state.sessionMaxAgeS).toBe(86_400);
    expect(mocks.userManager.signinSilent).not.toHaveBeenCalled();
    await vi.waitFor(() => expect(mocks.userManager.removeUser).toHaveBeenCalled());
    expect(mocks.userManager.revokeTokens).toHaveBeenCalledWith(["refresh_token"]);
    // El refresh se revoca ANTES de borrar el usuario: después no quedaría qué revocar.
    expect(mocks.userManager.revokeTokens.mock.invocationCallOrder[0]).toBeLessThan(
      mocks.userManager.removeUser.mock.invocationCallOrder[0],
    );
    expect(window.localStorage.getItem("takab.session.window")).toBeNull();
  });

  it("un 401 GENÉRICO de /me con Cognito ⇒ UNA renovación y /me otra vez", async () => {
    mocks.userManager.getUser.mockResolvedValue({ id_token: "t1", expired: false });
    mocks.userManager.signinSilent.mockResolvedValue({ id_token: "t2" });
    mocks.getMe
      .mockRejectedValueOnce(new MeRequestError(401))
      .mockResolvedValueOnce(ME_FIXTURES.soc_operator);

    await useSessionStore.getState().bootstrap();

    expect(mocks.userManager.signinSilent).toHaveBeenCalledTimes(1);
    expect(mocks.getMe).toHaveBeenCalledTimes(2);
    const state = useSessionStore.getState();
    expect(state.status).toBe("authenticated");
    expect(state.idToken).toBe("t2");
  });

  it("si el token RENOVADO también da 401, se cierra (una sola vez, no un bucle)", async () => {
    mocks.userManager.getUser.mockResolvedValue({ id_token: "t1", expired: false });
    mocks.userManager.signinSilent.mockResolvedValue({ id_token: "t2" });
    mocks.getMe.mockRejectedValue(new MeRequestError(401));

    await useSessionStore.getState().bootstrap();

    expect(mocks.userManager.signinSilent).toHaveBeenCalledTimes(1);
    const state = useSessionStore.getState();
    expect(state.status).toBe("anonymous");
    expect(state.endedReason).toBe("expired");
  });

  it("/me guarda el plazo y la edad máxima; la edad sobrevive a una recarga", async () => {
    grabarVentana(T0, null);
    mocks.userManager.getUser.mockResolvedValue({ id_token: "cog", expired: false });
    const expira = Date.now() + 10 * H;
    mocks.getMe.mockResolvedValue(meCon(expira, 86_400));

    await useSessionStore.getState().bootstrap();

    const state = useSessionStore.getState();
    expect(state.sessionExpiresAt).toBe(expira);
    expect(state.sessionMaxAgeS).toBe(86_400);
    expect(state.loginAt).toBe(T0);
    expect(JSON.parse(window.localStorage.getItem("takab.session.window") ?? "{}")).toEqual({
      loginAt: T0,
      maxAgeS: 86_400,
    });
  });

  it("el callback graba la hora del login —el `auth_time` del token— en localStorage", async () => {
    mocks.userManager.signinRedirectCallback.mockResolvedValue({
      id_token: fakeJwt({ auth_time: T0 / 1000 }),
      state: {},
    });
    mocks.getMe.mockResolvedValue(ME_FIXTURES.soc_operator);

    await useSessionStore.getState().completeCognitoCallback();

    expect(useSessionStore.getState().loginAt).toBe(T0);
    expect(JSON.parse(window.localStorage.getItem("takab.session.window") ?? "{}")).toEqual({
      loginAt: T0,
      maxAgeS: null,
    });
  });

  it("sin `auth_time` en el token, la hora del login es la de la vuelta", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(T0 + 5_000);
    mocks.userManager.signinRedirectCallback.mockResolvedValue({ id_token: "opaco", state: {} });
    mocks.getMe.mockResolvedValue(ME_FIXTURES.soc_operator);

    await useSessionStore.getState().completeCognitoCallback();

    expect(useSessionStore.getState().loginAt).toBe(T0 + 5_000);
  });

  // --- El cinturón en el cliente --------------------------------------------

  it("el cinturón cierra al llegar el plazo aunque el servidor no haya dicho nada", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(T0);
    saveDevSession({ idToken: "dev-tok", expiresAt: T0 + H });
    mocks.getMe.mockResolvedValue(meCon(T0 + 5_000, 86_400));
    await useSessionStore.getState().bootstrap();
    expect(useSessionStore.getState().status).toBe("authenticated");

    await vi.advanceTimersByTimeAsync(4_999);
    expect(useSessionStore.getState().status).toBe("authenticated");
    await vi.advanceTimersByTimeAsync(1);

    const state = useSessionStore.getState();
    expect(state.status).toBe("anonymous");
    expect(state.endedReason).toBe("max_age");
    expect(state.sessionMaxAgeS).toBe(86_400);
  });

  it("el plazo efectivo es el MENOR: si el servidor lo corriera, manda la marca del login", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(T0 + 23 * H);
    saveDevSession({ idToken: "dev-tok", expiresAt: T0 + 24 * H, authTimeMs: T0 });
    // El servidor dice 24 h desde un auth_time que avanzó 3 h (A-006).
    mocks.getMe.mockResolvedValue(meCon(T0 + 27 * H, 86_400));
    await useSessionStore.getState().bootstrap();
    expect(selectSessionDeadline(useSessionStore.getState())).toBe(T0 + 24 * H);

    await vi.advanceTimersByTimeAsync(H);

    expect(useSessionStore.getState().endedReason).toBe("max_age");
  });

  it("un plazo a 30 días NO dispara al instante (setTimeout desborda a 24.8 d)", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(T0);
    saveDevSession({ idToken: "dev-tok", expiresAt: T0 + H });
    mocks.getMe.mockResolvedValue(meCon(T0 + 30 * 24 * H, 2_592_000));
    await useSessionStore.getState().bootstrap();

    await vi.advanceTimersByTimeAsync(1_000);
    expect(useSessionStore.getState().status).toBe("authenticated");

    await vi.advanceTimersByTimeAsync(30 * 24 * H);
    expect(useSessionStore.getState().endedReason).toBe("max_age");
  });

  it("sin dato del plazo no hay cinturón que inventar", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(T0);
    saveDevSession({ idToken: "dev-tok", expiresAt: T0 + H });
    mocks.getMe.mockResolvedValue(ME_FIXTURES.soc_operator);
    await useSessionStore.getState().bootstrap();

    expect(selectSessionDeadline(useSessionStore.getState())).toBeNull();
    await vi.advanceTimersByTimeAsync(100 * 24 * H);
    expect(useSessionStore.getState().status).toBe("authenticated");
  });

  // --- renewToken: lo que el canal live usa ante un 4401 ---------------------

  it("renewToken (Cognito): signinSilent y el id_token nuevo al store; dos a la vez ⇒ UNA", async () => {
    mocks.userManager.getUser.mockResolvedValue({ id_token: "t1", expired: false });
    mocks.getMe.mockResolvedValue(ME_FIXTURES.soc_operator);
    await useSessionStore.getState().bootstrap();
    let soltar: (u: { id_token: string }) => void = () => undefined;
    mocks.userManager.signinSilent.mockReturnValue(
      new Promise((resolve) => {
        soltar = resolve;
      }),
    );

    const a = useSessionStore.getState().renewToken();
    const b = useSessionStore.getState().renewToken();
    soltar({ id_token: "t2" });

    await expect(a).resolves.toBe("t2");
    await expect(b).resolves.toBe("t2");
    expect(mocks.userManager.signinSilent).toHaveBeenCalledTimes(1);
    expect(useSessionStore.getState().idToken).toBe("t2");
  });

  it("renewToken (dev): re-emite con los MISMOS parámetros y lo guarda", async () => {
    saveDevSession({
      idToken: "dev-1",
      expiresAt: Date.now() + 60_000,
      request: { role: "soc_operator", tenant_id: TENANT_ID, sub: "u-7", expires_in: 120 },
      authTimeMs: Date.now() - 10_000,
    });
    mocks.getMe.mockResolvedValue(ME_FIXTURES.soc_operator);
    await useSessionStore.getState().bootstrap();
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        jsonResponse(200, { id_token: "dev-2", token_use: "id", expires_in: 120 }),
      );
    vi.stubGlobal("fetch", fetchMock);

    await expect(useSessionStore.getState().renewToken()).resolves.toBe("dev-2");

    const body = JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string);
    expect(body).toMatchObject({
      role: "soc_operator",
      tenant_id: TENANT_ID,
      sub: "u-7",
      expires_in: 120,
    });
    expect(body.auth_age_s).toBeGreaterThanOrEqual(10);
    expect(useSessionStore.getState().idToken).toBe("dev-2");
    expect(JSON.parse(window.sessionStorage.getItem(DEV_STORAGE_KEY) ?? "{}").idToken).toBe(
      "dev-2",
    );
  });

  it("renewToken con el plazo ya cumplido no renueva: termina por tope", async () => {
    mocks.userManager.getUser.mockResolvedValue({ id_token: "t1", expired: false });
    mocks.getMe.mockResolvedValue(meCon(Date.now() + H, 86_400));
    await useSessionStore.getState().bootstrap();
    useSessionStore.setState({ sessionExpiresAt: Date.now() - 1 });

    await expect(useSessionStore.getState().renewToken()).resolves.toBeNull();

    expect(mocks.userManager.signinSilent).not.toHaveBeenCalled();
    expect(useSessionStore.getState().endedReason).toBe("max_age");
  });

  it("dev: arranque con el token vencido y parámetros ⇒ se re-emite en vez de pedir login", async () => {
    saveDevSession({
      idToken: "dev-viejo",
      expiresAt: Date.now() - 1,
      request: { role: "soc_operator", tenant_id: TENANT_ID, sub: "u-7" },
      authTimeMs: Date.now() - 2 * H,
    });
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          jsonResponse(200, { id_token: "dev-nuevo", token_use: "id", expires_in: 3600 }),
        ),
    );
    mocks.getMe.mockResolvedValue(ME_FIXTURES.soc_operator);

    await useSessionStore.getState().bootstrap();

    const state = useSessionStore.getState();
    expect(state.status).toBe("authenticated");
    expect(state.idToken).toBe("dev-nuevo");
  });

  // --- recoverFromUnauthorized: el 401 del REST ------------------------------

  it("un 401 con un token que YA no es el vigente no renueva otra vez", async () => {
    mocks.userManager.getUser.mockResolvedValue({ id_token: "t2", expired: false });
    mocks.getMe.mockResolvedValue(ME_FIXTURES.soc_operator);
    await useSessionStore.getState().bootstrap();

    await expect(useSessionStore.getState().recoverFromUnauthorized("t1")).resolves.toBe(true);

    expect(mocks.userManager.signinSilent).not.toHaveBeenCalled();
    expect(useSessionStore.getState().status).toBe("authenticated");
  });

  it("sin sesión no hay nada que recuperar (y no se acusa nada)", async () => {
    await useSessionStore.getState().bootstrap();

    await expect(useSessionStore.getState().recoverFromUnauthorized("t1")).resolves.toBe(false);
    expect(useSessionStore.getState().endedReason).toBeNull();
  });

  // --- Fin de sesión ----------------------------------------------------------

  it("un 'expired' tardío (el WS que cae después) no pisa el 'max_age'", () => {
    useSessionStore.setState({ status: "authenticated", origin: "dev", idToken: "t" });
    useSessionStore.getState().handleUnauthorized("max_age");
    useSessionStore.getState().handleUnauthorized("expired");

    expect(useSessionStore.getState().endedReason).toBe("max_age");
  });

  it("logout cognito revoca el refresh ANTES de borrar el usuario y de ir al /logout", async () => {
    grabarVentana(T0, 86_400);
    mocks.userManager.getUser.mockResolvedValue({ id_token: "cog", expired: false });
    mocks.getMe.mockResolvedValue(ME_FIXTURES.tenant_admin);
    await useSessionStore.getState().bootstrap();

    await useSessionStore.getState().logout();

    expect(mocks.userManager.revokeTokens).toHaveBeenCalledWith(["refresh_token"]);
    const revocado = mocks.userManager.revokeTokens.mock.invocationCallOrder[0];
    expect(revocado).toBeLessThan(mocks.userManager.removeUser.mock.invocationCallOrder[0]);
    expect(revocado).toBeLessThan(mocks.hardRedirect.mock.invocationCallOrder[0]);
    expect(window.localStorage.getItem("takab.session.window")).toBeNull();
    // Un SALIR deliberado no es un tope ni una expiración.
    expect(useSessionStore.getState().endedReason).toBeNull();
  });

  it("si Cognito no contesta a la revocación, SALIR no se queda colgado", async () => {
    vi.useFakeTimers();
    mocks.userManager.getUser.mockResolvedValue({ id_token: "cog", expired: false });
    mocks.getMe.mockResolvedValue(ME_FIXTURES.tenant_admin);
    await useSessionStore.getState().bootstrap();
    mocks.userManager.revokeTokens.mockReturnValue(new Promise(() => undefined));

    const salir = useSessionStore.getState().logout();
    await vi.advanceTimersByTimeAsync(5_000);
    await salir;

    expect(mocks.hardRedirect).toHaveBeenCalledTimes(1);
  });

  it("un userLoaded que llega DESPUÉS de cerrar (la revocación lo emite) no resucita la sesión", async () => {
    mocks.userManager.getUser.mockResolvedValue({ id_token: "cog", expired: false });
    mocks.getMe.mockResolvedValue(ME_FIXTURES.tenant_admin);
    await useSessionStore.getState().bootstrap();
    const onUserLoaded = mocks.userManager.events.addUserLoaded.mock.calls[0][0] as (u: {
      id_token: string;
    }) => void;

    await useSessionStore.getState().logout();
    onUserLoaded({ id_token: "zombi" });

    expect(useSessionStore.getState().idToken).toBeNull();
  });

  it("accessTokenExpired intenta renovar UNA vez; si falla, cierra como expirada", async () => {
    mocks.userManager.getUser.mockResolvedValue({ id_token: "cog", expired: false });
    mocks.getMe.mockResolvedValue(ME_FIXTURES.tenant_admin);
    await useSessionStore.getState().bootstrap();
    const onExpired = mocks.userManager.events.addAccessTokenExpired.mock.calls[0][0] as () => void;
    mocks.userManager.signinSilent.mockRejectedValue(new Error("red"));

    onExpired();

    await vi.waitFor(() => expect(useSessionStore.getState().status).toBe("anonymous"));
    expect(useSessionStore.getState().endedReason).toBe("expired");
    expect(mocks.userManager.signinSilent).toHaveBeenCalledTimes(1);
  });
});

// ---------------------------------------------------------------------------
// [T-2.134] NINGÚN ESTADO DE SESIÓN SIN PRODUCTOR
// ---------------------------------------------------------------------------
//
// Es la misma doctrina que `T-2.133` aplicó al registro de `incident_actions`,
// aquí sobre la máquina de estados de la sesión: un miembro del union que nadie
// escribe nunca es código muerto que se lee como una rama viva. `status: "error"`
// llevaba así desde que `T-2.123` convirtió el único fallo de `/me` que existía
// en `degraded` — y arrastraba consigo `ErrorScreen` y una rama de `LoginPage`,
// dos pantallas que ningún camino podía alcanzar.
//
// El censo se DERIVA: los miembros salen del propio `type SessionStatus` y los
// productores del código de producción (los `*.test.*` no cuentan; un `setState`
// de test no es un camino que un operador pueda recorrer). El estado siguiente
// que se añada sin escribirse pondrá esto en rojo.
describe("[T-2.134] la máquina de estados de la sesión no tiene ramas muertas", () => {
  const AUTH = resolve(process.cwd(), "src", "auth");
  const APP = resolve(process.cwd(), "src", "app");
  const PAGES = resolve(process.cwd(), "src", "pages");

  function fuentesDeProduccion(dir: string, acc: string[] = []): string[] {
    for (const entrada of readdirSync(dir)) {
      const ruta = join(dir, entrada);
      if (statSync(ruta).isDirectory()) {
        fuentesDeProduccion(ruta, acc);
      } else if (/\.tsx?$/.test(entrada) && !/\.test\.tsx?$/.test(entrada)) {
        acc.push(ruta);
      }
    }
    return acc;
  }

  /**
   * Miembros del union `SessionStatus`, leídos de su declaración.
   *
   * Los comentarios se quitan ANTES de cortar por `;`, y no es celo: la primera
   * versión de este censo cortaba en crudo y un `;` dentro del docblock de un
   * miembro dejó fuera del barrido justo al miembro que la ficha venía a cazar.
   * El test pasaba en verde sin haber mirado `error`.
   */
  function estadosDeclarados(): string[] {
    const fuente = readFileSync(join(AUTH, "session.store.ts"), "utf8")
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/\/\/.*$/gm, "");
    const bloque = fuente.split("export type SessionStatus =")[1]?.split(";")[0];
    expect(bloque, "`SessionStatus` cambió de forma: el censo dejó de saber leerlo").toBeDefined();
    return [...(bloque ?? "").matchAll(/"(\w+)"/g)].map((m) => m[1]);
  }

  const ESTADOS = estadosDeclarados();
  const FUENTES = [AUTH, APP, PAGES].flatMap((d) => fuentesDeProduccion(d));

  it("el censo no está vacío (si esto falla, el resto de este bloque miente)", () => {
    expect(ESTADOS.length).toBeGreaterThanOrEqual(5);
    expect(ESTADOS).toContain("degraded");
  });

  it.each(ESTADOS)("`%s` lo ESCRIBE alguien en producción", (estado) => {
    // `status === "x"` es un LECTOR, no un productor: la rama muerta se
    // reconocía justamente por tener lectores y ningún escritor.
    const escritura = new RegExp(`status:\\s*"${estado}"`);
    const productores = FUENTES.filter((f) => escritura.test(readFileSync(f, "utf8")));
    expect(productores).not.toHaveLength(0);
  });
});
