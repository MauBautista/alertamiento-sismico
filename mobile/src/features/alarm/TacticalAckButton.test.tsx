// [T-2.147.b · D-05] TEST DE HONESTIDAD del acuse de la brigada.
//
// Mismo criterio que `BuildingAlarmView.test.tsx`: se asserta **el texto que lee la
// persona**, no la lógica que lo elige. Aquí importa el doble, porque este botón vive
// en el camino de emergencia y la forma barata de equivocarse es prometer con
// palabras algo que el botón no hace — que es exactamente el defecto de `T-2.104`,
// pero en un control en vez de en un titular.
import { fireEvent, render } from "@testing-library/react-native";

import { TacticalAckButton } from "./TacticalAckButton";

type Vista = Awaited<ReturnType<typeof render>>;

function texto(component: Vista): string {
  return JSON.stringify(component.toJSON());
}

/** `render` es asíncrono en este árbol (React 19 + RNTL): sin `await`, `c` es una
 *  promesa y `getByTestId` no existe — y el fallo se lee como «el testID no está»,
 *  que manda a buscar el defecto al sitio equivocado. */
async function ver(
  props: Partial<Parameters<typeof TacticalAckButton>[0]> = {},
): Promise<Vista> {
  return await render(
    <TacticalAckButton acusadoALas={null} estado="idle" onPress={() => {}} visible {...props} />,
  );
}

describe("TacticalAckButton — qué ve y qué NO ve la persona", () => {
  it("un ocupante no lo ve siquiera", async () => {
    const c = await ver({ visible: false });
    expect(c.toJSON()).toBeNull();
  });

  it("un táctico lo ve y puede pulsarlo", async () => {
    const onPress = jest.fn();
    const c = await ver({ onPress });
    fireEvent.press(c.getByTestId("tactical-ack"));
    expect(onPress).toHaveBeenCalledTimes(1);
  });

  // El deber NEGATIVO, y es el que hace que este control sea honesto: acusar no
  // silencia la sirena (eso es `siren_silence`, otro permiso y otro camino) ni
  // resuelve el incidente (eso es `ack_incident`, y es del SOC).
  it("NO promete silenciar la sirena ni resolver nada", async () => {
    const t = texto(await ver());
    expect(t).toMatch(/No silencia la sirena/);
    expect(t).not.toMatch(/SILENCIAR/i);
    expect(t).not.toMatch(/APAGAR/i);
    expect(t).not.toMatch(/RESOLVER|RESUELTO/i);
    expect(t).not.toMatch(/EVAC/i);
  });

  it("mientras envía no se puede volver a pulsar", async () => {
    const onPress = jest.fn();
    const c = await ver({ estado: "enviando", onPress });
    fireEvent.press(c.getByTestId("tactical-ack"));
    expect(onPress).not.toHaveBeenCalled();
  });

  it("acusado: lo confirma con la hora y RECUERDA que la sirena sigue", async () => {
    const c = await ver({ acusadoALas: "14:35", estado: "acusado" });
    expect(c.getByTestId("tactical-ack-hecho")).toBeTruthy();
    expect(texto(c)).toMatch(/14:35/);
    expect(texto(c)).toMatch(/sigue sonando/);
    // Ya no hay nada que pulsar: el estado es terminal para este teléfono.
    expect(c.queryByTestId("tactical-ack")).toBeNull();
  });

  it("un fallo se DECLARA y deja reintentar, jamás se traga", async () => {
    // Un acuse perdido en silencio haría creer a quien lo pulsó que ya avisó,
    // mientras el SOC escala igual a los ~2 min: la peor combinación posible.
    const c = await ver({ estado: "error" });
    expect(c.getByTestId("tactical-ack-error")).toBeTruthy();
    expect(c.getByTestId("tactical-ack")).toBeTruthy();
  });
});
