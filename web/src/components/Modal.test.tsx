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

  it("footer opcional se renderiza cuando se da", () => {
    render(
      <Modal title="X" onClose={vi.fn()} footer={<button>OK</button>}>
        <p>c</p>
      </Modal>,
    );
    expect(screen.getByRole("button", { name: "OK" })).toBeInTheDocument();
  });
});
