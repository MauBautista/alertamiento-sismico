// [T-6.02] Los dos botones del pie de /tenants salían grises y mudos en el estado
// por defecto (sin cambios): `screens.spec.ts` «los apagados dicen por qué»
// fallaba por ellos (U-38). Aquí se fija que cada estado apagado tiene su porqué
// y que el porqué es el correcto, no un texto cualquiera.
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import SyncFooter, { syncFooterTitles, type SyncFooterProps } from "./SyncFooter";

function pintar(over: Partial<SyncFooterProps> = {}) {
  const props: SyncFooterProps = {
    status: "synced",
    syncedFingerprint: null,
    publishedVersion: null,
    changedElsewhere: false,
    dirty: false,
    errors: [],
    applyError: null,
    pending: false,
    canEdit: true,
    onApply: vi.fn(),
    onReset: vi.fn(),
    ...over,
  };
  render(<SyncFooter {...props} />);
  return {
    reset: screen.getByRole("button", { name: /RESTAURAR/ }),
    apply: screen.getByRole("button", { name: /APLICAR Y SINCRONIZAR/ }),
  };
}

describe("SyncFooter · los apagados dicen por qué", () => {
  it("sin cambios: los dos apagados, y cada uno con su razón", () => {
    const { reset, apply } = pintar();
    expect(reset).toBeDisabled();
    expect(reset).toHaveAttribute("title", "Sin cambios que restaurar");
    expect(apply).toBeDisabled();
    expect(apply).toHaveAttribute("title", "Sin cambios que aplicar");
  });

  it("sin permiso de edición el porqué es el gate, no «sin cambios»", () => {
    const { apply } = pintar({ canEdit: false, dirty: true });
    expect(apply).toBeDisabled();
    expect(apply.getAttribute("title")).toMatch(/edit_thresholds/);
  });

  it("con errores de validación el porqué son los errores", () => {
    const { apply } = pintar({ dirty: true, errors: ["PGA fuera de rango"] });
    expect(apply).toBeDisabled();
    expect(apply.getAttribute("title")).toMatch(/Corrige los errores/);
  });

  it("con cambios los dos están vivos y el title dice qué hacen", () => {
    const { reset, apply } = pintar({ dirty: true });
    expect(reset).toBeEnabled();
    expect(reset.getAttribute("title")).toMatch(/Descarta los cambios/);
    expect(apply).toBeEnabled();
    expect(apply.getAttribute("title")).toMatch(/versión nueva/);
  });

  it("mientras aplica, los dos lo dicen", () => {
    const { reset, apply } = pintar({ dirty: true, pending: true });
    expect(reset).toBeDisabled();
    expect(reset.getAttribute("title")).toMatch(/Aplicando/);
    expect(apply).toBeDisabled();
    expect(apply.getAttribute("title")).toMatch(/Aplicando/);
  });

  it("todo estado apagado tiene un porqué de más de tres letras (lo que exige el e2e)", () => {
    for (const canEdit of [true, false])
      for (const dirty of [true, false])
        for (const hasErrors of [true, false])
          for (const pending of [true, false]) {
            const t = syncFooterTitles({ canEdit, dirty, hasErrors, pending });
            expect(t.reset.length).toBeGreaterThan(3);
            expect(t.apply.length).toBeGreaterThan(3);
          }
  });
});
