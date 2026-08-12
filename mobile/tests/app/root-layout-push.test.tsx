// UBICACIÓN: este test vive FUERA de `src/app/` a propósito, y no es estilo.
// `expo-router` construye su tabla de rutas con un `require.context` sobre
// `src/app`, que barre TODOS los ficheros de ahí — los `*.test.tsx` incluidos.
// Con un test dentro, el bundle arrastra `@testing-library/react-native` y la
// app NO ARRANCA (pasó del 8 al 9 de agosto de 2026, sin que jest/tsc/eslint lo
// vieran). Lo vigila el gate `expo export` del job `mobile` en CI.
//
// [T-2.109] EL TOKEN SE REGISTRA CON EL INMUEBLE, Y EN CADA MOMENTO DEL CICLO.
//
// `_layout.tsx` llamaba a `registerDeviceForPush()` SIN argumento —único punto
// de llamada de toda la app—, así que el registro mandaba `site_id: null`. El
// orquestador de la nube filtra a sus destinatarios con
// `WHERE site_id = <uuid> AND tenant_id = ... AND revoked_at IS NULL`, y NULL
// no iguala a un UUID: ningún dispositivo entraba jamás en la lista.
//
// Hoy no hay regresión viva — `push_tokens` está VACÍA en producción porque el
// canal real sigue detrás de GATE-STORE (T-2.97) — y por eso es peor: es una
// MINA. El día que APNs/FCM aterricen, el registro seguiría mandando null, el
// filtro seguiría descartando, y la acreditación saldría VERDE sin que sonara
// un solo teléfono.
//
// Y había un segundo agujero encima: el efecto dependía SOLO de `status`, así
// que ni siquiera volvía a correr al enrolarse. Un teléfono que entraba sin
// sitio y luego canjeaba su código se quedaba sin re-registrar hasta reinstalar
// o cerrar sesión. Por eso el efecto depende AHORA del sitio vigilado, que es
// un store observable desde T-2.103: el enrolamiento lo fija y el registro se
// entera solo.
//
// Se moquean las FRONTERAS (router, notificaciones, SDK, almacén seguro y los
// vigilantes que no son objeto de esta prueba); `mySite` corre DE VERDAD,
// porque la fuente del `site_id` es justo lo que se está probando.
import { act, render, waitFor } from "@testing-library/react-native";
import type { MeResponse } from "@takab/sdk";
import type { ReactNode } from "react";

import { useSessionStore } from "@/auth/session.store";
import { resetWatchedSiteForTests, setWatchedSite } from "@/services/mySite";
import { registerDeviceForPush } from "@/services/push";

import RootLayout from "@/app/_layout";

jest.mock("expo-router", () => {
  const React = jest.requireActual("react") as typeof import("react");
  const Stack = ({ children }: { children?: ReactNode }) =>
    React.createElement(React.Fragment, null, children);
  // [T-2.125] `Screen` con nombre, no una flecha anónima colgada de `Stack`:
  // `react/display-name` lo exigía y nadie lo veía porque `expo lint` no
  // alcanzaba `tests/**`. No es cosmética — un componente sin nombre sale como
  // `<Unknown>` en el árbol renderizado, que es justo lo que se lee cuando uno
  // de estos tests falla.
  const Screen = () => null;
  Screen.displayName = "Stack.Screen";
  (Stack as unknown as { Screen: typeof Screen }).Screen = Screen;
  return { Stack, useRouter: () => ({ push: jest.fn(), replace: jest.fn() }) };
});

jest.mock("expo-status-bar", () => ({ StatusBar: () => null }));

jest.mock("expo-secure-store", () => {
  const disco = new Map<string, string>();
  return {
    __disco: disco,
    getItemAsync: jest.fn(async (k: string) => disco.get(k) ?? null),
    setItemAsync: jest.fn(async (k: string, v: string) => void disco.set(k, v)),
    deleteItemAsync: jest.fn(async (k: string) => void disco.delete(k)),
  };
});

jest.mock("@/services/sdk", () => ({ configureApiClient: jest.fn() }));
jest.mock("@/auth/useAuth", () => ({ bootstrapSession: jest.fn(async () => undefined) }));
jest.mock("@/features/alert/CrisisWatcher", () => ({ CrisisWatcher: () => null }));
jest.mock("@/offline/OfflineSyncGate", () => ({ OfflineSyncGate: () => null }));
jest.mock("@/services/push", () => ({ registerDeviceForPush: jest.fn(async () => "registered") }));

const registrar = registerDeviceForPush as jest.Mock;

/** Sitios pasados al registro, en orden (lo único que importa aquí). */
function sitiosRegistrados(): (string | null)[] {
  return registrar.mock.calls.map((c) => c[0] ?? null);
}

async function entrar(): Promise<void> {
  await act(async () => {
    useSessionStore.getState().setAuthenticated({ profile: "occupant", idToken: "tok", me: null });
  });
}

beforeEach(() => {
  registrar.mockClear();
  resetWatchedSiteForTests();
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  (require("expo-secure-store") as { __disco: Map<string, string> }).__disco.clear();
  useSessionStore.setState({ status: "booting", profile: null, idToken: null, me: null });
});

describe("[T-2.109] el registro del push lleva el inmueble en todo el ciclo de vida", () => {
  it("arranque con edificio ya vinculado ⇒ el token se registra CON el inmueble", async () => {
    await setWatchedSite("site-abc"); // sesión anterior: el sitio vive en el disco
    resetWatchedSiteForTests(); // ...pero la app arranca de cero (store en null)

    await render(<RootLayout />);
    await entrar();

    // La hidratación de `useWatchedSiteId` resuelve el sitio del disco y el
    // registro se re-dispara con él. Sin esto viajaba `site_id: null`.
    await waitFor(() => expect(sitiosRegistrados()).toContain("site-abc"));
    expect(registrar).not.toHaveBeenCalledWith(undefined);
  });

  it("enrolarse RE-REGISTRA el token: sin reinstalar y sin cerrar sesión", async () => {
    await render(<RootLayout />);
    await entrar();

    // Instalación nueva: autenticado y todavía sin edificio (paso 3 de 3).
    await waitFor(() => expect(sitiosRegistrados()).toEqual([null]));

    // El occupant canjea su código: `enrolamiento.tsx` fija el sitio vigilado.
    await act(async () => {
      await setWatchedSite("site-abc");
    });

    await waitFor(() => expect(sitiosRegistrados()).toEqual([null, "site-abc"]));
  });

  it("cambiar de edificio re-apunta el token (no se queda en el anterior)", async () => {
    await render(<RootLayout />);
    await entrar();
    await act(async () => {
      await setWatchedSite("site-abc");
    });
    await waitFor(() => expect(sitiosRegistrados()).toContain("site-abc"));

    await act(async () => {
      await setWatchedSite("site-otro");
    });

    // El upsert del backend es por `token`: re-registrar con otro sitio MUEVE la
    // fila, no crea una segunda. Lo que no puede pasar es que nadie lo llame.
    await waitFor(() => expect(sitiosRegistrados().at(-1)).toBe("site-otro"));
  });

  it("[T-2.114] cerrar sesión suelta el sitio y quien vuelve lo recupera de /me", async () => {
    await render(<RootLayout />);
    await entrar();
    await act(async () => {
      await setWatchedSite("site-abc");
    });
    await waitFor(() => expect(sitiosRegistrados()).toContain("site-abc"));

    await act(async () => {
      useSessionStore.getState().signOut();
    });
    const trasSalir = registrar.mock.calls.length;

    // Anónimo: no se registra nada (no hay portador que avale el inmueble).
    await act(async () => {});
    expect(registrar.mock.calls.length).toBe(trasSalir);

    // [T-2.114] Y al volver a entrar NO se presume que la fila del servidor
    // siga bien apuntada: se re-registra. Pero el inmueble YA NO sale del
    // disco —cerrar sesión lo borró, que es justo el arreglo—: sale de `/me`,
    // que devuelve el enrolamiento del portador. Si en su lugar viniera del
    // SecureStore, el siguiente usuario del teléfono heredaría el edificio.
    await act(async () => {
      useSessionStore.getState().setAuthenticated({
        profile: "occupant",
        idToken: "tok",
        me: {
          sub: "ana",
          site_scope: [],
          enrolled_sites: [{ site_id: "site-abc", site_name: "Torre A" }],
        } as unknown as MeResponse,
      });
    });
    await waitFor(() => expect(registrar.mock.calls.length).toBeGreaterThan(trasSalir));
    await waitFor(() => expect(sitiosRegistrados().at(-1)).toBe("site-abc"));
  });
});
