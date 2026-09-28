// [T-9.52 · D-44] La superficie ESTIMADA en la consola: lo que se pinta, lo que
// se declara y cómo se rotula. Todo puro: el PNG lo pinta la nube, aquí sólo se
// decide si se puede enseñar y qué hay que decir al lado.

import { describe, expect, it } from "vitest";

import type { PuntoProps, ShakemapOut, SuperficieOut } from "@takab/sdk";

import {
  ALFA_AJUSTADA,
  ALFA_MODELADA,
  BANDAS_SUPERFICIE,
  CORTE_ROJO_MIN_G,
  CORTE_VERDE_MAX_G,
  esquinasDeBbox,
  rotuloEstimado,
  textoDelPunto,
  vistaSuperficie,
  type PngSuperficie,
} from "./superficie";

const SUP: SuperficieOut = {
  bbox: [-99.4, 19.1, -98.9, 19.6],
  ancho: 50,
  alto: 50,
  n_sensores: 4,
  n_calibrados: 3,
  escala_km: 30,
  ley: "ATTEN-LAW v1",
  metodo: "residuos-gaussianos-v1",
  cita_mmi: "Wald et al. (1999), relación PGA–MMI",
  pga_max_g: 0.083,
  mmi_max_estimada: 6.1,
  png: "/incidents/i-1/shakemap/superficie.png",
  verde_max_g: null,
  rojo_min_g: null,
};

function mapa(over: Partial<ShakemapOut> = {}): ShakemapOut {
  return {
    incident_id: "i-1",
    estado: "completo",
    calculado_en: "2026-09-14T10:41:30Z",
    ley: "ATTEN-LAW v1",
    cobertura_km: 25,
    epicentro: null,
    fuera_de_alcance: [],
    observado: { type: "FeatureCollection", features: [] },
    modelado: null,
    superficie: SUP,
    superficie_motivo: null,
    superficie_motivo_texto: null,
    ...over,
  };
}

const LISTO: PngSuperficie = { url: "blob:x/1", cargando: false, error: false };

describe("esquinasDeBbox · el orden de MapLibre", () => {
  it("[oeste, sur, este, norte] ⇒ arriba-izq, arriba-der, abajo-der, abajo-izq", () => {
    expect(esquinasDeBbox([-99.4, 19.1, -98.9, 19.6])).toEqual([
      [-99.4, 19.6],
      [-98.9, 19.6],
      [-98.9, 19.1],
      [-99.4, 19.1],
    ]);
  });

  it("un bbox que no es un rectángulo legible NO se pinta", () => {
    // Pintar un PNG sobre esquinas invertidas lo voltea: el rojo de un lado
    // acabaría del otro, y nada en pantalla lo delataría.
    expect(esquinasDeBbox([-98.9, 19.1, -99.4, 19.6])).toBeNull();
    expect(esquinasDeBbox([-99.4, 19.6, -98.9, 19.1])).toBeNull();
    expect(esquinasDeBbox([-99.4, 19.1, -98.9])).toBeNull();
    expect(esquinasDeBbox([-99.4, 19.1, Number.NaN, 19.6])).toBeNull();
    expect(esquinasDeBbox([-199, 19.1, -98.9, 19.6])).toBeNull();
  });
});

describe("la leyenda de la superficie", () => {
  it("se rotula ESTIMADO, con sus sensores, y la MMI como estimada y no observada", () => {
    expect(rotuloEstimado(SUP)).toBe(
      "ESTIMADO a partir de 4 sensores (3 calibrados) · MMI estimada (Wald 1999), no observada",
    );
    expect(rotuloEstimado({ ...SUP, n_sensores: 1, n_calibrados: 1 })).toBe(
      "ESTIMADO a partir de 1 sensor (1 calibrado) · MMI estimada (Wald 1999), no observada",
    );
  });

  it("las tres bandas son las de la nube, con los cortes por defecto del dictamen", () => {
    expect(CORTE_VERDE_MAX_G).toBe(0.04);
    expect(CORTE_ROJO_MIN_G).toBe(0.1);
    expect(BANDAS_SUPERFICIE.map((b) => b.banda)).toEqual(["rojo", "amarillo", "verde"]);
    expect(BANDAS_SUPERFICIE.map((b) => b.rotulo)).toEqual(["≥ 0.10 g", "0.04–0.10 g", "< 0.04 g"]);
    // La opacidad es la ZONA, y la ajustada se ve más que la modelada.
    expect(ALFA_AJUSTADA).toBeGreaterThan(ALFA_MODELADA);
  });
});

describe("vistaSuperficie · qué se pinta y qué se DECLARA (regla de oro 7)", () => {
  it("con superficie y PNG listo: se pinta, sobre las esquinas del bbox", () => {
    const v = vistaSuperficie(mapa(), LISTO, false);
    expect(v.pinta).toBe(true);
    expect(v.url).toBe("blob:x/1");
    expect(v.esquinas?.[0]).toEqual([-99.4, 19.6]);
    expect(v.superficie).toBe(SUP);
    expect(v.nota).toBeNull();
  });

  it("mientras el PNG carga NO se pinta nada, y se dice", () => {
    const v = vistaSuperficie(mapa(), { url: null, cargando: true, error: false }, false);
    expect(v.pinta).toBe(false);
    expect(v.url).toBeNull();
    expect(v.notaTestId).toBe("superficie-cargando");
  });

  it("si el PNG falla se dice, y no se confunde con «no hay superficie»", () => {
    const v = vistaSuperficie(mapa(), { url: null, cargando: false, error: true }, false);
    expect(v.pinta).toBe(false);
    expect(v.notaTestId).toBe("superficie-error");
    expect(v.nota).toMatch(/NO DISPONIBLE/);
  });

  it("sin superficie, la nota es el MOTIVO que da la nube", () => {
    const v = vistaSuperficie(
      mapa({
        superficie: null,
        superficie_motivo: "sin_epicentro",
        superficie_motivo_texto: "no hay epicentro con magnitud: sin él no hay ley que corregir",
      }),
      { url: null, cargando: false, error: false },
      false,
    );
    expect(v.pinta).toBe(false);
    expect(v.superficie).toBeNull();
    expect(v.notaTestId).toBe("superficie-motivo");
    expect(v.nota).toBe(
      "SIN SUPERFICIE ESTIMADA · no hay epicentro con magnitud: sin él no hay ley que corregir",
    );
  });

  it("un motivo que la nube no sabe decir en frase se cita tal cual", () => {
    const v = vistaSuperficie(
      mapa({ superficie: null, superficie_motivo: "raro", superficie_motivo_texto: null }),
      { url: null, cargando: false, error: false },
      false,
    );
    expect(v.nota).toBe("SIN SUPERFICIE ESTIMADA · MOTIVO «raro»");
  });

  it("sin superficie NI motivo (snapshot anterior a D-44) también se dice", () => {
    const v = vistaSuperficie(
      mapa({ superficie: null }),
      { url: null, cargando: false, error: false },
      false,
    );
    expect(v.notaTestId).toBe("superficie-motivo");
    expect(v.nota).toBe("SIN SUPERFICIE ESTIMADA EN ESTE SNAPSHOT");
  });

  it("con el snapshot en error, pendiente, ilegible o ausente, la superficie calla", () => {
    // Esos estados ya los declara la nota del mapa de la sacudida: una segunda
    // nota diciendo «sin superficie» atribuiría la ausencia a otra causa.
    expect(vistaSuperficie(mapa(), LISTO, true)).toMatchObject({ pinta: false, nota: null });
    expect(vistaSuperficie(mapa({ estado: "pendiente" }), LISTO, false)).toMatchObject({
      pinta: false,
      nota: null,
    });
    expect(vistaSuperficie(mapa({ estado: "otro" }), LISTO, false)).toMatchObject({
      pinta: false,
      nota: null,
    });
    expect(vistaSuperficie(undefined, LISTO, false)).toMatchObject({ pinta: false, nota: null });
  });

  it("un bbox ilegible no se pinta y se declara", () => {
    const v = vistaSuperficie(mapa({ superficie: { ...SUP, bbox: [1, 2, 3] } }), LISTO, false);
    expect(v.pinta).toBe(false);
    expect(v.notaTestId).toBe("superficie-bbox");
  });
});

describe("textoDelPunto · la MMI de un punto es SIEMPRE «estimada»", () => {
  const P: PuntoProps = {
    site_id: "s-1",
    site_code: "site-cholula-a",
    site_name: "Cholula A",
    procedencia: "measured",
    pga_g: 0.083,
    pgv_cms: 2.1,
    dist_km: 120,
    hypo_km: 129,
    pga_g_modelada: 0.041,
    residuo_log10: 0.306,
    medido_en: "2026-09-14T10:00:35Z",
    voto_contado: true,
    mmi_estimada: 6.1,
    mmi_romano: "VI",
  };

  it("nombre, medida y MMI estimada con su cita", () => {
    expect(textoDelPunto(P)).toBe(
      "Cholula A · 0.083 g · ×2.0 · MMI ESTIMADA VI (6.1) · Wald 1999 · NO OBSERVADA",
    );
  });

  it("sin MMI estimada se dice, sin inventar un grado", () => {
    expect(textoDelPunto({ ...P, mmi_estimada: null, mmi_romano: null })).toBe(
      "Cholula A · 0.083 g · ×2.0 · MMI ESTIMADA: SIN VALOR",
    );
  });

  it("jamás «INTENSIDAD MMI» ni una MMI sin «ESTIMADA» detrás", () => {
    for (const t of [textoDelPunto(P), textoDelPunto({ ...P, mmi_estimada: null })]) {
      expect(t).not.toMatch(/INTENSIDAD MMI/i);
      expect(t).not.toMatch(/MMI(?! ESTIMADA)/);
    }
  });
});
