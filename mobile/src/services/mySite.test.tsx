import { act, renderHook, waitFor } from "@testing-library/react-native";
import type { MeResponse } from "@takab/sdk";

import { useSessionStore } from "@/auth/session.store";

import {
  getStoredWatchedSite,
  resetWatchedSiteForTests,
  setWatchedSite,
  siteFromMe,
  siteFromScope,
  useWatchedSiteId,
} from "./mySite";

function me(sub: string, sites: string[] = []): MeResponse {
  return {
    sub,
    site_scope: [],
    enrolled_sites: sites.map((s) => ({ site_id: s, site_name: `Edificio ${s}` })),
  } as unknown as MeResponse;
}

async function entrarComo(m: MeResponse | null): Promise<void> {
  await act(async () => {
    useSessionStore
      .getState()
      .setAuthenticated({ profile: "occupant", idToken: "tok", me: m as MeResponse | null });
  });
}

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

// ─── [T-2.114] El sitio vigilado dejó de heredarse entre usuarios ────────────

describe("siteFromMe — el SERVIDOR es la fuente de verdad del inmueble", () => {
  it("occupant enrolado ⇒ su inmueble sale de /me (no del teléfono)", () => {
    expect(siteFromMe(me("u-1", ["site-abc"]))).toBe("site-abc");
  });

  it("sin enrolamiento cae al site_scope del claim (táctico)", () => {
    expect(siteFromMe({ sub: "u-2", site_scope: ["s-9"] } as unknown as MeResponse)).toBe("s-9");
  });

  it("sin /me no se adivina nada", () => {
    expect(siteFromMe(null)).toBeNull();
    expect(siteFromMe(me("u-3"))).toBeNull();
  });
});

describe("[T-2.114] dos usuarios en el MISMO teléfono", () => {
  beforeEach(async () => {
    resetWatchedSiteForTests();
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    (require("expo-secure-store") as { __disco: Map<string, string> }).__disco.clear();
    await act(async () => {
      useSessionStore.setState({ status: "booting", profile: null, idToken: null, me: null });
    });
  });

  it("el segundo usuario NO hereda el edificio del primero", async () => {
    // Ana entra y se enrola en su edificio.
    await entrarComo(me("ana", ["site-ana"]));
    const { result, rerender } = await renderHook(() => useWatchedSiteId());
    await act(async () => {
      await setWatchedSite("site-ana");
    });
    await waitFor(() => expect(result.current).toBe("site-ana"));

    // Ana cierra sesión y Beto entra EN EL MISMO TELÉFONO, sin enrolarse aún.
    await act(async () => {
      useSessionStore.getState().signOut();
    });
    await waitFor(() => expect(result.current).toBeNull());
    await entrarComo(me("beto"));
    rerender(undefined);

    // El defecto: Beto veía el edificio de Ana y `CrisisWatcher` vigilaba un
    // inmueble que no es el suyo. Ahora se declara "sin inmueble".
    await waitFor(() => expect(result.current).toBeNull());
  });

  it("cerrar sesión BORRA el sitio del disco, no solo de la memoria", async () => {
    // El test viejo solo comprobaba el store en memoria; el valor seguía en
    // SecureStore y la siguiente sesión lo re-hidrataba. Ése era el bug.
    await entrarComo(me("ana", ["site-ana"]));
    await renderHook(() => useWatchedSiteId());
    await act(async () => {
      await setWatchedSite("site-ana");
    });
    expect(await getStoredWatchedSite()).toBe("site-ana");

    await act(async () => {
      useSessionStore.getState().signOut();
    });
    await waitFor(async () => expect(await getStoredWatchedSite()).toBeNull());
  });

  it("el MISMO ocupante que vuelve recupera su edificio de /me, sin código nuevo", async () => {
    // Ésta es la razón por la que ahora sí se puede soltar el caché: el
    // enrolamiento vive en la base y `/me` lo devuelve.
    await entrarComo(me("ana", ["site-ana"]));
    const { result } = await renderHook(() => useWatchedSiteId());
    await waitFor(() => expect(result.current).toBe("site-ana"));
    expect(await getStoredWatchedSite()).toBe("site-ana");
  });

  it("un caché de OTRA identidad se ignora aunque sobreviva (app muerta a media salida)", async () => {
    // Defensa en profundidad: si el borrado del cierre de sesión no llegó a
    // ejecutarse, el valor sigue estando marcado con el sujeto que lo fijó.
    await entrarComo(me("ana", ["site-ana"]));
    await renderHook(() => useWatchedSiteId());
    await act(async () => {
      await setWatchedSite("site-ana");
    });

    resetWatchedSiteForTests();
    await entrarComo(me("beto"));
    const { result } = await renderHook(() => useWatchedSiteId());
    await waitFor(() => expect(result.current).toBeNull());
  });

  it("arranque OFFLINE (me = null): la sesión guardada conserva su edificio", async () => {
    // Sin red `bootstrapSession` no puede llamar a /me y deja `me = null`. El
    // ocupante sigue siendo el mismo (su sesión está en el Keychain), así que
    // el caché es la respuesta correcta: dejarlo sin inmueble aquí sería
    // dejarlo sin pantalla de crisis (regla de oro 2).
    await entrarComo(me("ana", ["site-ana"]));
    await renderHook(() => useWatchedSiteId());
    await act(async () => {
      await setWatchedSite("site-ana");
    });

    resetWatchedSiteForTests();
    await entrarComo(null);
    const { result } = await renderHook(() => useWatchedSiteId());
    await waitFor(() => expect(result.current).toBe("site-ana"));
  });
});
