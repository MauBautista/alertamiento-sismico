import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { expect } from "vitest";

/** Los 4 estados obligatorios de todo componente SOC (regla de oro 7). */
export type UiState = "loading" | "error" | "empty" | "stale";

export const UI_STATES: readonly UiState[] = ["loading", "error", "empty", "stale"];

/**
 * Gate de la regla de oro 7: `ui(state)` devuelve el componente con sus datos
 * forzados a ese estado; se exige que el DOM materialice `data-state="<state>"`
 * (lo emite StateFrame). Un componente sin los 4 estados NO pasa a la consola.
 */
export function expectFourStates(ui: (state: UiState) => ReactElement): void {
  for (const state of UI_STATES) {
    const { container, unmount } = render(ui(state));
    expect(
      container.querySelector(`[data-state="${state}"]`),
      `el componente no materializa el estado "${state}"`,
    ).not.toBeNull();
    unmount();
  }
}
