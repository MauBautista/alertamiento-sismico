// [T-6.32] EL MAPA EN UN PORTÁTIL DE 900 px DE ALTO.
//
// `layout.spec.ts:70` y `smoke.spec.ts:50` exigen que `.soc-stage` pase de 400 px
// —el mapa es la pantalla, y ya se lo comieron tres veces: el simulacro (T-1.62),
// la tira de KPIs (T-2.57) y el aviso de privacidad (T-6.11)—. El bloque de
// alivio que lo protege cortaba en `max-height: 800px`, y ahí estaba el agujero:
// un portátil de 900 px de alto **no recibe nada** de ese alivio y tampoco tiene
// el aire de un 1080. Medido el 2026-09-10 contra `make soc-local`:
//
//   ventana      topbar  KPIs  cola   mapa    ¿alivio?
//   1280×800       52     59    137   438 ✓     sí
//   1440×900       64     77    224   399 ✗     NO
//   1600×900       64     77    224   391 ✗     NO
//   1920×1080      64     48    224   600 ✓     no le hace falta
//
// Falla por UN píxel en 1440×900 y por nueve en 1600×900, que son las dos
// resoluciones de portátil más comunes del mercado. Subido el corte a 1000 px,
// el mapa mide 538 en las dos y 1920×1080 no se mueve.
//
// El valor va LITERAL en el prelude —una custom property no es válida ahí— así
// que la única forma de que el token y la hoja no se desincronicen es cruzarlos,
// exactamente como ya se hace con los tres cortes de ancho.
import { readFileSync } from "node:fs";
import path from "node:path";

import { createRequire } from "node:module";

import { describe, expect, it } from "vitest";

const require_ = createRequire(import.meta.url);
const pkgDir = path.dirname(require_.resolve("@takab/design-tokens/package.json"));
const tokens = JSON.parse(readFileSync(path.join(pkgDir, "tokens.json"), "utf8")) as Record<
  string,
  string
>;
const SOC = readFileSync(path.resolve(process.cwd(), "src", "styles", "soc.css"), "utf8");

/** Los `max-height` que la hoja declara en el prelude de una `@media`. */
function cortesDeAlto(): number[] {
  return [...SOC.matchAll(/@media[^{]*max-height:\s*(\d+)px/g)].map((m) => Number(m[1]));
}

describe("[T-6.32] el corte de ALTO cubre los portátiles de 900 px", () => {
  it("el token existe y trae el valor que la hoja lleva escrito a mano", () => {
    expect(tokens["--tk-bp-alto-corto"]).toBe("1000px");
  });

  it("la hoja declara UN solo corte de alto, y es el del token", () => {
    // Dos cortes de alto distintos serían dos alivios que se pisan: el que gana
    // depende del orden, y eso no se lee en ninguna parte.
    expect(cortesDeAlto()).toEqual([1000]);
  });

  it("ese corte cubre 900 px, que es donde el mapa caía bajo su umbral", () => {
    const corte = Number(tokens["--tk-bp-alto-corto"].replace("px", ""));
    expect(
      corte,
      "un portátil de 900 px se queda sin alivio y el mapa baja de 400",
    ).toBeGreaterThanOrEqual(900);
    // Y no tanto como para robarle el aire al muro: 1080 no puede entrar.
    expect(corte, "a 1080 no le falta alto: meterlo en el alivio sería un rediseño").toBeLessThan(
      1080,
    );
  });

  it("el bloque de alivio sigue haciendo lo que promete: recortar, no reordenar", () => {
    const i = SOC.indexOf("@media (max-height: 1000px) {");
    expect(i, "no está el bloque de alivio de alto").toBeGreaterThan(-1);
    let prof = 0;
    let k = SOC.indexOf("{", i);
    do {
      const c = SOC[k];
      if (c === "{") prof++;
      else if (c === "}") prof--;
      k++;
    } while (prof > 0);
    const cuerpo = SOC.slice(i, k);
    // Recorta paddings y alturas y hace que la tira de KPIs se desplace en vez
    // de partirse. Lo que NO puede hacer es mover nada de sitio.
    expect(cuerpo).toContain("flex-wrap: nowrap");
    expect(cuerpo).toContain("overflow-x: auto");
    expect(cuerpo).not.toMatch(/\bgrid-template-areas\b|\border:\s*\d/);
  });
});
