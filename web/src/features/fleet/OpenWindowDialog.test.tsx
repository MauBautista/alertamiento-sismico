import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import OpenWindowDialog, { DURACIONES } from "./OpenWindowDialog";

function arrange(over: Partial<React.ComponentProps<typeof OpenWindowDialog>> = {}) {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  render(
    <OpenWindowDialog
      error={null}
      gatewayId="gw-1"
      label="Torre Norte"
      onCancel={onCancel}
      onConfirm={onConfirm}
      pending={false}
      {...over}
    />,
  );
  return { onConfirm, onCancel };
}

describe("OpenWindowDialog — abrir una ventana de mantenimiento", () => {
  it("sin motivo NO se puede abrir", () => {
    // El motivo no es burocracia: es lo único que separa «silencio con dueño» de
    // «silencio que nadie recuerda haber pedido», y es la fila que alguien leerá
    // cuando pregunte por qué no sonó la alarma.
    arrange();
    expect(screen.getByTestId("open-window-confirm")).toBeDisabled();
  });

  it("un motivo de solo espacios tampoco vale", () => {
    const { onConfirm } = arrange();
    fireEvent.change(screen.getByTestId("open-window-reason"), { target: { value: "   " } });
    expect(screen.getByTestId("open-window-confirm")).toBeDisabled();
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("con motivo abre, y manda el gabinete y la duración elegida", () => {
    const { onConfirm } = arrange();
    fireEvent.change(screen.getByTestId("open-window-reason"), {
      target: { value: "  cambio de UPS  " },
    });
    fireEvent.change(screen.getByTestId("open-window-duration"), {
      target: { value: String(DURACIONES[2].s) },
    });
    fireEvent.click(screen.getByTestId("open-window-confirm"));
    expect(onConfirm).toHaveBeenCalledWith({
      gateway_id: "gw-1",
      reason: "cambio de UPS", // recortado: el espacio no es motivo
      duration_s: DURACIONES[2].s,
    });
  });

  it("dice QUÉ se silencia, con el nombre del inmueble delante", () => {
    arrange();
    expect(screen.getByTestId("open-window-target")).toHaveTextContent("Torre Norte");
  });

  // El deber NEGATIVO, y es el que evita las dos lecturas equivocadas de golpe:
  // quien crea que esto desarma el edificio no abrirá una ventana nunca; quien crea
  // lo contrario dejará un edificio pensando que está callado cuando sigue protegido.
  it("declara que la protección del edificio NO se toca", () => {
    arrange();
    const t = screen.getByTestId("open-window-keeps").textContent ?? "";
    expect(t).toMatch(/SASMEX→sirena/);
    expect(t).toMatch(/NO se toca/);
    expect(t).toMatch(/OPERACIÓN/);
  });

  it("mientras abre no se puede volver a pulsar", () => {
    const { onConfirm } = arrange({ pending: true });
    fireEvent.change(screen.getByTestId("open-window-reason"), { target: { value: "x" } });
    expect(screen.getByTestId("open-window-confirm")).toBeDisabled();
    fireEvent.click(screen.getByTestId("open-window-confirm"));
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("un fallo del servidor se muestra, no se traga", () => {
    arrange({ error: "la ventana no se abrió (HTTP 403)" });
    expect(screen.getByTestId("open-window-error")).toHaveTextContent("HTTP 403");
  });

  it("cancelar no abre nada", () => {
    const { onCancel, onConfirm } = arrange();
    fireEvent.click(screen.getByTestId("open-window-cancel"));
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();
  });
});
