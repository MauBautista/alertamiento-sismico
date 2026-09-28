// [T-9.64 · D-46] LA COSTURA DE LA ESCALA: la consola y la app pintan los sismos
// con UNA sola escala, `shared/fixtures/escala-sismos.json`.
//
// La consola no importa el JSON en producción (la imagen de la consola no copia
// `shared/fixtures`, ver `consoleImageCensus.test.ts`): lleva sus cifras en
// `escalaSismos.ts` y ESTE test las cruza contra la fixture. Si alguien cambia
// un corte o un color en un lado, se pone rojo aquí (y en la suite de la app).
// El redondeo del grado se cruza además contra `gmice.romano` de la nube.

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { COLOR_MMI, TAMANO, colorDeMmi, radioDeMagnitud, romanoDeMmi } from "./escalaSismos";

interface Escala {
  tamano: { desde_mag: number; radio_px: number }[];
  color_mmi: { desde: number; romano: string; color: string }[];
  leyenda: string;
}

const ESCALA = JSON.parse(
  readFileSync(resolve(process.cwd(), "../shared/fixtures/escala-sismos.json"), "utf8"),
) as Escala;

const GMICE = readFileSync(
  resolve(process.cwd(), "../api/src/takab_api/shakemap/gmice.py"),
  "utf8",
).replace(/^\s*#.*$/gm, "");

describe("[T-9.64] la escala de la consola es la de la fixture compartida", () => {
  it("los cortes de tamaño son los de la fixture, en el mismo orden", () => {
    expect(TAMANO).toEqual(ESCALA.tamano.map((t) => ({ desde: t.desde_mag, radio: t.radio_px })));
  });

  it("la paleta MMI es la de la fixture, grado por grado", () => {
    expect(COLOR_MMI).toEqual(
      ESCALA.color_mmi.map((c) => ({ desde: c.desde, romano: c.romano, color: c.color })),
    );
  });

  it("radioDeMagnitud da el radio de cada corte en su borde y dentro", () => {
    for (const t of ESCALA.tamano) {
      expect(radioDeMagnitud(t.desde_mag)).toBe(t.radio_px);
      expect(radioDeMagnitud(t.desde_mag + 0.9)).toBe(t.radio_px);
    }
  });

  it("por debajo de M 4.0 el ◇ no desaparece: se queda en el radio mínimo", () => {
    expect(radioDeMagnitud(3.2)).toBe(ESCALA.tamano[0].radio_px);
    expect(radioDeMagnitud(8.2)).toBe(ESCALA.tamano[ESCALA.tamano.length - 1].radio_px);
  });

  it("colorDeMmi da el color de cada grado de la fixture", () => {
    for (const c of ESCALA.color_mmi) {
      expect(colorDeMmi(c.desde)).toBe(c.color);
      expect(romanoDeMmi(c.desde)).toBe(c.romano);
    }
  });

  it("el grado se REDONDEA al entero más cercano, como gmice.romano (5.5 → VI)", () => {
    expect(GMICE).toMatch(/math\.floor\(mmi \+ 0\.5\)/);
    expect(romanoDeMmi(5.5)).toBe("VI");
    expect(romanoDeMmi(5.49)).toBe("V");
    expect(colorDeMmi(5.5)).toBe("#FFFF00");
    expect(colorDeMmi(4.4)).toBe("#80FFFF");
  });

  it("fuera de rango se acota a I…X, igual que gmice (min(10, max(1, grado)))", () => {
    expect(GMICE).toMatch(/min\(10, max\(1, grado\)\)/);
    expect(romanoDeMmi(0.2)).toBe("I");
    expect(romanoDeMmi(11.7)).toBe("X");
  });

  it("sin MMI estimada no se inventa color", () => {
    expect(colorDeMmi(null)).toBeNull();
    expect(romanoDeMmi(null)).toBeNull();
  });
});
