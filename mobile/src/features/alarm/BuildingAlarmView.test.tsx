// [T-2.106] TEST DE HONESTIDAD de la pantalla de ALARMA DEL INMUEBLE.
//
// Assertan el TEXTO QUE LEE LA PERSONA, no la lógica que lo elige, y es
// deliberado: la lección de T-2.104 es que un componente presentacional puede
// llevar una mentira ESCRITA A FUEGO que ninguna prueba de la lógica alcanza
// (`CrisisView` titulaba «ALERTA SÍSMICA SASMEX» para las cuatro fuentes
// mientras `sourceLabel`, bien probado, distinguía las cuatro).
//
// La decisión de producto (2026-08-09): una activación manual es alarma del
// inmueble, NO evacuación sísmica. Así que esta pantalla tiene dos deberes
// negativos tan importantes como los positivos: no decir «alerta sísmica» y no
// ordenar evacuar.
import { render } from "@testing-library/react-native";

import { BuildingAlarmView, horaDeReloj } from "./BuildingAlarmView";

function treeText(component: Awaited<ReturnType<typeof render>>): string {
  return JSON.stringify(component.toJSON());
}

async function renderView(zoneName: string | null = null) {
  return await render(<BuildingAlarmView sinceLabel="14:32" zoneName={zoneName} />);
}

describe("BuildingAlarmView — qué lee la persona", () => {
  it("dice ALARMA DEL INMUEBLE", async () => {
    expect((await renderView()).getByText("ALARMA DEL INMUEBLE")).toBeTruthy();
  });

  it("declara que NO es una alerta sísmica", async () => {
    expect((await renderView()).getByText("NO ES UNA ALERTA SÍSMICA")).toBeTruthy();
  });

  it("NO ordena evacuar (criterio 2 de T-2.106)", async () => {
    const text = treeText(await renderView("P10-A"));
    expect(text).not.toMatch(/EVAC/i); // EVACÚE / EVACUACIÓN / evacuar
    expect(text).not.toMatch(/REPLIÉGUESE/);
    expect(text).not.toMatch(/PROTÉJASE/);
  });

  it("NO se atribuye a SASMEX ni titula como alerta sísmica", async () => {
    const text = treeText(await renderView());
    expect(text).not.toMatch(/SASMEX/);
    expect(text).not.toMatch(/ALERTA SÍSMICA SASMEX/);
    expect(text).not.toMatch(/SISMO/);
  });

  it("NO trae el contador T+ de sismo ni ninguna cuenta regresiva", async () => {
    const text = treeText(await renderView());
    expect(text).not.toMatch(/T\+/);
    expect(text).not.toMatch(/T-[0-9]/);
    expect(text).not.toMatch(/magnitud/i);
  });

  it("remite a la brigada y declara que TAKAB no conoce el motivo", async () => {
    const view = await renderView();
    expect(view.getByText("ATIENDA A SU BRIGADA")).toBeTruthy();
    expect(view.getByText(/indicaciones de su brigada/)).toBeTruthy();
    expect(view.getByText(/no conoce el motivo/)).toBeTruthy();
  });

  it("muestra la HORA DE RELOJ en que se activó, no un cronómetro", async () => {
    const view = await renderView();
    expect(view.getByText("SIRENA ACTIVADA A LAS")).toBeTruthy();
    expect(view.getByText("14:32")).toBeTruthy();
  });

  it("etiqueta el origen como activación manual del inmueble", async () => {
    expect((await renderView()).getByText("ORIGEN · ACTIVACIÓN MANUAL DEL INMUEBLE")).toBeTruthy();
  });

  it("pinta la zona cuando el servidor la trae, y nada cuando no", async () => {
    expect((await renderView("P10-A")).getByText("ZONA P10-A")).toBeTruthy();
    expect((await renderView(null)).queryByText(/^ZONA /)).toBeNull();
  });
});

describe("horaDeReloj", () => {
  it("devuelve HH:MM", () => {
    expect(horaDeReloj("2026-08-10T14:32:00Z")).toMatch(/^[0-9]{2}:[0-9]{2}$/);
  });

  it("una fecha ilegible NO se le muestra a nadie como «Invalid Date»", () => {
    expect(horaDeReloj("no-es-una-fecha")).toBe("--:--");
  });
});
