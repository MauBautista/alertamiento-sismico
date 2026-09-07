// [T-6.19] La franja se deriva de lo que HIZO el gabinete, no de la ventana.
import type { MobileDrillOut } from "@takab/sdk";

import { drillNotice, stripOverlap, TAB_SCREEN_TOP_RESERVE } from "./drillNotice";

function drill(over: Partial<MobileDrillOut> = {}): MobileDrillOut {
  return {
    active: false,
    next_scheduled_at: null,
    last_started_at: null,
    last_note: null,
    execution: "none",
    sites_total: 1,
    sites_executing: 0,
    ...over,
  } as MobileDrillOut;
}

describe("drillNotice · qué dice la franja", () => {
  it("sin simulacro no hay aviso", () => {
    expect(drillNotice(drill())).toBeNull();
  });

  it("EN CURSO sólo cuando el gabinete de ESTE sitio acusó", () => {
    const n = drillNotice(drill({ execution: "executing", active: true, sites_executing: 1 }));
    expect(n?.kind).toBe("executing");
    expect(n?.title).toContain("SIMULACRO EN CURSO");
    expect(n?.title).toContain("ESTO NO ES UNA ALERTA REAL");
    expect(n?.glyph).toBe("volume-2");
  });

  it("[U-01] con el gabinete en `rejected` NO dice EN CURSO: dice por qué", () => {
    // Medido el 2026-09-06: dos gabinetes rechazaron y el teléfono anunció
    // EN CURSO tres minutos. `active` en la nube vieja seguía siendo la ventana.
    const n = drillNotice(drill({ execution: "rejected", active: true }));
    expect(n?.kind).toBe("not_executing");
    expect(n?.title).toBe("SIMULACRO ANUNCIADO — NINGÚN GABINETE LO EJECUTA");
    expect(n?.title).not.toContain("EN CURSO");
    expect(n?.detail).toContain("rechazó");
    expect(n?.glyph).toBe("slash");
  });

  it("dos gabinetes: cuenta cuántos lo ejecutan, y si el suyo no, lo dice", () => {
    const suyoNo = drillNotice(
      drill({ execution: "rejected", sites_total: 3, sites_executing: 1 }),
    );
    expect(suyoNo?.title).toBe("SIMULACRO ANUNCIADO — SU GABINETE NO LO EJECUTA");
    expect(suyoNo?.detail).toBe("1 de 3 gabinetes lo ejecutan · El gabinete rechazó el comando");
    const ninguno = drillNotice(
      drill({ execution: "rejected", sites_total: 2, sites_executing: 0 }),
    );
    expect(ninguno?.title).toBe("SIMULACRO ANUNCIADO — NINGÚN GABINETE LO EJECUTA");
    expect(ninguno?.detail).toContain("0 de 2 gabinetes");
    const enCurso = drillNotice(
      drill({ execution: "executing", sites_total: 2, sites_executing: 2 }),
    );
    expect(enCurso?.detail).toBe("2 de 2 gabinetes lo ejecutan");
  });

  it("pendiente = anunciado y aún sin confirmar; vencido y sin gabinete llevan su razón", () => {
    expect(drillNotice(drill({ execution: "pending" }))).toMatchObject({
      kind: "pending",
      title: "SIMULACRO ANUNCIADO — EL GABINETE AÚN NO CONFIRMA",
      glyph: "clock",
    });
    expect(drillNotice(drill({ execution: "expired" }))?.detail).toContain("venció");
    expect(drillNotice(drill({ execution: "no_gateway" }))?.detail).toContain(
      "no tiene gabinete comandable",
    );
  });

  it("abortado por alerta real: lo dice y manda a seguir la alerta", () => {
    const n = drillNotice(drill({ execution: "aborted" }));
    expect(n?.kind).toBe("aborted");
    expect(n?.title).toContain("ABORTADO");
    expect(n?.title).toContain("ALERTA REAL");
    expect(n?.glyph).toBe("alert-triangle");
  });

  it("un valor futuro que no se reconoce cae en ANUNCIADO, jamás en EN CURSO", () => {
    const n = drillNotice(drill({ execution: "lo-que-sea" as never, active: true }));
    expect(n?.kind).toBe("not_executing");
    expect(n?.title).not.toContain("EN CURSO");
  });

  it("nube anterior a T-6.17 (sin `execution`): cae a `active`", () => {
    const viejo = { active: true, next_scheduled_at: null, last_started_at: null, last_note: null };
    expect(drillNotice(viejo as MobileDrillOut)?.kind).toBe("executing");
    expect(drillNotice({ ...viejo, active: false } as MobileDrillOut)).toBeNull();
  });
});

describe("stripOverlap · la franja solapa la banda que las pestañas reservan", () => {
  it("con inset cero solapa la reserva entera; con inset, lo que sobra; nunca negativo", () => {
    expect(stripOverlap(0)).toBe(TAB_SCREEN_TOP_RESERVE);
    expect(stripOverlap(24)).toBe(TAB_SCREEN_TOP_RESERVE - 24);
    expect(stripOverlap(TAB_SCREEN_TOP_RESERVE + 10)).toBe(0);
    expect(stripOverlap(-5)).toBe(TAB_SCREEN_TOP_RESERVE);
  });
});
