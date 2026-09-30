// [T-9.13] Lo que el teléfono le dice a su dueño cuando NO va a sonar como debe.
import { act, fireEvent, render } from "@testing-library/react-native";

import { AvisoTelefono } from "./AvisoTelefono";

const NO_MOLESTAR = {
  level: "degraded" as const,
  reasons: [
    "Con «No molestar» activado, la alerta sísmica llegará en SILENCIO: permita a TAKAB el acceso a «No molestar».",
  ],
  accion: "permitir_no_molestar" as const,
};

describe("AvisoTelefono", () => {
  it("sin dato todavía, o con el teléfono en orden, no pinta nada", async () => {
    const onAccion = jest.fn();
    const sinDato = await render(<AvisoTelefono alertabilidad={null} onAccion={onAccion} />);
    expect(sinDato.toJSON()).toBeNull();
    const enOrden = await render(
      <AvisoTelefono alertabilidad={{ level: "ok", reasons: [] }} onAccion={onAccion} />,
    );
    expect(enOrden.toJSON()).toBeNull();
  });

  it("sin paso por «No molestar»: lo dice con su motivo y ofrece PERMITIR", async () => {
    const onAccion = jest.fn();
    const v = await render(<AvisoTelefono alertabilidad={NO_MOLESTAR} onAccion={onAccion} />);
    expect(v.getByTestId("aviso-telefono-degraded")).toBeTruthy();
    expect(v.getByText(/llegará en SILENCIO/)).toBeTruthy();
    expect(v.getByText("PERMITIR «NO MOLESTAR»")).toBeTruthy();
    await act(async () => {
      fireEvent.press(v.getByTestId("aviso-telefono-accion"));
    });
    expect(onAccion).toHaveBeenCalledWith("permitir_no_molestar");
  });

  it("notificaciones denegadas: NO RECIBIRÁ ALERTAS, con salida a los ajustes", async () => {
    const onAccion = jest.fn();
    const v = await render(
      <AvisoTelefono
        alertabilidad={{
          level: "blocked",
          reasons: ["Las notificaciones están DENEGADAS en los ajustes del sistema."],
          accion: "abrir_ajustes",
        }}
        onAccion={onAccion}
      />,
    );
    expect(v.getByText("ESTE TELÉFONO NO RECIBIRÁ ALERTAS")).toBeTruthy();
    await act(async () => {
      fireEvent.press(v.getByTestId("aviso-telefono-accion"));
    });
    expect(onAccion).toHaveBeenCalledWith("abrir_ajustes");
  });

  it("un motivo sin arreglo en la mano (iOS sin alerta crítica) se dice, sin botón", async () => {
    const v = await render(
      <AvisoTelefono
        alertabilidad={{ level: "degraded", reasons: ["Sin alerta crítica."] }}
        onAccion={jest.fn()}
      />,
    );
    expect(v.getByText("Sin alerta crítica.")).toBeTruthy();
    expect(v.queryByTestId("aviso-telefono-accion")).toBeNull();
  });
});
