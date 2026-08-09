// UBICACIÓN: este test vive FUERA de `src/app/` a propósito, y no es estilo.
// `expo-router` construye su tabla de rutas con un `require.context` sobre
// `src/app`, que barre TODOS los ficheros de ahí — los `*.test.tsx` incluidos.
// Con este archivo dentro, el bundle arrastraba `@testing-library/react-native`
// → `console` de Node, que no existe en el runtime de React Native, y la app
// NO ARRANCABA. Estuvo así desde el 2026-08-08 sin que nadie lo viera: la suite
// de móvil corre jest, tsc y eslint, y ninguno construye un bundle.
// Lo vigila ahora el gate `expo export` del job `mobile` en CI.
//
// Ninguna pantalla del onboarding puede dejar a alguien sin sesión y EN SILENCIO.
//
// [T-2.79.b] `app/index.tsx:34` era el ÚNICO punto de la app que reaccionaba a
// quedarse anónimo, y el stack de `app/onboarding/` no lo tiene montado: era un
// `Stack` pelado, sin guarda. Un `signOut()` disparado durante el onboarding
// —hoy un 401, mañana otro— dejaba a la persona EN LA PANTALLA, sin token y sin
// aviso: nadie la llevaba al login. Para un occupant es una trampa cerrada:
// canjear el código de sitio exige sesión viva, así que nunca termina el
// onboarding y por tanto nunca llega al check-in de vida ni al botón de pánico
// (reglas de oro 1 y 2).
//
// **La lista de pantallas se DERIVA del directorio del stack**, no se enumera:
// expo-router enruta por ficheros, así que el contenido de esta carpeta ES el
// stack. Una pantalla nueva mañana queda cubierta sin que nadie se acuerde de
// añadirla a una lista — que es exactamente la clase de olvido que produjo este
// fallo.
//
// Se moquean solo las FRONTERAS (expo-router, almacén seguro, notificaciones,
// SDK): las pantallas y la guarda corren de verdad.
import { act, render } from "@testing-library/react-native";
import type { ComponentType, ReactNode } from "react";

import { useSessionStore } from "@/auth/session.store";

import OnboardingLayout, { OnboardingSessionGuard } from "@/app/onboarding/_layout";

declare const __dirname: string;

jest.mock("expo-router", () => {
  const React = jest.requireActual("react") as typeof import("react");
  const { Text } = jest.requireActual("react-native") as typeof import("react-native");
  return {
    Redirect: ({ href }: { href: string }) =>
      React.createElement(Text, { testID: "redirect" }, String(href)),
    Stack: ({ children }: { children?: ReactNode }) =>
      React.createElement(React.Fragment, null, children),
    useRouter: () => ({ push: jest.fn(), replace: jest.fn(), back: jest.fn() }),
  };
});

jest.mock("expo-secure-store", () => ({
  getItemAsync: jest.fn(async () => null),
  setItemAsync: jest.fn(async () => undefined),
  deleteItemAsync: jest.fn(async () => undefined),
}));

jest.mock("expo-notifications", () => ({
  getPermissionsAsync: jest.fn(async () => ({
    granted: true,
    canAskAgain: true,
    status: "granted",
  })),
  requestPermissionsAsync: jest.fn(async () => ({
    granted: true,
    canAskAgain: true,
    status: "granted",
  })),
  setNotificationChannelAsync: jest.fn(async () => undefined),
  getDevicePushTokenAsync: jest.fn(async () => ({ data: "tok" })),
  AndroidImportance: { MAX: 5, DEFAULT: 3 },
  AndroidNotificationVisibility: { PUBLIC: 1 },
}));

jest.mock("@takab/sdk", () => ({
  client: {
    get: jest.fn(async () => ({ error: { detail: "sin red" }, response: { status: 503 } })),
    post: jest.fn(async () => ({ error: { detail: "sin red" }, response: { status: 503 } })),
  },
  enrollMeEnrollmentPost: jest.fn(async () => ({
    error: { detail: "sin red" },
    response: { status: 503 },
  })),
  registerPushTokenMePushTokensPost: jest.fn(async () => ({ data: {} })),
}));

type EntradaDir = { name: string; isDirectory: () => boolean };
type FsMinimo = {
  readdirSync: (dir: string, opts: { withFileTypes: true }) => EntradaDir[];
};

const fs = jest.requireActual("fs") as FsMinimo;

/** Las pantallas del stack, LEÍDAS del directorio de rutas (no enumeradas).
 * Se descartan `_layout`/`_*` (no son rutas), los tests y todo lo que no sea
 * un módulo de ruta. Los subdirectorios también cuelgan de este layout. */
function pantallasDelStack(dir: string, prefijo = ""): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entrada) => {
    if (entrada.isDirectory()) {
      return pantallasDelStack(`${dir}/${entrada.name}`, `${prefijo}${entrada.name}/`);
    }
    if (!/\.tsx?$/.test(entrada.name)) {
      return [];
    }
    if (entrada.name.startsWith("_") || /\.(test|spec)\.tsx?$/.test(entrada.name)) {
      return [];
    }
    return [`${prefijo}${entrada.name}`];
  });
}

/** El directorio REAL del stack, que ya no es el de este archivo.
 *
 * Se declara UNA vez y lo usan las dos mitades —listar las pantallas y
 * cargarlas—, porque si se separan, una puede quedarse mirando a un directorio
 * vacío y el `it.each` pasaría por vacuidad: cero casos, cero fallos, verde. */
const DIR_STACK = "../../../src/app/onboarding";
const PANTALLAS = pantallasDelStack(`${__dirname}/${DIR_STACK}`);

function cargarPantalla(archivo: string): ComponentType {
  const modulo = jest.requireActual(`${DIR_STACK}/${archivo}`) as { default: ComponentType };
  return modulo.default;
}

async function autenticar(): Promise<void> {
  await act(async () => {
    useSessionStore.getState().setAuthenticated({ profile: "occupant", idToken: "tok", me: null });
  });
}

afterEach(async () => {
  await act(async () => {
    useSessionStore.setState({
      status: "booting",
      profile: null,
      idToken: null,
      me: null,
      deniedReason: null,
    });
  });
});

describe("el stack de onboarding se DERIVA del directorio, no de una lista", () => {
  it("hay pantallas que cubrir y todas exportan un componente", () => {
    // Si el filtro se rompiera y devolviera [], `it.each` no correría NADA y el
    // fichero saldría verde sin haber probado una sola pantalla.
    expect(PANTALLAS.length).toBeGreaterThanOrEqual(3);
    for (const archivo of PANTALLAS) {
      expect(typeof cargarPantalla(archivo)).toBe("function");
    }
  });

  it("`_layout` y los tests NO se cuentan como pantallas", () => {
    expect(PANTALLAS).not.toContain("_layout.tsx");
    expect(PANTALLAS.some((p) => p.includes(".test."))).toBe(false);
  });
});

describe("quedarse anónimo dentro del onboarding lleva al login", () => {
  it.each(PANTALLAS)("%s: signOut() ⇒ redirección a /login", async (archivo) => {
    const Pantalla = cargarPantalla(archivo);
    await autenticar();

    const v = await render(
      <OnboardingSessionGuard>
        <Pantalla />
      </OnboardingSessionGuard>,
    );
    // Con sesión viva la pantalla se ve: la guarda no estorba el camino normal.
    expect(v.queryByTestId("redirect")).toBeNull();

    await act(async () => {
      useSessionStore.getState().signOut();
    });

    expect(v.getByTestId("redirect").props.children).toBe("/login");
  });

  it.each(PANTALLAS)("%s: el gate negado ⇒ /denied, no un limbo", async (archivo) => {
    const Pantalla = cargarPantalla(archivo);
    await autenticar();

    const v = await render(
      <OnboardingSessionGuard>
        <Pantalla />
      </OnboardingSessionGuard>,
    );

    await act(async () => {
      useSessionStore.getState().setDenied("role_not_mobile");
    });

    expect(v.getByTestId("redirect").props.children).toBe("/denied");
  });
});

describe("la guarda vive en el _layout — por eso cubre a las que aún no existen", () => {
  it("el layout del stack redirige al login si la sesión está muerta", async () => {
    await act(async () => {
      useSessionStore.getState().signOut();
    });

    const v = await render(<OnboardingLayout />);

    expect(v.getByTestId("redirect").props.children).toBe("/login");
  });

  it("con sesión viva el layout monta el stack (no redirige)", async () => {
    await autenticar();

    const v = await render(<OnboardingLayout />);

    expect(v.queryByTestId("redirect")).toBeNull();
  });

  it("arrancando (`booting`) NO expulsa: sesión desconocida ≠ sesión muerta", async () => {
    // Redirigir al login mientras el bootstrap lee el almacén seguro echaría a
    // gente con sesión válida en cada arranque en frío.
    const v = await render(<OnboardingLayout />);

    expect(v.queryByTestId("redirect")).toBeNull();
  });
});
