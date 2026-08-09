import { act, renderHook, waitFor } from "@testing-library/react-native";

import { useSessionStore } from "@/auth/session.store";

import {
  resetWatchedSiteForTests,
  setWatchedSite,
  siteFromScope,
  useWatchedSiteId,
} from "./mySite";

jest.mock("expo-secure-store", () => {
  const disco = new Map<string, string>();
  return {
    __disco: disco,
    getItemAsync: jest.fn(async (k: string) => disco.get(k) ?? null),
    setItemAsync: jest.fn(async (k: string, v: string) => void disco.set(k, v)),
    deleteItemAsync: jest.fn(async (k: string) => void disco.delete(k)),
  };
});

describe("siteFromScope — fallback táctico sin adivinar", () => {
  it("lista de sitios ⇒ el primero (selector fino en T-2.08)", () => {
    expect(siteFromScope(["s-1", "s-2"])).toBe("s-1");
  });

  it('"*" (todo el tenant) ⇒ null: no hay sitio único que vigilar', () => {
    expect(siteFromScope("*")).toBeNull();
  });

  it("vacío/ausente ⇒ null (default-deny, se declara)", () => {
    expect(siteFromScope([])).toBeNull();
    expect(siteFromScope(null)).toBeNull();
    expect(siteFromScope(undefined)).toBeNull();
  });
});

describe("useWatchedSiteId — el enrolamiento tiene que llegar a quien YA está montado", () => {
  beforeEach(async () => {
    resetWatchedSiteForTests();
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    (require("expo-secure-store") as { __disco: Map<string, string> }).__disco.clear();
    await act(async () => {
      useSessionStore.getState().setAuthenticated({
        profile: "occupant",
        idToken: "tok",
        me: null,
      });
    });
  });

  it("[T-2.103] un consumidor montado ANTES del enrolamiento ve el sitio al vincular", async () => {
    // `CrisisWatcher` vive en el layout RAÍZ: se monta antes del onboarding, con
    // SecureStore vacío en una instalación nueva.
    const { result } = await renderHook(() => useWatchedSiteId());
    await waitFor(() => expect(result.current).toBeNull());

    // El occupant se vincula a su edificio.
    await act(async () => {
      await setWatchedSite("site-abc");
    });

    // SIN este arreglo el hook se quedaba en null hasta reiniciar la app, y con
    // él se quedaba también el vigilante de crisis: sin sitio no hay
    // `mobile-state`, sin fase no hay toma de pantalla, y un sismo justo después
    // de enrolarse no avisaba a nadie. Medido en device el 2026-08-09.
    await waitFor(() => expect(result.current).toBe("site-abc"));
  });

  it("cerrar sesión suelta el sitio: la sesión siguiente no hereda el edificio", async () => {
    const { result } = await renderHook(() => useWatchedSiteId());
    await act(async () => {
      await setWatchedSite("site-abc");
    });
    await waitFor(() => expect(result.current).toBe("site-abc"));

    await act(async () => {
      useSessionStore.getState().signOut();
    });
    await waitFor(() => expect(result.current).toBeNull());
  });
});
