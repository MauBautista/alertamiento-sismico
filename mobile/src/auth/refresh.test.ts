// [T-8.04 · A-001/A-002/A-005/A-007/A-009] LA SESIÓN MÓVIL SE RENUEVA.
//
// Medido antes de esta ficha: `useAuth.ts` guardaba el refresh token y NINGÚN
// código lo usaba. El ID token vive 60 min; al vencer, el primer 401 cerraba la
// sesión y la app volvía a pedir contraseña —y TOTP a los tácticos— cada hora.
//
// Lo que se fija aquí:
//   · vuelo único: dos renovaciones a la vez gastan UN refresh (con rotación, dos
//     canjes paralelos del mismo refresh token pueden matar la sesión);
//   · tres salidas y sólo una expulsa: `dead` (Cognito rechazó el grant), frente
//     a `offline` (no se pudo preguntar), que CONSERVA la sesión;
//   · el cinturón del cliente (D-38): pasado `authAt + maxAgeS` la sesión está
//     muerta aunque el servidor no lo haya dicho, y ni se pregunta a Cognito;
//   · un cierre de sesión durante el vuelo no se resucita.
import * as AuthSession from "expo-auth-session";
import * as SecureStore from "expo-secure-store";

import {
  ensureFreshToken,
  onAppForeground,
  pastMaxAge,
  refreshSession,
  resetRefreshForTests,
  secondsLeft,
  wireSessionToForeground,
} from "./refresh";
import { loadSession, saveSession, SESSION_KEY } from "./secureTokens";
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

jest.mock("expo-auth-session", () => {
  class TokenError extends Error {
    code: string;
    params: Record<string, string>;
    constructor(params: { error: string }) {
      super(params.error);
      this.code = params.error;
      this.params = params;
    }
  }
  return { refreshAsync: jest.fn(), TokenError };
});

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
const { TokenError } = AuthSession as unknown as { TokenError: new (p: { error: string }) => Error };

const VIEJO = fakeJwt({ exp: nowS() - 10, auth_time: nowS() - 7200 });

async function sesionGuardada(over: Partial<Parameters<typeof saveSession>[0]> = {}) {
  const s = {
    profile: "tactical" as const,
    idToken: VIEJO,
    refreshToken: "rt-1",
    issuedAt: Date.now() - 7_200_000,
    idTokenExp: nowS() - 10,
    authAt: Date.now() - 7_200_000,
    maxAgeS: 2_592_000,
    ...over,
  };
  await saveSession(s);
  useSessionStore.setState({
    status: "authenticated",
    profile: s.profile,
    idToken: s.idToken,
    me: null,
    deniedReason: null,
    signOutReason: null,
    authAt: s.authAt,
    maxAgeS: s.maxAgeS,
  });
  return s;
}

function respuestaCognito(idToken: string, refreshToken?: string) {
  return { idToken, refreshToken, accessToken: "at", expiresIn: 3600, issuedAt: nowS() };
}

beforeEach(() => {
  mem.clear();
  jest.clearAllMocks();
  resetRefreshForTests();
  useSessionStore.setState({
    status: "anonymous",
    profile: null,
    idToken: null,
    me: null,
    deniedReason: null,
    signOutReason: null,
    authAt: null,
    maxAgeS: null,
  });
});

afterEach(() => {
  jest.useRealTimers();
});

describe("refreshSession — vuelo único", () => {
  it("dos llamadas concurrentes ⇒ UN refreshAsync, y ambas ven 'ok'", async () => {
    await sesionGuardada();
    const nuevo = fakeJwt({ exp: nowS() + 3600 });
    refreshAsync.mockResolvedValue(respuestaCognito(nuevo));

    const [a, b] = await Promise.all([refreshSession(), refreshSession()]);

    expect(a).toBe("ok");
    expect(b).toBe("ok");
    expect(refreshAsync).toHaveBeenCalledTimes(1);
    expect(refreshAsync).toHaveBeenCalledWith(
      { clientId: "tac-client", refreshToken: "rt-1" },
      expect.objectContaining({ tokenEndpoint: "https://tac.auth.test/oauth2/token" }),
    );
  });

  it("terminado el vuelo, una llamada NUEVA sí vuelve a preguntar", async () => {
    await sesionGuardada();
    refreshAsync.mockResolvedValue(respuestaCognito(fakeJwt({ exp: nowS() + 3600 })));
    await refreshSession();
    await refreshSession();
    expect(refreshAsync).toHaveBeenCalledTimes(2);
  });
});

describe("refreshSession — éxito", () => {
  it("persiste el ID token nuevo en el almacén seguro y en el store; authAt NO cambia", async () => {
    const antes = await sesionGuardada();
    const nuevo = fakeJwt({ exp: nowS() + 3600, auth_time: nowS() });
    refreshAsync.mockResolvedValue(respuestaCognito(nuevo));

    await expect(refreshSession()).resolves.toBe("ok");

    expect(useSessionStore.getState().idToken).toBe(nuevo);
    const guardada = await loadSession();
    expect(guardada?.idToken).toBe(nuevo);
    expect(guardada?.idTokenExp).toBe(nowS() + 3600);
    // El tope de D-38 cuenta desde el login REAL: un refresh no lo alarga,
    // aunque Cognito estrenara un `auth_time` (A-006, no medido).
    expect(guardada?.authAt).toBe(antes.authAt);
    expect(guardada?.refreshToken).toBe("rt-1");
  });

  it("con rotación, el refresh token NUEVO sustituye al viejo", async () => {
    await sesionGuardada();
    refreshAsync.mockResolvedValue(respuestaCognito(fakeJwt({ exp: nowS() + 3600 }), "rt-2"));
    await refreshSession();
    expect((await loadSession())?.refreshToken).toBe("rt-2");
  });
});

describe("refreshSession — las tres salidas", () => {
  it("invalid_grant ⇒ 'dead' y no toca lo guardado (la expulsión la decide quien llama)", async () => {
    await sesionGuardada();
    refreshAsync.mockRejectedValue(new TokenError({ error: "invalid_grant" }));
    await expect(refreshSession()).resolves.toBe("dead");
    expect((await loadSession())?.idToken).toBe(VIEJO);
  });

  it("error de red ⇒ 'offline' y la sesión se CONSERVA", async () => {
    await sesionGuardada();
    refreshAsync.mockRejectedValue(new TypeError("Network request failed"));
    await expect(refreshSession()).resolves.toBe("offline");
    expect(useSessionStore.getState().status).toBe("authenticated");
    expect((await loadSession())?.refreshToken).toBe("rt-1");
  });

  it("un error del servidor de Cognito que NO es del grant ⇒ 'offline', no 'dead'", async () => {
    await sesionGuardada();
    refreshAsync.mockRejectedValue(new TokenError({ error: "server_error" }));
    await expect(refreshSession()).resolves.toBe("offline");
  });

  it("una respuesta sin id_token ⇒ 'offline' (anómala, no prueba que la sesión murió)", async () => {
    await sesionGuardada();
    refreshAsync.mockResolvedValue({ accessToken: "at" });
    await expect(refreshSession()).resolves.toBe("offline");
  });

  it("sin refresh token guardado ⇒ 'dead' sin preguntar a Cognito", async () => {
    await sesionGuardada({ refreshToken: undefined });
    await expect(refreshSession()).resolves.toBe("dead");
    expect(refreshAsync).not.toHaveBeenCalled();
  });

  it("sin sesión guardada ⇒ 'dead'", async () => {
    await expect(refreshSession()).resolves.toBe("dead");
    expect(refreshAsync).not.toHaveBeenCalled();
  });

  it("si Cognito no contesta a tiempo ⇒ 'offline'; y si contesta TARDE, el token se guarda igual", async () => {
    // Con rotación, descartar una respuesta tardía perdería el refresh token
    // NUEVO y el viejo moriría al pasar la gracia: una expulsión fabricada.
    await sesionGuardada();
    jest.useFakeTimers();
    let contestar: (v: unknown) => void = () => undefined;
    refreshAsync.mockReturnValue(new Promise((r) => (contestar = r)));

    const intento = refreshSession({ timeoutMs: 1_000 });
    await jest.advanceTimersByTimeAsync(1_001);
    await expect(intento).resolves.toBe("offline");

    const tardio = fakeJwt({ exp: nowS() + 3600 });
    contestar(respuestaCognito(tardio, "rt-2"));
    jest.useRealTimers();
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));

    expect(useSessionStore.getState().idToken).toBe(tardio);
    expect((await loadSession())?.refreshToken).toBe("rt-2");
  });
});

describe("refreshSession — no resucita una sesión cerrada durante el vuelo", () => {
  it("signOut mientras Cognito contesta ⇒ ni store ni almacén vuelven a tener token", async () => {
    await sesionGuardada();
    let contestar: (v: unknown) => void = () => undefined;
    refreshAsync.mockReturnValue(new Promise((r) => (contestar = r)));

    const intento = refreshSession();
    await new Promise((r) => setTimeout(r, 0));
    useSessionStore.getState().signOut("user");
    contestar(respuestaCognito(fakeJwt({ exp: nowS() + 3600 })));

    await expect(intento).resolves.toBe("dead");
    expect(useSessionStore.getState().idToken).toBeNull();
    expect(mem.has(SESSION_KEY)).toBe(false);
  });
});

describe("[D-38] cinturón del cliente: authAt + maxAgeS", () => {
  it("pasado el tope, la sesión está muerta y NI SE PREGUNTA a Cognito", async () => {
    await sesionGuardada({ authAt: Date.now() - 86_401_000, maxAgeS: 86_400 });
    expect(pastMaxAge()).toBe(true);
    await expect(refreshSession()).resolves.toBe("dead");
    expect(refreshAsync).not.toHaveBeenCalled();
  });

  it("dentro del tope no hay cinturón que valga", async () => {
    await sesionGuardada({ authAt: Date.now() - 1_000, maxAgeS: 86_400 });
    expect(pastMaxAge()).toBe(false);
  });

  it("tope desconocido (/me aún no lo dijo) ⇒ sin cinturón: nadie queda fuera por actualizar", async () => {
    await sesionGuardada({ authAt: 0, maxAgeS: null });
    expect(pastMaxAge()).toBe(false);
  });
});

describe("ensureFreshToken — barato cuando no hace falta", () => {
  it("a un token con margen NO se le renueva", async () => {
    await sesionGuardada();
    useSessionStore.setState({ idToken: fakeJwt({ exp: nowS() + 3000 }) });
    await expect(ensureFreshToken(300)).resolves.toBe("ok");
    expect(refreshAsync).not.toHaveBeenCalled();
  });

  it("a un token con menos del margen se le renueva", async () => {
    await sesionGuardada();
    useSessionStore.setState({ idToken: fakeJwt({ exp: nowS() + 120 }) });
    refreshAsync.mockResolvedValue(respuestaCognito(fakeJwt({ exp: nowS() + 3600 })));
    await expect(ensureFreshToken(300)).resolves.toBe("ok");
    expect(refreshAsync).toHaveBeenCalledTimes(1);
  });

  it("recién fallado por red, no se martillea a Cognito en cada petición", async () => {
    await sesionGuardada();
    refreshAsync.mockRejectedValue(new TypeError("Network request failed"));
    await expect(ensureFreshToken(300)).resolves.toBe("offline");
    await expect(ensureFreshToken(300)).resolves.toBe("offline");
    expect(refreshAsync).toHaveBeenCalledTimes(1);
  });

  it("secondsLeft lee el exp del JWT; un token ilegible cuenta como vencido", () => {
    expect(secondsLeft(fakeJwt({ exp: nowS() + 100 }))).toBeGreaterThan(90);
    expect(secondsLeft("basura")).toBe(-Infinity);
    expect(secondsLeft(null)).toBe(-Infinity);
  });
});

describe("volver a primer plano", () => {
  it("renueva un token por vencer", async () => {
    await sesionGuardada();
    refreshAsync.mockResolvedValue(respuestaCognito(fakeJwt({ exp: nowS() + 3600 })));
    await onAppForeground();
    expect(refreshAsync).toHaveBeenCalledTimes(1);
    expect(useSessionStore.getState().status).toBe("authenticated");
  });

  it("refresh muerto ⇒ fuera, con motivo 'expired'", async () => {
    await sesionGuardada();
    refreshAsync.mockRejectedValue(new TokenError({ error: "invalid_grant" }));
    await onAppForeground();
    expect(useSessionStore.getState().status).toBe("anonymous");
    expect(useSessionStore.getState().signOutReason).toBe("expired");
  });

  it("sin red ⇒ la sesión se queda (la app ya sabe mostrar lo retenido)", async () => {
    await sesionGuardada();
    refreshAsync.mockRejectedValue(new TypeError("Network request failed"));
    await onAppForeground();
    expect(useSessionStore.getState().status).toBe("authenticated");
  });

  it("pasado el tope ⇒ fuera con motivo 'max_age' aunque el servidor no lo haya dicho", async () => {
    await sesionGuardada({ authAt: Date.now() - 2_592_001_000, maxAgeS: 2_592_000 });
    await onAppForeground();
    expect(useSessionStore.getState().signOutReason).toBe("max_age");
    expect(refreshAsync).not.toHaveBeenCalled();
  });

  it("anónimo ⇒ no hace nada", async () => {
    await onAppForeground();
    expect(refreshAsync).not.toHaveBeenCalled();
  });

  it("el cable con AppState dispara sólo con 'active', y se suelta", async () => {
    await sesionGuardada();
    refreshAsync.mockResolvedValue(respuestaCognito(fakeJwt({ exp: nowS() + 3600 })));
    let cb: (s: string) => void = () => undefined;
    const remove = jest.fn();
    const soltar = wireSessionToForeground({
      addEventListener: (_t: "change", f: (s: string) => void) => {
        cb = f;
        return { remove };
      },
    });
    cb("background");
    cb("inactive");
    expect(refreshAsync).not.toHaveBeenCalled();
    cb("active");
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));
    expect(refreshAsync).toHaveBeenCalledTimes(1);
    soltar();
    expect(remove).toHaveBeenCalled();
  });
});
