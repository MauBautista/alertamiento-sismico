// T-2.02 — la sesión persiste SOLO en el almacén seguro del sistema
// (Keychain/Keystore vía expo-secure-store), jamás en AsyncStorage.
import * as SecureStore from "expo-secure-store";

import { clearSession, loadSession, saveSession, SESSION_KEY } from "./secureTokens";

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

  it("guarda y recupera la sesión completa", async () => {
    const session = {
      profile: "occupant" as const,
      idToken: "id.jwt",
      refreshToken: "refresh.jwt",
      issuedAt: 1752537600000,
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
