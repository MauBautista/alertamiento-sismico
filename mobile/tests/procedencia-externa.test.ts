// [T-5.10] La app NO pinta cifras sísmicas externas — y este test lo mantiene así.
//
// La regla del proyecto es «con procedencia, o no se pinta»
// (`shared/glossary/procedencia.json`). En la consola eso significó hacer que la
// magnitud exija fuente y hora de consulta. **En la app significa otra cosa: que
// no hay ninguna cifra externa que pintar**, y es una decisión tomada, no un
// hueco pendiente:
//
//   · `CrisisView` lo lleva escrito: «PROHIBIDO cualquier cronómetro regresivo o
//     magnitud preliminar».
//   · `machine.ts` (§2.1-A): el WR-1 entrega un BOOLEANO — no hay magnitud ni ETA
//     que mostrar, y fabricarlos sería inventarlos.
//   · `dictamenView.ts`: «aquí no se muestra magnitud».
//
// Lo que este archivo impide es que alguien la añada sin darse cuenta de lo que
// significa. La app la mira alguien que está DENTRO del edificio, con el suelo
// moviéndose: una magnitud ahí no cambia lo que tiene que hacer, y una cifra sin
// procedencia se lee como medida por nosotros.
//
// Si algún día la app SÍ debe mostrarla, este test se cambia a propósito y con la
// decisión escrita — que es exactamente la fricción que se busca.
//
// [T-9.62 · T-9.66 · D-46] ESE DÍA LLEGÓ, y sólo para la pestaña SISMOS. La
// decisión: la app enseña los sismos de México que PUBLICÓ USGS —después del
// sismo, nunca en la crisis— con la atribución que manda el servidor y la hora de
// la última sincronización («con procedencia, o no se pinta»). Sigue prohibido en
// todo lo demás: la crisis, el dictamen y la alerta no pintan magnitud. La
// excepción es una LISTA CERRADA comparada por IGUALDAD: un fichero nuevo que
// pinte magnitud pone esto rojo, y uno de la lista que deje de citar la fuente,
// también.

import { readFileSync } from "node:fs";
import { join } from "node:path";

import { globSync } from "glob";

const RAIZ = join(__dirname, "..");
const GLOSARIO = join(RAIZ, "..", "shared", "glossary", "procedencia.json");

/** Las pantallas: lo que el usuario ve. Se excluyen los tests y los tipos. */
const PANTALLAS = globSync("src/**/*.{ts,tsx}", { cwd: RAIZ }).filter(
  (f) => !f.includes(".test.") && !f.endsWith(".d.ts"),
);

/**
 * [D-46] Las ÚNICAS vistas que pintan una magnitud externa, y por qué:
 *   · `SismosList.tsx` — la lista de la pestaña SISMOS (catálogo de USGS).
 *   · `HistorialCard.tsx` — los sismos del catálogo en el historial del inmueble.
 * Ninguna es de crisis: las dos viven en SISMOS, que es posterior al evento.
 */
const PINTAN_MAGNITUD_CON_PROCEDENCIA = [
  "src/features/sismos/HistorialCard.tsx",
  "src/features/sismos/SismosList.tsx",
];

describe("[T-5.10] la app no pinta cifras sísmicas externas", () => {
  it("el censo de pantallas no está vacío", () => {
    // Guarda de no-vacuidad: un glob que deje de casar convertiría todo lo de
    // abajo en un bucle sobre cero ficheros, verde y sin comprobar nada.
    expect(PANTALLAS.length).toBeGreaterThan(20);
  });

  it("ninguna pantalla formatea una magnitud, salvo las de SISMOS (D-46)", () => {
    // Se busca la FORMA de pintarla —`M 7.1`, `magnitude.toFixed`— y no la palabra
    // «magnitud», que aparece en los comentarios que PROHÍBEN pintarla.
    const culpables: string[] = [];
    for (const rel of PANTALLAS) {
      const src = readFileSync(join(RAIZ, rel), "utf8");
      const sinComentarios = src
        .replace(/\/\*[\s\S]*?\*\//g, "")
        .replace(/^\s*\/\/.*$/gm, "");
      if (/magnitude\s*\.\s*toFixed|["'`]M\s*\$\{|["'`]M\s+\d/.test(sinComentarios)) {
        culpables.push(rel);
      }
    }
    expect(culpables.sort()).toEqual(PINTAN_MAGNITUD_CON_PROCEDENCIA);
  });

  it("ninguna pantalla lee magnitud, epicentro ni profundidad de un evento, salvo SISMOS", () => {
    const culpables: string[] = [];
    for (const rel of PANTALLAS) {
      const src = readFileSync(join(RAIZ, rel), "utf8");
      const sinComentarios = src
        .replace(/\/\*[\s\S]*?\*\//g, "")
        .replace(/^\s*\/\/.*$/gm, "");
      if (/\b(?:event|evento|quake)\s*\.\s*(?:magnitude|epicenter\w*|depth_km)\b/.test(sinComentarios)) {
        culpables.push(rel);
      }
    }
    // Subconjunto de la lista cerrada: leer la magnitud del evento sólo lo hace
    // el historial, que pinta sismos del catálogo con su atribución.
    expect(culpables.filter((c) => !PINTAN_MAGNITUD_CON_PROCEDENCIA.includes(c))).toEqual([]);
  });

  it("[D-46] las vistas de la excepción CITAN la fuente que manda el servidor", () => {
    // «Con procedencia, o no se pinta»: la atribución del servidor, en el marcado.
    for (const rel of PINTAN_MAGNITUD_CON_PROCEDENCIA) {
      const src = readFileSync(join(RAIZ, rel), "utf8");
      expect(src).toMatch(/\.atribucion\b/);
    }
    // Y la lista pinta además la hora de la última sincronización.
    const lista = readFileSync(join(RAIZ, "src/features/sismos/SismosList.tsx"), "utf8");
    expect(lista).toMatch(/Actualizado: /);
  });

  it("[D-46] ninguna vista de crisis entra en la excepción", () => {
    for (const rel of PINTAN_MAGNITUD_CON_PROCEDENCIA) {
      expect(rel.startsWith("src/features/sismos/")).toBe(true);
    }
  });

  it("el vocabulario compartido existe y trae los cinco estados", () => {
    // La app no los pinta HOY, pero comparte el vocabulario: si mañana muestra
    // uno, tiene que llamarlo como las otras dos superficies y no inventar otro.
    const glosario = JSON.parse(readFileSync(GLOSARIO, "utf8"));
    const estados = Object.keys(glosario.estados);
    expect(estados).toHaveLength(5);
    for (const estado of estados) {
      expect(typeof glosario.estados[estado].movil).toBe("string");
      expect(glosario.estados[estado].movil.length).toBeGreaterThan(0);
    }
  });

  it("el glosario no dice «estimando» en el texto de la app", () => {
    const glosario = JSON.parse(readFileSync(GLOSARIO, "utf8"));
    for (const [estado, fila] of Object.entries<{ movil: string }>(glosario.estados)) {
      expect(fila.movil.toLowerCase()).not.toMatch(/estima/);
      expect(estado).toBeTruthy();
    }
  });
});
