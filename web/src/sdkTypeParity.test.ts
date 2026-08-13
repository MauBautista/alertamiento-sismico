// [T-2.82.b] Guardia DERIVADA: ninguna superficie declara a mano la forma de
// una respuesta que el SDK ya publica.
//
// El defecto que cierra: cuatro sitios (`ComplianceDeclared`, `useComplianceLabels`,
// `usePrivacyConsent` y `mobile/services/privacy`) escribieron a mano el tipo de una
// respuesta «mientras el SDK se regenera». El SDK se regeneró el 2026-08-08 y los
// tipos a mano siguieron ahí — que es el estado peligroso, porque un tipo a mano es
// una SEGUNDA VERDAD sobre el mismo cable y las dos pueden divergir en silencio. Ya
// pasó: la consola afirmaba que `provenance` siempre viene y el contrato publicado
// decía que podía faltar. La consola tenía razón, y aun así el problema no era quién
// acertaba: era que hubiera dos.
//
// Por qué DERIVADA y no una lista de cuatro nombres: la lista de hoy no impide el
// quinto de mañana. Aquí se cruza el CONJUNTO COMPLETO de tipos objeto declarados en
// `web/src` y `mobile/src` contra el CONJUNTO COMPLETO de tipos de
// `shared/sdk-ts/src/gen/types.gen.ts`, por FIRMA (el juego de nombres de campo).
// Cualquier duplicado nuevo sale por aquí, se llame como se llame — es la misma
// forma de guardia que sacó sola la deuda de tokens de `soc.css` en T-2.64.d.
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const RAIZ = path.resolve(process.cwd(), "..");
const TIPOS_GEN = path.join(RAIZ, "shared", "sdk-ts", "src", "gen", "types.gen.ts");

/**
 * Umbral MEDIDO, no elegido a ojo: por debajo de 3 campos la coincidencia
 * estructural deja de ser evidencia de duplicación y pasa a ser casualidad. A 2
 * campos este mismo barrido señala `MultiChannelStripProps ≡ MultiChannelFeatures`
 * —unas props de componente contra un tipo de datos, que no comparten cable
 * ninguno—, y un falso positivo en una guardia es lo que enseña a la gente a
 * añadir excepciones.
 */
const CAMPOS_MINIMOS = 3;

/** Nombre de campo de cada línea `  foo?: T;` de un cuerpo de tipo objeto. */
function campos(cuerpo: string, sangria: number): string[] {
  const limpio = cuerpo.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*/g, "");
  const re = new RegExp(String.raw`^\s{${sangria}}'?([a-zA-Z_]\w*)'?\??:`, "gm");
  return [...limpio.matchAll(re)].map((m) => m[1]).sort();
}

/** Firma → nombres generados que la tienen. */
function firmasGeneradas(): Map<string, string[]> {
  const src = readFileSync(TIPOS_GEN, "utf8");
  const out = new Map<string, string[]>();
  for (const m of src.matchAll(/export type (\w+) = \{([^}]*)\};/g)) {
    const c = campos(m[2], 4);
    if (c.length < CAMPOS_MINIMOS) continue;
    const firma = c.join("|");
    out.set(firma, [...(out.get(firma) ?? []), m[1]]);
  }
  return out;
}

/** Tipos objeto declarados a mano en una superficie (`interface X {}` / `type X = {}`). */
function tiposLocales(src: string): { nombre: string; firma: string }[] {
  const out: { nombre: string; firma: string }[] = [];
  for (const m of src.matchAll(/export (?:interface (\w+) \{|type (\w+) = \{)([\s\S]*?)\n\}/g)) {
    const c = campos(m[3], 2);
    if (c.length < CAMPOS_MINIMOS) continue;
    out.push({ nombre: m[1] ?? m[2], firma: c.join("|") });
  }
  return out;
}

function fuentes(base: string): string[] {
  const out: string[] = [];
  const walk = (dir: string): void => {
    for (const e of readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, e.name);
      if (e.isDirectory()) {
        if (e.name !== "node_modules") walk(p);
        continue;
      }
      // Los tests declaran fixtures a su antojo: lo que se vigila es lo que se
      // ENVÍA A PRODUCCIÓN. Un fixture tipado contra el SDK es justamente la
      // forma correcta de anclarlo, y ahí no hay segunda verdad que cerrar.
      if (/\.tsx?$/.test(e.name) && !/\.test\./.test(e.name)) out.push(p);
    }
  };
  walk(base);
  return out;
}

const SUPERFICIES = ["web/src", "mobile/src"];

function duplicados(): string[] {
  const generadas = firmasGeneradas();
  const out: string[] = [];
  for (const base of SUPERFICIES) {
    for (const file of fuentes(path.join(RAIZ, base))) {
      for (const { nombre, firma } of tiposLocales(readFileSync(file, "utf8"))) {
        const gemelos = generadas.get(firma);
        if (gemelos !== undefined) {
          out.push(`${path.relative(RAIZ, file)}: ${nombre} ≡ ${gemelos.join(" / ")}`);
        }
      }
    }
  }
  return out.sort();
}

describe("[T-2.82.b] ninguna superficie redeclara un tipo que el SDK ya publica", () => {
  it("el barrido encuentra fuentes y contrato (si esto falla, el resto miente)", () => {
    // Sin esta guarda, una ruta mal resuelta daría cero duplicados y el test
    // pasaría en verde sin mirar nada — la forma exacta en que una red deja de
    // ser una red.
    expect(firmasGeneradas().size).toBeGreaterThan(50);
    for (const base of SUPERFICIES) {
      expect(fuentes(path.join(RAIZ, base)).length, base).toBeGreaterThan(20);
    }
  });

  it("cero tipos locales con la firma de un tipo generado", () => {
    const encontrados = duplicados();
    expect(
      encontrados,
      "una superficie declara a mano la forma de una respuesta que `@takab/sdk` ya " +
        "publica. No la corrijas copiando campos: importa el tipo generado (o " +
        "aliásalo) para que haya UNA sola verdad sobre el cable.\n" +
        encontrados.join("\n"),
    ).toEqual([]);
  });
});
