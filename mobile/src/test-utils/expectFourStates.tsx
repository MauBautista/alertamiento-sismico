// [T-2.111] EL EQUIVALENTE MÓVIL DE `expectFourStates` (regla de oro 7).
//
// Espejo de `web/src/test-utils/states.ts`, adaptado a React Native: aquí no
// hay DOM ni `data-state`, así que la señal es el `testID` que materializa
// `@/ui/StateFrame` — `state-loading`, `state-error`, `state-empty`,
// `state-stale`.
//
// DIFERENCIA DE FONDO CON LA CONSOLA. En web el componente recibe sus datos
// por props y forzar un estado es pasar otras props. En móvil las pantallas
// leen de HOOKS (`useAlertState`, `useQuery`, `useWatchedSiteId`), así que el
// estado se fuerza desde los mocks: por eso el `ui(estado)` de aquí puede
// preparar sus mocks antes de devolver el elemento, y por eso hay que dejar
// asentar los efectos antes de mirar el árbol.
//
// LO QUE SE EXIGE, Y POR QUÉ ES MÁS QUE «existe el testID»: se comprueba
// también que los otros tres estados NO estén presentes. Un marco que pintara
// a la vez el spinner y el contenido sería exactamente la mentira que la regla
// de oro 7 persigue («mostrar un dato congelado como si fuera live»), y la
// presencia a secas no la caza.
//
// LIMITACIÓN DECLARADA: la exclusión mutua vale para una pantalla con UN
// `StateFrame`. Una pantalla con varios marcos hermanos (p. ej. `panel.tsx`)
// tiene que probarse marco a marco, renderizando el subárbol de cada uno.
import { act, render } from "@testing-library/react-native";
import type { ReactElement } from "react";

/** Los 4 estados obligatorios de todo componente (regla de oro 7). */
export type UiState = "loading" | "error" | "empty" | "stale";

export const UI_STATES: readonly UiState[] = ["loading", "error", "empty", "stale"];

/** El `testID` con el que `StateFrame` materializa cada estado. */
export function testIdDeEstado(estado: UiState): string {
  return `state-${estado}`;
}

export interface OpcionesCuatroEstados {
  /**
   * Deja asentar efectos y microtareas tras montar (react-query, SecureStore…).
   * Por defecto un `act` vacío, que basta para el ciclo de efectos.
   */
  asentar?: () => Promise<void>;
}

/**
 * Gate de la regla de oro 7 para pantallas móviles: `ui(estado)` prepara los
 * mocks de ese estado y devuelve la pantalla; se exige que el árbol renderice
 * `state-<estado>` y NINGUNO de los otros tres.
 *
 * Una pantalla que no materialice los cuatro no pasa: el fallo dice cuál falta
 * y qué se pintó en su lugar.
 */
export async function expectFourStates(
  ui: (estado: UiState) => ReactElement,
  opciones: OpcionesCuatroEstados = {},
): Promise<void> {
  for (const estado of UI_STATES) {
    const v = await render(ui(estado));
    if (opciones.asentar) {
      await opciones.asentar();
    } else {
      await act(async () => {});
    }

    const presentes = UI_STATES.filter((e) => v.queryAllByTestId(testIdDeEstado(e)).length > 0);
    const arbol = v.toJSON();
    // TRAMPA de RNTL 14 (la misma que documenta `ackTracking.test.tsx`):
    // `unmount` es ASÍNCRONO. Sin `await`, su `act()` queda abierto, el
    // `render` de la vuelta siguiente cae dentro de ese act huérfano y produce
    // un ÁRBOL VACÍO — sin error ni aviso. Un gate que fallara así acusaría a
    // la pantalla de no declarar un estado que sí declara.
    await v.unmount();

    if (!presentes.includes(estado)) {
      throw new Error(
        `la pantalla no materializa el estado "${estado}": no hay ningún ` +
          `\`testID="${testIdDeEstado(estado)}"\` en el árbol. ` +
          `Estados presentes: ${presentes.length > 0 ? presentes.join(", ") : "ninguno"}. ` +
          "Cúbrelo con `@/ui/StateFrame` cableando sus cuatro entradas " +
          `(loading, error, empty, staleSinceMs).\n${JSON.stringify(arbol)?.slice(0, 900)}`,
      );
    }
    const intrusos = presentes.filter((e) => e !== estado);
    if (intrusos.length > 0) {
      throw new Error(
        `forzada al estado "${estado}", la pantalla pinta ADEMÁS ${intrusos.join(", ")}. ` +
          "Los cuatro estados son excluyentes: la precedencia la resuelve un solo " +
          "`StateFrame` (loading > error > empty > contenido+stale). Si la pantalla " +
          "tiene varios marcos hermanos, pruébalos uno a uno.",
      );
    }
  }
}
