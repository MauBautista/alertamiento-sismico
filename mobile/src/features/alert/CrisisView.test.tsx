// TESTS DE HONESTIDAD de las pantallas 1.2/1.3 (spec §2.1-A / §10): con
// source sasmex_wr1 la pantalla JAMÁS contiene magnitud ni ETA; el contador
// es ascendente (T+); el hueco de ETA no se renderiza con el flag en false.
import { render } from "@testing-library/react-native";

import { CrisisView } from "./CrisisView";
import { sourceLabel } from "./source";

const SASMEX = sourceLabel({ trigger: "sasmex", max_pga_g: null, node_count: null });

function treeText(component: Awaited<ReturnType<typeof render>>): string {
  return JSON.stringify(component.toJSON());
}

describe("CrisisView — honestidad §2.1-A", () => {
  it("sasmex: SIN magnitud, SIN ETA, SIN cuenta regresiva (test que FALLA si aparecen)", async () => {
    const view = await render(
      <CrisisView elapsedS={4} policy="evacuate" source={SASMEX} zoneName={null} />,
    );
    const text = treeText(view);
    expect(text).not.toMatch(/magnitud/i);
    expect(text).not.toMatch(/M ?[0-9]+(\.[0-9])?/); // "M 6.8" y variantes
    expect(text).not.toMatch(/T-[0-9]/); // cronómetro regresivo
    expect(text).not.toMatch(/llegada|arribo|epicentro/i); // ETA/epicentro fabricados
    expect(view.getByText(/T\+04s/)).toBeTruthy(); // ascendente, dato real
    expect(view.getByText(/SASMEX WR-1/)).toBeTruthy();
  });

  it("el hueco de ETA NO se renderiza (ALERT_SOURCE_CARRIES_ETA=false)", async () => {
    const view = await render(
      <CrisisView elapsedS={10} policy="evacuate" source={SASMEX} zoneName={null} />,
    );
    expect(view.queryByTestId("eta-slot")).toBeNull();
  });

  it("política evacuate ⇒ EVACÚE AHORA (1.2)", async () => {
    const view = await render(
      <CrisisView elapsedS={4} policy="evacuate" source={SASMEX} zoneName="P02" />,
    );
    expect(view.getByText(/EVACÚE/)).toBeTruthy();
    expect(view.getByText(/No use elevadores/)).toBeTruthy();
    expect(view.getByText(/ZONA P02/)).toBeTruthy();
  });

  it("política shelter ⇒ REPLIÉGUESE (1.3)", async () => {
    const view = await render(
      <CrisisView elapsedS={4} policy="shelter" source={SASMEX} zoneName="P10-A" />,
    );
    expect(view.getByText("REPLIÉGUESE")).toBeTruthy();
    expect(view.getByText(/ventanas y cristales/)).toBeTruthy();
  });

  it("sin política de zona ⇒ PROTÉJASE (banner MVP) — el teléfono no adivina", async () => {
    const view = await render(
      <CrisisView elapsedS={4} policy={null} source={SASMEX} zoneName={null} />,
    );
    expect(view.getByText("PROTÉJASE")).toBeTruthy();
    expect(view.queryByText(/EVACÚE/)).toBeNull();
    expect(view.queryByText("REPLIÉGUESE")).toBeNull();
  });

  it("fuente quórum: estaciones corroborantes (dato real de red)", async () => {
    const quorum = sourceLabel({ trigger: "quorum", max_pga_g: null, node_count: 3 });
    const view = await render(
      <CrisisView elapsedS={70} policy="evacuate" source={quorum} zoneName={null} />,
    );
    expect(view.getByText(/CONFIRMADO · 3 ESTACIONES/)).toBeTruthy();
    expect(view.getByText(/T\+1m10s/)).toBeTruthy();
  });

  it("fuente local: PGA instrumental MEDIDO, jamás magnitud", async () => {
    const local = sourceLabel({ trigger: "local_threshold", max_pga_g: 0.15, node_count: null });
    const view = await render(
      <CrisisView elapsedS={9} policy="shelter" source={local} zoneName={null} />,
    );
    expect(view.getByText(/PGA 0\.15g MEDIDO/)).toBeTruthy();
    expect(treeText(view)).not.toMatch(/magnitud/i);
  });
});
