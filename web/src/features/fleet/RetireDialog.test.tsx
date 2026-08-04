import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import RetireDialog from "./RetireDialog";

function arrange(over: Partial<React.ComponentProps<typeof RetireDialog>> = {}) {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  render(
    <RetireDialog
      kind="gateway"
      label="Torre Norte"
      confirmValue="TKB-0007"
      codeConfigured
      pending={false}
      error={null}
      onCancel={onCancel}
      onConfirm={onConfirm}
      {...over}
    />,
  );
  // El botón de confirmación lleva el sustantivo de lo que se retira; se localiza por
  // exclusión del de cancelar para no acoplar el test al copy exacto.
  const confirmBtn = screen
    .getAllByRole("button")
    .filter((b) => b.textContent !== "CANCELAR" && b.getAttribute("aria-label") !== "Cerrar")
    .at(-1) as HTMLButtonElement;
  return { onConfirm, onCancel, confirmBtn };
}

function fields() {
  return {
    id: screen.getByLabelText(/Escribe el serial/i),
    code: screen.getByLabelText(/Código de retiro del cliente/i),
  };
}

describe("RetireDialog · doble fricción [T-2.36]", () => {
  it("el botón nace deshabilitado", () => {
    const { confirmBtn } = arrange();
    expect(confirmBtn).toBeDisabled();
  });

  it("teclear el identificador SIN código no habilita", () => {
    const { confirmBtn } = arrange();
    fireEvent.change(fields().id, { target: { value: "TKB-0007" } });
    expect(confirmBtn).toBeDisabled();
  });

  it("el código SIN el identificador tampoco habilita", () => {
    const { confirmBtn } = arrange();
    fireEvent.change(fields().code, { target: { value: "SECRETO" } });
    expect(confirmBtn).toBeDisabled();
  });

  it("el identificador se compara EXACTO (mayúsculas incluidas)", () => {
    const { confirmBtn } = arrange();
    fireEvent.change(fields().id, { target: { value: "tkb-0007" } });
    fireEvent.change(fields().code, { target: { value: "SECRETO" } });
    expect(confirmBtn).toBeDisabled();
  });

  it("con los dos factores envía exactamente lo tecleado", () => {
    const { confirmBtn, onConfirm } = arrange();
    fireEvent.change(fields().id, { target: { value: "  TKB-0007  " } });
    fireEvent.change(fields().code, { target: { value: "SECRETO" } });
    expect(confirmBtn).toBeEnabled();
    fireEvent.click(confirmBtn);
    expect(onConfirm).toHaveBeenCalledWith({
      confirmValue: "TKB-0007",
      retireCode: "SECRETO",
    });
  });

  it("el código no se pinta en claro", () => {
    arrange();
    expect(fields().code).toHaveAttribute("type", "password");
    expect(fields().code).toHaveAttribute("autoComplete", "off");
  });

  // Regla de oro 7: prometer un botón que siempre daría 409 es mentir.
  it("sin código configurado avisa y bloquea los campos", () => {
    const { confirmBtn } = arrange({ codeConfigured: false });
    expect(screen.getByTestId("retire-no-code")).toBeInTheDocument();
    expect(fields().id).toBeDisabled();
    expect(fields().code).toBeDisabled();
    expect(confirmBtn).toBeDisabled();
  });

  it("mientras no se sabe si hay código, NO bloquea (el servidor decide)", () => {
    arrange({ codeConfigured: null });
    expect(screen.queryByTestId("retire-no-code")).not.toBeInTheDocument();
    expect(fields().id).toBeEnabled();
  });

  it("el error del servidor se pinta como alerta accionable", () => {
    arrange({ error: "CÓDIGO INCORRECTO · verifica el código de retiro con TAKAB." });
    const alert = screen.getByTestId("retire-error");
    expect(alert).toHaveAttribute("role", "alert");
    expect(alert).toHaveTextContent(/CÓDIGO INCORRECTO/);
  });

  it("CANCELAR no confirma nada", () => {
    const { onCancel, onConfirm } = arrange();
    fireEvent.click(screen.getByRole("button", { name: "CANCELAR" }));
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("mientras retira, ni confirma de nuevo ni deja cancelar a medias", () => {
    const { confirmBtn } = arrange({ pending: true });
    fireEvent.change(fields().id, { target: { value: "TKB-0007" } });
    fireEvent.change(fields().code, { target: { value: "SECRETO" } });
    expect(confirmBtn).toBeDisabled();
    expect(screen.getByRole("button", { name: "CANCELAR" })).toBeDisabled();
  });

  it("el copy de un SITIO advierte que arrastra sus gabinetes", () => {
    arrange({ kind: "site", confirmValue: "TORRE-A" });
    expect(screen.getByTestId("retire-dialog")).toHaveTextContent(
      /se retirarán también TODOS sus gabinetes/i,
    );
    expect(screen.getByLabelText(/Escribe el código/i)).toBeInTheDocument();
  });
});
