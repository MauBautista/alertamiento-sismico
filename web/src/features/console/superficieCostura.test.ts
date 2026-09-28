// [T-9.52 · D-44] LA COSTURA DE LA SUPERFICIE: la leyenda de la consola y el PNG
// de la nube tienen que hablar de los MISMOS colores, opacidades y cortes.
//
// El PNG lo pinta `shakemap/raster.py` y la consola sólo lo pega sobre el mapa;
// la leyenda, en cambio, se escribe aquí. Si la nube cambiara el rojo o el corte
// del verde, la leyenda seguiría rotulando lo de antes con toda tranquilidad, y
// ninguna de las dos suites se enteraría: cada una fabrica sus propias cifras.
// Esto las cruza leyendo el código de la nube (patrón `shakemapCostura.test.ts`).

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import {
  ALFA_AJUSTADA,
  ALFA_MODELADA,
  BANDAS_SUPERFICIE,
  CORTE_ROJO_MIN_G,
  CORTE_VERDE_MAX_G,
} from "./superficie";

const API = resolve(process.cwd(), "../api/src/takab_api");

/** Un módulo de la nube SIN comentarios (la prosa cita nombres que no son código). */
function nube(ruta: string): string {
  return readFileSync(resolve(API, ruta), "utf8").replace(/^\s*#.*$/gm, "");
}

const RASTER = nube("shakemap/raster.py");
const SETTINGS = nube("settings.py");

describe("[T-9.52] la leyenda de la superficie y el PNG de la nube dicen lo mismo", () => {
  it("el color de cada banda es el RGB que pinta `raster.py`", () => {
    for (const b of BANDAS_SUPERFICIE) {
      const constante = `BANDA_${b.banda.toUpperCase()}`;
      const m = new RegExp(`${constante}:\\s*\\((\\d+),\\s*(\\d+),\\s*(\\d+)\\)`).exec(RASTER);
      expect(m, `raster.py ya no pinta ${constante}`).not.toBeNull();
      expect(b.rgb, `el ${b.banda} de la leyenda no es el del PNG`).toEqual([
        Number(m![1]),
        Number(m![2]),
        Number(m![3]),
      ]);
    }
  });

  it("la opacidad de cada zona es la del PNG", () => {
    const ajustada = /^ALFA_AJUSTADA\s*=\s*(\d+)/m.exec(RASTER);
    const modelada = /^ALFA_MODELADA\s*=\s*(\d+)/m.exec(RASTER);
    expect(ajustada).not.toBeNull();
    expect(modelada).not.toBeNull();
    expect(ALFA_AJUSTADA).toBeCloseTo(Number(ajustada![1]) / 255, 5);
    expect(ALFA_MODELADA).toBeCloseTo(Number(modelada![1]) / 255, 5);
  });

  it("los cortes rotulados son los defaults del dictamen en `settings.py`", () => {
    // Son los DEFAULTS: el PNG usa los del `rule_set` del sitio, que el snapshot
    // no publica. La leyenda lo declara en pantalla; aquí se asegura al menos
    // que el default que rotula es el de verdad.
    const verde = /dictamen_verde_max_g:\s*float\s*=\s*([\d.]+)/.exec(SETTINGS);
    const rojo = /dictamen_rojo_min_g:\s*float\s*=\s*([\d.]+)/.exec(SETTINGS);
    expect(verde).not.toBeNull();
    expect(rojo).not.toBeNull();
    expect(CORTE_VERDE_MAX_G).toBe(Number(verde![1]));
    expect(CORTE_ROJO_MIN_G).toBe(Number(rojo![1]));
  });
});
