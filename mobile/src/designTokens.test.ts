/**
 * [T-6.21 · U-21] NI UN COLOR ESCRITO A MANO EN `mobile/src`.
 *
 * La app tenía 43 literales repartidos por cinco ficheros —incluidos ámbares
 * que NO existían en `tokens.json`— y todos ellos en las dos pantallas de
 * VIDA: la crisis sísmica y la alarma del inmueble. `BuildingAlarmView`
 * declaraba la excepción por escrito, y eso era honesto; pero el efecto era que
 * las dos pantallas que más importa que se vean bien eran las ÚNICAS fuera de
 * cualquier drift gate. Se podía cambiar la marca entera y no se enteraban.
 *
 * Este censo es la otra mitad del trato del paquete: `make drift` vigila que el
 * CSS se derive de `tokens.json`, y esto vigila que nadie se salte el paquete
 * escribiendo el color a mano.
 */
/// <reference types="node" />
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";

import { tokens } from "@takab/design-tokens";

const SRC = resolve(__dirname);

/** Todo `.ts`/`.tsx` de producción bajo `src/` (los tests quedan fuera: un
 *  fixture puede necesitar un color literal para comparar contra él). */
function fuentes(dir = SRC, out: string[] = []): string[] {
  for (const e of readdirSync(dir)) {
    const full = join(dir, e);
    if (statSync(full).isDirectory()) {
      fuentes(full, out);
      continue;
    }
    if (!/\.tsx?$/.test(e) || e.includes(".test.")) continue;
    // El tema es el ÚNICO puente con el paquete; su trabajo es nombrar tokens.
    if (relative(SRC, full) === join("ui", "theme.ts")) continue;
    out.push(full);
  }
  return out;
}

/** `#rrggbb`, `#rgb` y `rgb()/rgba()` con números — un color escrito a mano. */
const LITERAL = /#[0-9A-Fa-f]{3,8}\b|rgba?\(\s*\d/g;

describe("[T-6.21] el color de la app sale del paquete, siempre", () => {
  it("el barrido encuentra fuentes (si esto falla, el resto mira aire)", () => {
    expect(fuentes().length).toBeGreaterThan(40);
  });

  it("ningún fichero de producción escribe un color a mano", () => {
    const ofensores: string[] = [];
    for (const f of fuentes()) {
      const texto = readFileSync(f, "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
      for (const m of texto.matchAll(LITERAL)) {
        const linea = texto.slice(0, m.index).split("\n").length;
        // Un color citado en un COMENTARIO de línea es prosa, no una regla.
        const renglon = texto.split("\n")[linea - 1] ?? "";
        if (renglon.trimStart().startsWith("//")) continue;
        ofensores.push(`${relative(SRC, f)}:${linea} → ${m[0]}`);
      }
    }
    expect(
      ofensores,
      // (jest no imprime este mensaje; queda como razón para quien lea el fallo)
    ).toEqual([]);
  });

  it("y las dos pieles de emergencia EXISTEN en el paquete", () => {
    // El censo de arriba pasaría con las pantallas borradas. Esto ata que la
    // familia que las viste siga estando y con la forma que consume el tema.
    for (const c of [tokens.color.emergency.red, tokens.color.emergency.amber]) {
      expect(Object.keys(c).length).toBeGreaterThan(4);
      for (const v of Object.values(c)) {
        expect(typeof v).toBe("string");
        expect(v).toMatch(/^(#|rgba?\()/);
      }
    }
  });
});
