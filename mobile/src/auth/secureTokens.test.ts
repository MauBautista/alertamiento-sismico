// T-2.02 — la sesión persiste SOLO en el almacén seguro del sistema
// (Keychain/Keystore vía expo-secure-store), jamás en AsyncStorage.
//
// [T-8.04 · D-38] La sesión guardada gana tres campos —`idTokenExp`, `authAt` y
// `maxAgeS`— y NINGUNA sesión guardada antes de ellos puede expulsar a nadie al
// actualizar la app: lo que falte se DERIVA (el `exp` del propio JWT, el login
// real de `issuedAt`) en vez de tratar el registro como corrupto.
import * as SecureStore from "expo-secure-store";

import {
  clearSession,
  decodeJwtClaims,
  loadSession,
  saveSession,
  SESSION_KEY,
} from "./secureTokens";
import { fakeJwt } from "./testJwt";

jest.mock("expo-secure-store", () => {
  const mem = new Map<string, string>();
  return {
    getItemAsync: jest.fn(async (k: string) => mem.get(k) ?? null),
    setItemAsync: jest.fn(async (k: string, v: string) => {
      mem.set(k, v);
    }),
    deleteItemAsync: jest.fn(async (k: string) => {
      mem.delete(k);
    }),
    __mem: mem,
  };
});

const mem = (SecureStore as unknown as { __mem: Map<string, string> }).__mem;

describe("secureTokens", () => {
  beforeEach(() => {
    mem.clear();
    jest.clearAllMocks();
  });

  it("guarda y recupera la sesión completa (con los campos de T-8.04)", async () => {
    const session = {
      profile: "occupant" as const,
      idToken: fakeJwt({ exp: 1_900_000_000 }),
      refreshToken: "refresh.jwt",
      issuedAt: 1752537600000,
      idTokenExp: 1_900_000_000,
      authAt: 1752537500000,
      maxAgeS: 7_776_000,
    };
    await saveSession(session);
    expect(SecureStore.setItemAsync).toHaveBeenCalledWith(SESSION_KEY, JSON.stringify(session));
    await expect(loadSession()).resolves.toEqual(session);
  });

  it("sin sesión guardada ⇒ null", async () => {
    await expect(loadSession()).resolves.toBeNull();
  });

  it("payload corrupto o de forma inválida ⇒ null y se purga (jamás revienta el arranque)", async () => {
    mem.set(SESSION_KEY, "{no-json");
    await expect(loadSession()).resolves.toBeNull();
    expect(SecureStore.deleteItemAsync).toHaveBeenCalledWith(SESSION_KEY);

    mem.set(SESSION_KEY, JSON.stringify({ idToken: 42 }));
    await expect(loadSession()).resolves.toBeNull();
  });

  it("clearSession borra la llave", async () => {
    mem.set(SESSION_KEY, "x");
    await clearSession();
    expect(mem.has(SESSION_KEY)).toBe(false);
  });
});

describe("[T-8.04] compatibilidad con sesiones guardadas ANTES de los campos nuevos", () => {
  beforeEach(() => {
    mem.clear();
    jest.clearAllMocks();
  });

  it("una sesión vieja se CARGA: exp sale del JWT, el login real de issuedAt, sin tope conocido", async () => {
    // La forma exacta que escribía la app hasta T-8.04.
    const vieja = {
      profile: "tactical",
      idToken: fakeJwt({ exp: 1_800_000_123, auth_time: 1_700_000_000 }),
      refreshToken: "rt",
      issuedAt: 1_752_537_600_000,
    };
    mem.set(SESSION_KEY, JSON.stringify(vieja));

    const s = await loadSession();

    expect(s).not.toBeNull();
    expect(s?.idTokenExp).toBe(1_800_000_123);
    // `issuedAt` ERA la hora del canje del código, es decir, el login real.
    expect(s?.authAt).toBe(1_752_537_600_000);
    // Hasta que /me lo diga, no hay tope: nadie queda fuera por actualizar.
    expect(s?.maxAgeS).toBeNull();
    expect(SecureStore.deleteItemAsync).not.toHaveBeenCalled();
  });

  it("un JWT ilegible NO purga la sesión: exp = 0 fuerza a renovar, no a volver a entrar", async () => {
    mem.set(
      SESSION_KEY,
      JSON.stringify({ profile: "occupant", idToken: "no-es-un-jwt", refreshToken: "rt", issuedAt: 5 }),
    );
    const s = await loadSession();
    expect(s?.idTokenExp).toBe(0);
    expect(s?.refreshToken).toBe("rt");
    expect(SecureStore.deleteItemAsync).not.toHaveBeenCalled();
  });

  it("un campo nuevo con tipo equivocado se IGNORA (se deriva), no tumba la sesión", async () => {
    mem.set(
      SESSION_KEY,
      JSON.stringify({
        profile: "occupant",
        idToken: fakeJwt({ exp: 1_800_000_000 }),
        issuedAt: 7,
        idTokenExp: "mañana",
        authAt: null,
        maxAgeS: "30d",
      }),
    );
    const s = await loadSession();
    expect(s).toEqual(
      expect.objectContaining({ idTokenExp: 1_800_000_000, authAt: 7, maxAgeS: null }),
    );
  });
});

describe("decodeJwtClaims", () => {
  it("lee los claims numéricos del payload (base64url, sin verificar firma)", () => {
    const claims = decodeJwtClaims(fakeJwt({ exp: 123, auth_time: 100, name: "Ñandú Pérez" }));
    expect(claims?.exp).toBe(123);
    expect(claims?.auth_time).toBe(100);
  });

  it("basura ⇒ null (jamás lanza)", () => {
    expect(decodeJwtClaims("")).toBeNull();
    expect(decodeJwtClaims("a.b")).toBeNull();
    expect(decodeJwtClaims("a.%%%.c")).toBeNull();
  });
});
