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
      label: "FUENTE · MISTERIO",
      detail: null,
    });
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
