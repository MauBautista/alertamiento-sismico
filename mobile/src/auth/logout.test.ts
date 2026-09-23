// [T-8.04 · A-020] CERRAR SESIÓN DE VERDAD.
//
// Medido antes: `signOut` sólo borraba el almacén y el estado. Quedaban vivos
//   · el token push, ligado al usuario y al inmueble (un teléfono que ya no es
//     de nadie seguía recibiendo las alertas del edificio);
//   · el refresh token en Cognito — grave con los 30/90 días de D-38;
//   · la cookie de la Hosted UI: el siguiente «INICIAR SESIÓN» entraba con la
//     identidad ANTERIOR (medido en el Pixel, T-7.56).
//
// Orden y best-effort: ningún paso que falle impide el siguiente, y el almacén
// se borra SIEMPRE, el último.
import * as AuthSession from "expo-auth-session";
import * as SecureStore from "expo-secure-store";
import * as WebBrowser from "expo-web-browser";

import { unregisterOwnPushToken } from "@/services/push";

import { logout } from "./logout";
import { saveSession, SESSION_KEY } from "./secureTokens";
import { useSessionStore } from "./session.store";
import { fakeJwt, nowS } from "./testJwt";

jest.mock("expo-secure-store", () => {
  const mem = new Map<string, string>();
  return {
    __mem: mem,
    getItemAsync: jest.fn(async (k: string) => mem.get(k) ?? null),
    setItemAsync: jest.fn(async (k: string, v: string) => void mem.set(k, v)),
    deleteItemAsync: jest.fn(async (k: string) => void mem.delete(k)),
  };
});

jest.mock("expo-auth-session", () => ({
  revokeAsync: jest.fn(),
  TokenTypeHint: { RefreshToken: "refresh_token" },
}));

jest.mock("expo-web-browser", () => ({
  openAuthSessionAsync: jest.fn(),
  dismissAuthSession: jest.fn(),
}));

jest.mock("@/services/push", () => ({ unregisterOwnPushToken: jest.fn() }));

jest.mock("./config", () => {
  const actual = jest.requireActual("./config");
  return {
    ...actual,
    POOLS: actual.buildPools({
      EXPO_PUBLIC_COGNITO_OCCUPANTS_ISSUER: "https://idp/occ",
      EXPO_PUBLIC_COGNITO_OCCUPANTS_CLIENT_ID: "occ-client",
      EXPO_PUBLIC_COGNITO_OCCUPANTS_DOMAIN: "occ.auth.test",
      EXPO_PUBLIC_COGNITO_TACTICAL_ISSUER: "https://idp/tac",
      EXPO_PUBLIC_COGNITO_TACTICAL_CLIENT_ID: "tac-client",
      EXPO_PUBLIC_COGNITO_TACTICAL_DOMAIN: "tac.auth.test",
    }),
  };
});

const mem = (SecureStore as unknown as { __mem: Map<string, string> }).__mem;
const revokeAsync = AuthSession.revokeAsync as jest.Mock;
const openAuthSession = WebBrowser.openAuthSessionAsync as jest.Mock;
const dismissAuthSession = WebBrowser.dismissAuthSession as jest.Mock;
const unregister = unregisterOwnPushToken as jest.Mock;

const orden: string[] = [];

async function sesion(): Promise<void> {
  const idToken = fakeJwt({ exp: nowS() + 3000 });
  await saveSession({
    profile: "tactical",
    idToken,
    refreshToken: "rt-1",
    issuedAt: Date.now(),
    authAt: Date.now(),
    maxAgeS: 2_592_000,
  });
  useSessionStore.setState({
    status: "authenticated",
    profile: "tactical",
    idToken,
    me: null,
    deniedReason: null,
    signOutReason: null,
    authAt: Date.now(),
    maxAgeS: 2_592_000,
  });
}

beforeEach(() => {
  mem.clear();
  jest.clearAllMocks();
  orden.length = 0;
  unregister.mockImplementation(async () => {
    // El DELETE necesita la sesión VIVA: se comprueba en el momento de la llamada.
    orden.push(`push:${useSessionStore.getState().status}`);
    return "revoked";
  });
  revokeAsync.mockImplementation(async () => {
    orden.push("revoke");
    return true;
  });
  openAuthSession.mockImplementation(async () => {
    orden.push("hosted-ui");
    return { type: "success", url: "takab://auth/logout" };
  });
});

describe("logout() — el orden", () => {
  it("push (con sesión viva) → revoke → /logout de la Hosted UI → almacén", async () => {
    await sesion();
    await logout();
    expect(orden).toEqual(["push:authenticated", "revoke", "hosted-ui"]);
    expect(useSessionStore.getState().status).toBe("anonymous");
    expect(useSessionStore.getState().signOutReason).toBe("user");
    expect(mem.has(SESSION_KEY)).toBe(false);
  });

  it("revoca el REFRESH token contra el revocationEndpoint del pool del perfil", async () => {
    await sesion();
    await logout();
    expect(revokeAsync).toHaveBeenCalledWith(
      { token: "rt-1", clientId: "tac-client", tokenTypeHint: "refresh_token" },
      { revocationEndpoint: "https://tac.auth.test/oauth2/revoke" },
    );
  });

  it("abre el /logout del dominio del pool con el deep link registrado en Terraform", async () => {
    await sesion();
    await logout();
    expect(openAuthSession).toHaveBeenCalledWith(
      "https://tac.auth.test/logout?client_id=tac-client&logout_uri=takab%3A%2F%2Fauth%2Flogout",
      "takab://auth/logout",
    );
  });
});

describe("logout() — best-effort", () => {
  it("si TODO falla, el almacén se borra igual", async () => {
    await sesion();
    unregister.mockRejectedValue(new Error("boom"));
    revokeAsync.mockRejectedValue(new Error("400"));
    openAuthSession.mockRejectedValue(new Error("sin navegador"));

    const informe = await logout();

    expect(useSessionStore.getState().status).toBe("anonymous");
    expect(mem.has(SESSION_KEY)).toBe(false);
    expect(informe).toEqual({ push: "error", refresh: "error", hostedUi: "error" });
  });

  it("sin red (el revoke no llegó) no se abre un navegador que se quedaría en blanco", async () => {
    await sesion();
    revokeAsync.mockRejectedValue(new TypeError("Network request failed"));
    const informe = await logout();
    expect(openAuthSession).not.toHaveBeenCalled();
    expect(informe.hostedUi).toBe("skipped");
    expect(useSessionStore.getState().status).toBe("anonymous");
  });

  it("si la Hosted UI no vuelve a tiempo, se descarta la sesión del navegador y se sigue", async () => {
    await sesion();
    openAuthSession.mockReturnValue(new Promise(() => undefined));
    jest.useFakeTimers();
    const p = logout({ hostedUiTimeoutMs: 500 });
    await jest.advanceTimersByTimeAsync(501);
    const informe = await p;
    jest.useRealTimers();
    expect(dismissAuthSession).toHaveBeenCalled();
    expect(informe.hostedUi).toBe("timeout");
    expect(useSessionStore.getState().status).toBe("anonymous");
  });

  it("sin sesión guardada no hay nada que revocar, pero se limpia igual", async () => {
    useSessionStore.setState({ status: "authenticated", profile: "occupant", idToken: "x" });
    const informe = await logout();
    expect(revokeAsync).not.toHaveBeenCalled();
    expect(informe.refresh).toBe("none");
    expect(useSessionStore.getState().status).toBe("anonymous");
  });

  it("dos toques seguidos ⇒ UNA secuencia", async () => {
    await sesion();
    await Promise.all([logout(), logout()]);
    expect(revokeAsync).toHaveBeenCalledTimes(1);
    expect(openAuthSession).toHaveBeenCalledTimes(1);
  });
});
