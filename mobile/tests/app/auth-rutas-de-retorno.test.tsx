// UBICACIÓN: fuera de `src/app/` a propósito — `expo-router` barre TODO lo que
// hay bajo `src/app` con un `require.context`, los `*.test.tsx` incluidos, y la
// app deja de compilar. Misma nota que `onboarding/guard.test.tsx`.
//
// [T-8.11 · A-021] TODO DEEP LINK DE RETORNO DE LA HOSTED UI TIENE SU RUTA.
//
// En ANDROID, `expo-web-browser` no intercepta el redirect de la Hosted UI: su
// polyfill escucha `Linking` y el intent `takab://auth/<algo>` le llega TAMBIÉN
// a expo-router como una navegación. Sin un fichero en `src/app` para ese
// camino, Android pinta la pantalla por defecto de expo-router —«Unmatched
// Route», en inglés—. Pasó con `takab://auth/callback` (por eso existe
// `app/auth/callback.tsx`) y volvió a pasar con `takab://auth/logout` en cuanto
// CERRAR SESIÓN de la Cuenta pasó a llamar a `logout()`: el paso 3 abre el
// `/logout` de la Hosted UI con `logout_uri=takab://auth/logout`, Cognito
// redirige ahí, y la ruta no existía. En la demostración, con un solo Pixel, se
// cierra sesión para pasar de ocupante a táctico.
//
// Ningún test lo cazaba: el de la Cuenta moquea `@/auth/logout`, y los
// recorridos de Maestro no pulsan CERRAR SESIÓN a propósito.
//
// La lista de deep links se DERIVA de `auth/config.ts` (toda constante que
// empiece por el `scheme` de `app.json`), no se enumera: un tercer retorno
// mañana queda cubierto sin que nadie se acuerde de añadirlo aquí.
/// <reference types="node" />
import { render } from "@testing-library/react-native";
import { existsSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import type { ComponentType } from "react";

import * as authConfig from "@/auth/config";

jest.mock("expo-router", () => {
  const { Text } = jest.requireActual("react-native") as typeof import("react-native");
  return {
    Redirect: (p: { href: string }) => <Text testID="redirect">{p.href}</Text>,
    useRouter: () => ({ replace: jest.fn(), push: jest.fn(), back: jest.fn() }),
    useLocalSearchParams: () => ({}),
  };
});

const MOBILE = resolve(__dirname, "..", "..");
const APP = join(MOBILE, "src", "app");

const scheme = (
  JSON.parse(readFileSync(join(MOBILE, "app.json"), "utf8")) as { expo: { scheme: string } }
).expo.scheme;

/** `takab://auth/logout?x=1` → `auth/logout`. */
function caminoDe(uri: string): string {
  return uri.slice(`${scheme}://`.length).split(/[?#]/)[0].replace(/\/+$/, "");
}

/** Los ficheros que expo-router acepta para un camino sin grupos ni parámetros. */
function ficherosDe(camino: string): string[] {
  return [".tsx", ".ts", ".jsx", ".js"].flatMap((ext) => [
    join(APP, `${camino}${ext}`),
    join(APP, camino, `index${ext}`),
  ]);
}

const RETORNOS: string[] = Object.values(authConfig).filter(
  (v): v is string => typeof v === "string" && v.startsWith(`${scheme}://`),
);

describe("deep links de retorno de la Hosted UI", () => {
  it("se derivan de auth/config.ts y no están vacíos (callback y logout, al menos)", () => {
    expect(scheme).toBe("takab");
    expect(RETORNOS).toEqual(
      expect.arrayContaining([authConfig.REDIRECT_URI, authConfig.LOGOUT_URI]),
    );
  });

  it.each(RETORNOS)("%s tiene su ruta en src/app (si no, Android pinta «Unmatched Route»)", (uri) => {
    const camino = caminoDe(uri);
    const existentes = ficherosDe(camino).filter((f) => existsSync(f));
    expect({ uri, ruta: existentes.map((f) => f.slice(MOBILE.length + 1)) }).toEqual({
      uri,
      ruta: [expect.stringContaining(camino)],
    });
  });
});

describe("app/auth/logout", () => {
  it("devuelve a la puerta de entrada, que reenruta por el estado de la sesión", async () => {
    const fichero = ficherosDe(caminoDe(authConfig.LOGOUT_URI)).find((f) => existsSync(f));
    expect(fichero).toBeDefined();
    // Carga dinámica: sin la ruta, este test falla con un mensaje legible en
    // vez de tumbar la suite entera por un import que no resuelve.
    const Ruta = jest.requireActual<{ default: ComponentType }>(fichero as string).default;
    const { getByTestId } = await render(<Ruta />);
    expect(getByTestId("redirect").props.children).toBe("/");
  });
});
