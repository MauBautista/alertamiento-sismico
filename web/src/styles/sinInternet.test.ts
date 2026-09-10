// [T-6.15] LA CONSOLA NO PIDE SU FUENTE A INTERNET.
//
// El hallazgo que abrió la ficha era «dos familias desde Google Fonts». La
// medición encontró algo peor y más silencioso: los dos `@import
// url(https://fonts.googleapis.com/…)` estaban escritos DESPUÉS del `@font-face`
// de Geist, y un `@import` sólo es válido al principio de la hoja. Así que no es
// que la consola dependiera de internet para su fuente del dato — es que **nunca
// la tuvo**. Medido el 2026-09-10 contra `make soc-local`:
//
//   · cero peticiones a `fonts.googleapis.com` o `fonts.gstatic.com`;
//   · `document.fonts` con una sola cara cargada, Geist;
//   · el bundle de producción sin un solo `@import` ni la cadena `googleapis`;
//   · y el ancho de «0123456789 ·» a 700 28px medía lo MISMO pidiendo
//     `'JetBrains Mono'` que pidiendo `'Saira Condensed'` (156.34 px las dos):
//     el sustituto del sistema, no la familia. Con la fuente alojada pasa a
//     204 px, que es la métrica de JetBrains Mono de verdad.
//
// Por eso este censo no vigila «que no haya CDNs»: vigila que **la familia que
// la hoja declara sea una que la hoja pueda entregar**.
import { readFileSync, existsSync, readdirSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const CSS_DIR = path.resolve(process.cwd(), "src", "styles");

function hojas(): Array<{ nombre: string; css: string; crudo: string }> {
  return readdirSync(CSS_DIR)
    .filter((f) => f.endsWith(".css"))
    .map((f) => {
      const crudo = readFileSync(path.join(CSS_DIR, f), "utf8");
      return { nombre: f, crudo, css: crudo.replace(/\/\*[\s\S]*?\*\//g, "") };
    });
}

describe("[T-6.15] ninguna hoja de la consola sale a la red", () => {
  it("el barrido encuentra hojas (si esto falla, el resto miente)", () => {
    expect(hojas().length).toBeGreaterThan(3);
  });

  it("cero hosts externos: ni fuentes, ni iconos, ni hojas de terceros", () => {
    const fugas: string[] = [];
    for (const { nombre, css } of hojas()) {
      css.split("\n").forEach((linea, i) => {
        for (const m of linea.matchAll(/url\(\s*['"]?(https?:)?\/\/[^)'"]+/g)) {
          fugas.push(`${nombre}:${i + 1} → ${m[0].slice(0, 70)}`);
        }
      });
    }
    expect(fugas, "un SOC con salida restringida perdería esto sin previo aviso").toEqual([]);
  });

  it("y ningún `@import` — el que había estaba mal colocado y era letra muerta", () => {
    // La regla del navegador: `@import` sólo vale antes de cualquier otra regla
    // (salvo `@charset` y `@layer`). Aquí no se permite ninguno: las fuentes se
    // declaran con `@font-face` en su sitio y las hojas se ordenan en `main.tsx`.
    const restos = hojas()
      .filter(({ css }) => /@import\b/.test(css))
      .map(({ nombre }) => nombre);
    expect(restos).toEqual([]);
  });
});

describe("[T-6.15] las dos familias que la consola pinta las ENTREGA la consola", () => {
  /** `@font-face` de la hoja, con su familia y los ficheros que cita. */
  function caras(): Array<{ familia: string; ficheros: string[] }> {
    const out: Array<{ familia: string; ficheros: string[] }> = [];
    for (const { css } of hojas()) {
      for (const m of css.matchAll(/@font-face\s*\{([^}]*)\}/g)) {
        const familia = /font-family:\s*['"]([^'"]+)['"]/.exec(m[1])?.[1];
        if (familia === undefined) continue;
        out.push({
          familia,
          ficheros: [...m[1].matchAll(/url\(\s*['"]?([^)'"]+)/g)].map((u) => u[1]),
        });
      }
    }
    return out;
  }

  it.each([
    ["Geist", "la fuente de la interfaz"],
    ["JetBrains Mono", "la fuente del DATO"],
  ])("`%s` (%s) tiene su `@font-face` en la hoja", (familia) => {
    expect(caras().map((c) => c.familia)).toContain(familia);
  });

  it("todo fichero que una cara cita EXISTE en disco", () => {
    const ausentes = caras()
      .flatMap((c) => c.ficheros)
      .filter((f) => !existsSync(path.join(CSS_DIR, f)));
    expect(ausentes).toEqual([]);
  });

  it("la fuente del dato es VARIABLE de 100 a 800: los 700 del KPI no se sintetizan", () => {
    // Sintetizar la negrita engorda los trazos sin cambiar los avances: en una
    // columna de cifras se nota, y es justo donde vive el dato de esta consola.
    const jb = hojas()
      .flatMap(({ css }) => [...css.matchAll(/@font-face\s*\{([^}]*)\}/g)].map((m) => m[1]))
      .filter((b) => /font-family:\s*['"]JetBrains Mono['"]/.test(b));
    expect(jb.length).toBeGreaterThan(0);
    for (const b of jb) {
      expect(b).toMatch(/font-weight:\s*100 800/);
      expect(b).toMatch(/format\(\s*['"]woff2-variations['"]\s*\)/);
    }
  });

  it("la licencia de la fuente VIAJA con ella (SIL OFL 1.1 lo exige)", () => {
    const ofl = path.join(CSS_DIR, "fonts", "OFL-JetBrainsMono.txt");
    expect(existsSync(ofl), "falta `fonts/OFL-JetBrainsMono.txt`").toBe(true);
    expect(readFileSync(ofl, "utf8")).toContain("SIL OPEN FONT LICENSE Version 1.1");
  });
});
