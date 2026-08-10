import { formatPga, sourceLabel } from "./source";

describe("sourceLabel — solo datos reales (§2.1-A)", () => {
  it("sasmex: booleano del WR-1 — SIN magnitud, SIN ETA, SIN números", () => {
    const s = sourceLabel({ trigger: "sasmex", max_pga_g: 0.15, node_count: 4 });
    expect(s.label).toBe("FUENTE · SASMEX WR-1");
    // aunque existan otros datos en el payload, la fuente SASMEX no los porta;
    // el único dígito permitido es el del nombre del receptor ("WR-1")
    expect(s.detail).toBeNull();
    expect(JSON.stringify(s).replace(/WR-1/g, "")).not.toMatch(/[0-9]/);
  });

  it("detección local: PGA instrumental medido (o nada, jamás inventado)", () => {
    expect(
      sourceLabel({ trigger: "local_threshold", max_pga_g: 0.15, node_count: null }).detail,
    ).toBe("PGA 0.15g MEDIDO");
    expect(
      sourceLabel({ trigger: "local_threshold", max_pga_g: null, node_count: null }).detail,
    ).toBeNull();
  });

  it("quórum: estaciones corroborantes (mismo dato que el Triage)", () => {
    expect(sourceLabel({ trigger: "quorum", max_pga_g: null, node_count: 3 }).detail).toBe(
      "CONFIRMADO · 3 ESTACIONES",
    );
    expect(
      sourceLabel({ trigger: "quorum", max_pga_g: null, node_count: null }).detail,
    ).toBeNull();
  });

  it("trigger desconocido ⇒ crudo en mayúsculas, sin adornos", () => {
    expect(sourceLabel({ trigger: "misterio", max_pga_g: null, node_count: null })).toEqual({
      title: "ALERTA SÍSMICA",
      eyebrow: "● ALERTA SÍSMICA ACTIVA",
      label: "FUENTE · MISTERIO",
      detail: null,
    });
  });
});

// [T-2.104] EL TITULAR ES UNA ATRIBUCIÓN, y sólo una fuente puede llevarse el
// nombre del servicio oficial.
//
// `CrisisView` lo tenía escrito a fuego como «ALERTA SÍSMICA SASMEX` para las
// CUATRO fuentes. Medido el 2026-08-09 en un Pixel 8 Pro: moviendo el sensor con
// la mano, la app tituló «ALERTA SÍSMICA SASMEX» —el texto más grande de la
// pantalla— mientras la píldora de abajo decía, correctamente, «FUENTE · REGLAS
// LOCALES». SASMEX no había dicho nada.
//
// Por qué es grave y no cosmético: TAKAB **recibe** la alerta oficial, no la
// genera, y el documento de entrega deslinda expresamente sus falsos positivos.
// Atribuirle una detección propia invierte el deslinde — el día que el umbral
// local se dispare de más, el ocupante culpa a SASMEX. Y choca con T-2.32, que
// degradó la detección de una sola estación a AVISO precisamente porque una
// estación sola no es autoridad.
describe("sourceLabel · el titular no le atribuye a SASMEX lo que no dijo", () => {
  const de = (trigger: string) =>
    sourceLabel({ trigger, max_pga_g: null, node_count: null });

  it("SOLO el contacto seco del WR-1 titula con el nombre del servicio oficial", () => {
    expect(de("sasmex").title).toBe("ALERTA SÍSMICA SASMEX");
    for (const trigger of ["local_threshold", "quorum", "manual", "misterio"]) {
      expect(de(trigger).title).not.toMatch(/SASMEX/);
    }
  });

  it("la detección propia dice que es propia, y el cuórum que es de la red", () => {
    expect(de("local_threshold").title).toBe("SISMO DETECTADO EN ESTE EDIFICIO");
    expect(de("quorum").title).toBe("SISMO CONFIRMADO POR LA RED");
  });

  it("una activación manual NO se anuncia como alerta sísmica", () => {
    expect(de("manual").title).toBe("ALERTA ACTIVADA MANUALMENTE");
    expect(de("manual").eyebrow).not.toMatch(/SÍSMICA/);
    // Y las que sí lo son, lo siguen diciendo.
    expect(de("sasmex").eyebrow).toMatch(/SÍSMICA/);
    expect(de("local_threshold").eyebrow).toMatch(/SÍSMICA/);
  });
});

describe("formatPga — honesto con el piso MEMS", () => {
  it("valores de sacudida real en g", () => {
    expect(formatPga(0.15)).toBe("0.15g");
    expect(formatPga(0.01)).toBe("0.01g");
  });

  it("piso de ruido en mg (0.6-1.1 mg calibrado)", () => {
    expect(formatPga(0.0008)).toBe("0.8mg");
  });
});
