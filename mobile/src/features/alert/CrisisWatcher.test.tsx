// UBICACIÓN: fuera de `src/app/` a propósito — `expo-router` barre ese árbol
// con `require.context` y un `*.test.tsx` ahí dentro rompe el bundle (pasó el
// 2026-08-08 y la app no compiló durante un día).
//
// [T-2.114] EL VIGILANTE DE CRISIS NO PUEDE VIGILAR UN EDIFICIO AJENO.
//
// `CrisisWatcher` se monta en el layout RAÍZ y deriva su sitio de
// `useWatchedSiteId`. Mientras el inmueble vivía SOLO en el SecureStore y no se
// soltaba al cerrar sesión, un usuario distinto en el mismo teléfono acababa
// vigilando el edificio del anterior: en el servidor lo frena
// `assert_site_access` (404), así que el efecto neto es que el nuevo portador se
// queda SIN vigilante — y sin vigilante no hay toma de pantalla de crisis.
//
// Lo que se prueba es la COSTURA: qué `site_id` recibe `useAlertState`. Se
// moquea ese hook (y las fronteras de router/notificaciones) para no arrastrar
// el cliente de react-query con sus temporizadores de refetch; `mySite` corre DE
// VERDAD, porque de dónde sale el sitio es justo el objeto de la prueba.
import { act, render, waitFor } from "@testing-library/react-native";
import type { MeResponse } from "@takab/sdk";

import { useSessionStore } from "@/auth/session.store";
import { resetWatchedSiteForTests, setWatchedSite } from "@/services/mySite";

import { CrisisWatcher } from "./CrisisWatcher";

jest.mock("expo-router", () => ({
  useRouter: () => ({ push: jest.fn() }),
  usePathname: () => "/",
}));

jest.mock("expo-notifications", () => ({
  setNotificationHandler: jest.fn(),
  addNotificationReceivedListener: jest.fn(() => ({ remove: jest.fn() })),
  addNotificationResponseReceivedListener: jest.fn(() => ({ remove: jest.fn() })),
}));

jest.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: jest.fn() }),
}));

const vigilados: (string | null)[] = [];
jest.mock("./useAlertState", () => ({
  MOBILE_STATE_KEY: "mobile-state",
  useAlertState: (siteId: string | null) => {
    vigilados.push(siteId);
    return { state: null, data: null };
  },
}));

jest.mock("expo-secure-store", () => {
  const disco = new Map<string, string>();
  return {
    __disco: disco,
    getItemAsync: jest.fn(async (k: string) => disco.get(k) ?? null),
    setItemAsync: jest.fn(async (k: string, v: string) => void disco.set(k, v)),
    deleteItemAsync: jest.fn(async (k: string) => void disco.delete(k)),
  };
});

/** El sitio que el vigilante está observando AHORA (último render). */
function vigilando(): string | null {
  return vigilados.at(-1) ?? null;
}

async function entrarComo(sub: string, sitios: string[]): Promise<void> {
  await act(async () => {
    useSessionStore.getState().setAuthenticated({
      profile: "occupant",
      idToken: "tok",
      me: {
        sub,
        site_scope: [],
        enrolled_sites: sitios.map((s) => ({ site_id: s, site_name: `Edificio ${s}` })),
      } as unknown as MeResponse,
    });
  });
}

beforeEach(() => {
  vigilados.length = 0;
  resetWatchedSiteForTests();
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  (require("expo-secure-store") as { __disco: Map<string, string> }).__disco.clear();
  useSessionStore.setState({ status: "booting", profile: null, idToken: null, me: null });
});

describe("[T-2.114] CrisisWatcher tras cambiar de usuario en el mismo teléfono", () => {
  it("vigila el inmueble del portador ACTUAL, jamás el del anterior", async () => {
    await entrarComo("ana", ["site-ana"]);
    await act(async () => {
      render(<CrisisWatcher />);
    });
    await act(async () => {
      await setWatchedSite("site-ana");
    });
    await waitFor(() => expect(vigilando()).toBe("site-ana"));

    // Ana sale; Beto entra en el MISMO teléfono, con SU propio edificio.
    await act(async () => {
      useSessionStore.getState().signOut();
    });
    await entrarComo("beto", ["site-beto"]);

    await waitFor(() => expect(vigilando()).toBe("site-beto"));
  });

  it("un portador nuevo SIN enrolamiento no vigila NINGÚN sitio", async () => {
    await entrarComo("ana", ["site-ana"]);
    await act(async () => {
      render(<CrisisWatcher />);
    });
    await act(async () => {
      await setWatchedSite("site-ana");
    });
    await waitFor(() => expect(vigilando()).toBe("site-ana"));

    await act(async () => {
      useSessionStore.getState().signOut();
    });
    await entrarComo("beto", []);

    // Sin inmueble no se inventa uno: se declara null y el vigilante calla.
    // Antes heredaba "site-ana" y preguntaba por un edificio que no es suyo.
    await waitFor(() => expect(vigilando()).toBeNull());
  });

  it("cerrar sesión deja de vigilar de inmediato (no se queda mirando el edificio)", async () => {
    await entrarComo("ana", ["site-ana"]);
    await act(async () => {
      render(<CrisisWatcher />);
    });
    await act(async () => {
      await setWatchedSite("site-ana");
    });
    await waitFor(() => expect(vigilando()).toBe("site-ana"));

    await act(async () => {
      useSessionStore.getState().signOut();
    });
    await waitFor(() => expect(vigilando()).toBeNull());
  });
});
