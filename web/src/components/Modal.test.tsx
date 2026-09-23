import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import Modal from "./Modal";

describe("Modal (T-1.51)", () => {
  it("dialog accesible: role, aria-modal, título y foco inicial dentro", () => {
    render(
      <Modal title="REUBICAR EPICENTRO" onClose={vi.fn()}>
        <p>contenido</p>
      </Modal>,
    );
    const dialog = screen.getByRole("dialog", { name: "REUBICAR EPICENTRO" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveFocus();
    expect(screen.getByText("contenido")).toBeInTheDocument();
  });

  it("Esc y el botón Cerrar despachan onClose", () => {
    const onClose = vi.fn();
    render(
      <Modal title="X" onClose={onClose}>
        <p>c</p>
      </Modal>,
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Cerrar" }));
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  // [A-013 · T-8.07] El Modal le ROBABA el foco al campo cada segundo en
  // /console: el foco inicial vivía en un efecto con `[onClose]` y el wall se
  // redibuja cada 1 s pasando `onClose` como flecha nueva. Cada tic, el cursor
  // saltaba de LAT/LON, de la nota o de la fecha del simulacro al contenedor.
  it("un re-render del padre con otro onClose NO le quita el foco al campo", () => {
    function Padre({ tic }: { tic: number }) {
      // Flecha NUEVA en cada render, igual que `ConsoleWall` con su `useNow(1000)`.
      return (
        <Modal title="REUBICAR EPICENTRO" onClose={() => void tic}>
          <label>
            NOTA
            <input aria-label="NOTA" />
          </label>
        </Modal>
      );
    }
    const { rerender } = render(<Padre tic={0} />);
    const campo = screen.getByRole("textbox", { name: "NOTA" });
    campo.focus();
    expect(campo).toHaveFocus();
    rerender(<Padre tic={1} />);
    rerender(<Padre tic={2} />);
    expect(campo).toHaveFocus();
  });

  it("Esc llama al onClose VIGENTE, no al del primer render", () => {
    const primero = vi.fn();
    const segundo = vi.fn();
    const { rerender } = render(
      <Modal title="X" onClose={primero}>
        <p>c</p>
      </Modal>,
    );
    rerender(
      <Modal title="X" onClose={segundo}>
        <p>c</p>
      </Modal>,
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(primero).not.toHaveBeenCalled();
    expect(segundo).toHaveBeenCalledTimes(1);
  });

  it("footer opcional se renderiza cuando se da", () => {
    render(
      <Modal title="X" onClose={vi.fn()} footer={<button>OK</button>}>
        <p>c</p>
      </Modal>,
    );
    expect(screen.getByRole("button", { name: "OK" })).toBeInTheDocument();
  });
});
