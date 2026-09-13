// [T-7.29] La franja de alerta viva: sin ella, salir de la toma de crisis
// sería indistinguible de que el sismo terminó.
import { fireEvent, render } from "@testing-library/react-native";

import { AlertaVivaStrip } from "./AlertaVivaStrip";

describe("AlertaVivaStrip", () => {
  it("sin alerta no ocupa ni un píxel", async () => {
    const { queryByTestId } = await render(
      <AlertaVivaStrip onVolver={() => {}} visible={false} />,
    );
    expect(queryByTestId("alerta-viva")).toBeNull();
  });

  it("con alerta lo DICE y ofrece volver a la instrucción", async () => {
    const volver = jest.fn();
    const { getByTestId, getByText } = await render(
      <AlertaVivaStrip onVolver={volver} visible />,
    );
    expect(getByText("ALERTA SÍSMICA ACTIVA")).toBeTruthy();
    fireEvent.press(getByTestId("alerta-viva"));
    expect(volver).toHaveBeenCalledTimes(1);
  });

  it("la franja ENTERA es el control táctil, no un enlace dentro", async () => {
    // T-6.20: Android ignora el `hitSlop` de un control nativo, así que el
    // objetivo es la fila. Se afirma sobre el estilo porque es lo que se pinta.
    const { getByTestId } = await render(
      <AlertaVivaStrip onVolver={() => {}} visible />,
    );
    const estilo = getByTestId("alerta-viva").props.style;
    const plano = Array.isArray(estilo)
      ? Object.assign({}, ...estilo.flat())
      : estilo;
    expect(plano.minHeight).toBeGreaterThanOrEqual(48);
  });
});
