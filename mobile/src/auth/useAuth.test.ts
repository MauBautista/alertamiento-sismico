// [T-8.04] EL ARRANQUE RENUEVA ANTES DE PREGUNTAR A /me.
//
// Medido antes de esta ficha (A-001, paso 4): con el token guardado ya vencido,
// `bootstrapSession` mandaba ese token a /me, la API contestaba 401 y el
// interceptor cerraba la sesión — una app abierta por la mañana pedía contraseña
// aunque el refresh token siguiera vivo 29 días más.
//
// También el login: la sesión recién creada guarda `authAt` (el `auth_time` del
// token, la hora del login REAL) y `idTokenExp`; y /me siembra `maxAgeS` (D-38).
import * as AuthSession from "expo-auth-session";
import * as SecureStore from "expo-secure-store";
import { meMeGet } from "@takab/sdk";

import { loadSession, saveSession } from "./secureTokens";
import { useSessionStore } from "./session.store";
import { resetRefreshForTests } from "./refresh";
import { fakeJwt, nowS } from "./testJwt";
import { bootstrapSession, exchangeAndResolve } from "./useAuth";

jest.mock("expo-secure-store", () => {
  const mem = new Map<string, string>();
  return {
    __mem: mem,
    getItemAsync: jest.fn(async (k: string) => mem.get(k) ?? null),
    setItemAsync: jest.fn(async (k: string, v: string) => void mem.set(k, v)),
    deleteItemAsync: jest.fn(async (k: string) => void mem.delete(k)),
  };
});

jest.mock("expo-web-browser", () => ({ maybeCompleteAuthSession: jest.fn() }));

jest.mock("expo-auth-session", () => {
  class TokenError extends Error {
    code: string;
    constructor(p: { error: string }) {
      super(p.error);
      this.code = p.error;
    }
  }
  return {
    refreshAsync: jest.fn(),
    exchangeCodeAsync: jest.fn(),
    useAuthRequest: jest.fn(),
    ResponseType: { Code: "code" },
    TokenError,
  };
});

jest.mock("@takab/sdk", () => ({ meMeGet: jest.fn() }));

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
const refreshAsync = AuthSession.refreshAsync as jest.Mock;
const exchangeCodeAsync = AuthSession.exchangeCodeAsync as jest.Mock;
const me = meMeGet as jest.Mock;
const { TokenError } = AuthSession as unknown as { TokenError: new (p: { error: string }) => Error };

const ME_BRIGADISTA = {
  role: "brigadista",
  surface: "mobile",
  session_max_age_s: 2_592_000,
  session_expires_at: null,
};

/** Lo que /me vio en la cabecera Authorization, en orden. */
const tokensVistosPorMe: (string | null)[] = [];

beforeEach(() => {
  mem.clear();
  jest.clearAllMocks();
  resetRefreshForTests();
  tokensVistosPorMe.length = 0;
  me.mockImplementation(async () => {
    tokensVistosPorMe.push(useSessionStore.getState().idToken);
    return { data: ME_BRIGADISTA, response: { status: 200 } };
  });
  useSessionStore.setState({
    status: "booting",
    profile: null,
    idToken: null,
    me: null,
    deniedReason: null,
    signOutReason: null,
    authAt: null,
    maxAgeS: null,
  });
});

async function guardar(idToken: string, over: Record<string, unknown> = {}) {
  await saveSession({
    profile: "tactical",
    idToken,
    refreshToken: "rt-1",
    issuedAt: Date.now() - 3_600_000,
    authAt: Date.now() - 3_600_000,
    maxAgeS: null,
    ...over,
  });
}

describe("bootstrapSession", () => {
  it("token guardado VENCIDO ⇒ renueva ANTES de /me, y /me recibe el token nuevo", async () => {
    const vencido = fakeJwt({ exp: nowS() - 60 });
    const nuevo = fakeJwt({ exp: nowS() + 3600 });
    await guardar(vencido);
    const orden: string[] = [];
    refreshAsync.mockImplementation(async () => {
      orden.push("refresh");
      return { idToken: nuevo, accessToken: "at" };
    });
    me.mockImplementation(async () => {
      orden.push("me");
      tokensVistosPorMe.push(useSessionStore.getState().idToken);
      return { data: ME_BRIGADISTA, response: { status: 200 } };
    });

    await bootstrapSession();

    expect(orden).toEqual(["refresh", "me"]);
    expect(tokensVistosPorMe).toEqual([nuevo]);
    const s = useSessionStore.getState();
    expect(s.status).toBe("authenticated");
    expect(s.idToken).toBe(nuevo);
  });

  it("token guardado con margen ⇒ NO renueva: /me directo", async () => {
    const vivo = fakeJwt({ exp: nowS() + 3000 });
    await guardar(vivo);
    await bootstrapSession();
    expect(refreshAsync).not.toHaveBeenCalled();
    expect(tokensVistosPorMe).toEqual([vivo]);
  });

  it("refresh muerto ⇒ login (motivo 'expired') sin llegar a /me", async () => {
    await guardar(fakeJwt({ exp: nowS() - 60 }));
    refreshAsync.mockRejectedValue(new TokenError({ error: "invalid_grant" }));
    await bootstrapSession();
    expect(me).not.toHaveBeenCalled();
    expect(useSessionStore.getState().status).toBe("anonymous");
    expect(useSessionStore.getState().signOutReason).toBe("expired");
  });

  it("sin red para renovar NI para /me ⇒ sesión RETENIDA (me = null), no login", async () => {
    await guardar(fakeJwt({ exp: nowS() - 60 }));
    refreshAsync.mockRejectedValue(new TypeError("Network request failed"));
    me.mockRejectedValue(new TypeError("Network request failed"));
    await bootstrapSession();
    const s = useSessionStore.getState();
    expect(s.status).toBe("authenticated");
    expect(s.me).toBeNull();
  });

  it("[D-38] pasado el tope guardado ⇒ login con motivo 'max_age', sin red de por medio", async () => {
    await guardar(fakeJwt({ exp: nowS() + 3000 }), {
      authAt: Date.now() - 86_401_000,
      maxAgeS: 86_400,
    });
    await bootstrapSession();
    expect(me).not.toHaveBeenCalled();
    expect(refreshAsync).not.toHaveBeenCalled();
    expect(useSessionStore.getState().signOutReason).toBe("max_age");
  });

  it("/me siembra el tope del rol en el store y en el almacén", async () => {
    await guardar(fakeJwt({ exp: nowS() + 3000 }));
    await bootstrapSession();
    expect(useSessionStore.getState().maxAgeS).toBe(2_592_000);
    expect((await loadSession())?.maxAgeS).toBe(2_592_000);
  });
});

describe("exchangeAndResolve (login)", () => {
  it("guarda authAt = auth_time del token (ms), idTokenExp y el tope que dice /me", async () => {
    const authTime = nowS() - 5;
    // El `exp` se fija UNA vez: calcularlo otra vez en la aserción cruzaba de
    // segundo en una suite cargada y el test fallaba por 1 s (2026-09-23).
    const exp = nowS() + 3600;
    const idToken = fakeJwt({ exp, auth_time: authTime });
    exchangeCodeAsync.mockResolvedValue({ idToken, refreshToken: "rt-login" });

    await exchangeAndResolve("tactical", "code-único", "verifier");

    const s = await loadSession();
    expect(s?.authAt).toBe(authTime * 1000);
    expect(s?.idTokenExp).toBe(exp);
    expect(s?.refreshToken).toBe("rt-login");
    expect(s?.maxAgeS).toBe(2_592_000);
    const st = useSessionStore.getState();
    expect(st.status).toBe("authenticated");
    expect(st.authAt).toBe(authTime * 1000);
    expect(st.maxAgeS).toBe(2_592_000);
    expect(st.signOutReason).toBeNull();
  });
});
