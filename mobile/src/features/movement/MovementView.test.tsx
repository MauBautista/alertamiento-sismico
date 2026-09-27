// [T-9.11 · D-39] MOVIMIENTO EN EL INMUEBLE — la vista presentacional.
//
// Lo que se asserta es el TEXTO que lee la brigada: que no se confunda con una
// alerta sísmica oficial, que diga qué hacer (verificar y reportar daños), y que
// los datos del incidente se pinten solo si existen (un PGA inventado es un dato
// falso, §2.1-A).
import { fireEvent, render } from "@testing-library/react-native";
import { Text } from "react-native";

import { MovementView, etiquetaPga, haceCuanto } from "./MovementView";

describe("[T-9.11] MovementView", () => {
  it("titular y deslinde: NO es una alerta sísmica oficial", async () => {
    const v = await render(
      <MovementView abiertoLabel="hace 2 min" onReportarDanos={jest.fn()} pgaLabel={null} />,
    );
    expect(v.getByText("MOVIMIENTO EN EL INMUEBLE")).toBeTruthy();
    expect(
      v.getByText(
        "Se detectó un movimiento en el inmueble. No es una alerta sísmica oficial: verifique el inmueble y reporte daños.",
      ),
    ).toBeTruthy();
    expect(v.getByText("hace 2 min")).toBeTruthy();
  });

  it("sin PGA no se pinta ninguna cifra", async () => {
    const v = await render(
      <MovementView abiertoLabel="hace segundos" onReportarDanos={jest.fn()} pgaLabel={null} />,
    );
    expect(v.queryByTestId("movimiento-pga")).toBeNull();
  });

  it("con PGA se pinta", async () => {
    const v = await render(
      <MovementView abiertoLabel="hace segundos" onReportarDanos={jest.fn()} pgaLabel="0.012 g" />,
    );
    expect(v.getByTestId("movimiento-pga")).toHaveTextContent(/0\.012 g/);
  });

  it("REPORTAR DAÑOS llama a su acción", async () => {
    const onReportar = jest.fn();
    const v = await render(
      <MovementView abiertoLabel="hace 1 min" onReportarDanos={onReportar} pgaLabel={null} />,
    );
    fireEvent.press(v.getByTestId("movimiento-reportar"));
    expect(onReportar).toHaveBeenCalledTimes(1);
  });

  it("sin permiso de reportar, el botón no se pinta (server-driven)", async () => {
    const v = await render(
      <MovementView abiertoLabel="hace 1 min" onReportarDanos={null} pgaLabel={null} />,
    );
    expect(v.queryByTestId("movimiento-reportar")).toBeNull();
  });

  it("el hueco del acuse se pinta tal cual", async () => {
    const v = await render(
      <MovementView
        abiertoLabel="hace 1 min"
        onReportarDanos={null}
        pgaLabel={null}
        slotAcuse={<Text>ACUSE</Text>}
      />,
    );
    expect(v.getByText("ACUSE")).toBeTruthy();
  });
});

describe("[T-9.11] etiquetas del incidente", () => {
  it("haceCuanto: relativo y jamás negativo; fecha ilegible ⇒ guion", () => {
    const ahora = Date.parse("2026-09-27T12:10:00Z");
    expect(haceCuanto("2026-09-27T12:05:00Z", ahora)).toBe("hace 5 min");
    expect(haceCuanto("2026-09-27T12:20:00Z", ahora)).toBe("hace segundos");
    expect(haceCuanto("no-es-fecha", ahora)).toBe("—");
  });

  it("etiquetaPga: null ⇒ null; número ⇒ g con tres decimales", () => {
    expect(etiquetaPga(null)).toBeNull();
    expect(etiquetaPga(undefined)).toBeNull();
    expect(etiquetaPga(0.01234)).toBe("0.012 g");
    expect(etiquetaPga(Number.NaN)).toBeNull();
  });

  // [T-9.11 · D-39] La nube manda `building_alarm` TAMBIÉN durante el movimiento
  // (solo a la brigada). Sin este bloque, una alarma de pánico quedaba OCULTA
  // detrás de la pantalla del movimiento.
  it("con alarma del inmueble activa: bloque destacado y botón a la alarma", async () => {
    const abrir = jest.fn();
    const v = await render(
      <MovementView
        abiertoLabel="hace 2 min"
        onAbrirAlarma={abrir}
        onReportarDanos={null}
        pgaLabel={null}
      />,
    );
    expect(v.getByText("ALARMA DEL INMUEBLE ACTIVA")).toBeTruthy();
    fireEvent.press(v.getByTestId("movimiento-alarma"));
    expect(abrir).toHaveBeenCalledTimes(1);
  });

  it("sin alarma del inmueble no se pinta el bloque", async () => {
    const v = await render(
      <MovementView abiertoLabel="hace 2 min" onReportarDanos={null} pgaLabel={null} />,
    );
    expect(v.queryByText("ALARMA DEL INMUEBLE ACTIVA")).toBeNull();
    expect(v.queryByTestId("movimiento-alarma")).toBeNull();
  });
});
