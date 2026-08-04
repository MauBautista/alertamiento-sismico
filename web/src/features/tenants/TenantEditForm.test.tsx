import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { TenantOut } from "@takab/sdk";

import TenantEditForm from "./TenantEditForm";

function tenant(over: Partial<TenantOut> = {}): TenantOut {
  return {
    tenant_id: "t-1",
    code: "TKB-001",
    name: "Industrias del Valle",
    isolation_mode: "logical",
    vertical: "Industrial",
    visibility: "private",
    status: "active",
    plan_code: "mvp",
    row_version: "774100",
    created_at: "2026-01-01T00:00:00Z",
    ...over,
  };
}

function setup(over: Partial<TenantOut> = {}) {
  const onSubmit = vi.fn();
  const onCancel = vi.fn();
  render(
    <TenantEditForm
      tenant={tenant(over)}
      pending={false}
      error={null}
      onSubmit={onSubmit}
      onCancel={onCancel}
    />,
  );
  return { onSubmit, onCancel };
}

describe("TenantEditForm · PATCH parcial con testigo de concurrencia", () => {
  it("sin cambios, GUARDAR está deshabilitado (un PATCH vacío es 422)", () => {
    setup();
    expect(screen.getByRole("button", { name: "GUARDAR FICHA" }).hasAttribute("disabled")).toBe(
      true,
    );
  });

  it("manda SOLO los campos tocados, más el base_row_version", () => {
    const { onSubmit } = setup();
    fireEvent.change(screen.getByLabelText("Nombre"), { target: { value: "Nuevo Nombre" } });
    fireEvent.click(screen.getByRole("button", { name: "GUARDAR FICHA" }));
    expect(onSubmit).toHaveBeenCalledWith({ name: "Nuevo Nombre", base_row_version: "774100" });
  });

  it("vaciar la vertical la manda como null explícito, no como cadena vacía", () => {
    const { onSubmit } = setup();
    fireEvent.change(screen.getByLabelText("Vertical (opcional)"), { target: { value: "  " } });
    fireEvent.click(screen.getByRole("button", { name: "GUARDAR FICHA" }));
    expect(onSubmit).toHaveBeenCalledWith({ vertical: null, base_row_version: "774100" });
  });

  it("el nombre vacío bloquea el guardado (no se manda un 422 seguro)", () => {
    setup();
    fireEvent.change(screen.getByLabelText("Nombre"), { target: { value: "   " } });
    expect(screen.getByRole("button", { name: "GUARDAR FICHA" }).hasAttribute("disabled")).toBe(
      true,
    );
  });

  it("NO ofrece editar el `code` ni el modo de aislamiento", () => {
    setup();
    // `code` es la llave que vive en runbooks y en el edge.env de los gabinetes;
    // `isolation_mode` es una migración de datos, no una casilla.
    expect(screen.queryByLabelText(/Código/i)).toBeNull();
    expect(screen.queryByLabelText(/Aislamiento/i)).toBeNull();
  });

  it("NO ofrece mover el cliente ni tocar su tenant_id", () => {
    setup();
    expect(screen.queryByLabelText(/tenant/i)).toBeNull();
  });
});

describe("TenantEditForm · los dos cambios con consecuencia se advierten", () => {
  it("pasar a gov_shared avisa de que amplía QUIÉN lee los datos", () => {
    setup();
    expect(screen.queryByTestId("gov-shared-warning")).toBeNull();
    fireEvent.change(screen.getByLabelText("Visibilidad"), { target: { value: "gov_shared" } });
    expect(screen.getByTestId("gov-shared-warning").textContent).toMatch(/gov_operator/);
  });

  it("un cliente que YA es gov_shared no repite el aviso", () => {
    setup({ visibility: "gov_shared" });
    expect(screen.queryByTestId("gov-shared-warning")).toBeNull();
  });

  it("suspender aclara que NO deja al edificio sin protección (regla de oro 2)", () => {
    setup();
    fireEvent.change(screen.getByLabelText("Estado del servicio"), {
      target: { value: "suspended" },
    });
    expect(screen.getByTestId("suspended-warning").textContent).toMatch(/sin nube/);
  });
});

describe("TenantEditForm · errores del servidor", () => {
  it("el 409 se muestra literal, no se traga", () => {
    render(
      <TenantEditForm
        tenant={tenant()}
        pending={false}
        error="CONFLICTO · otro administrador guardó este cliente mientras editabas."
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByRole("alert").textContent).toMatch(/CONFLICTO/);
  });

  it("mientras guarda, los dos botones quedan bloqueados", () => {
    render(
      <TenantEditForm
        tenant={tenant()}
        pending
        error={null}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: "GUARDANDO…" }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByRole("button", { name: "CANCELAR" }).hasAttribute("disabled")).toBe(true);
  });
});
