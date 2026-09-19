// [T-7.58] EL CENSO: una promesa de `expo-file-system` sin esperar.
//
// EL DEFECTO NO ES TEÓRICO, es lo que costó esta ficha. `capture.ts` movía la
// foto forense con
//
//     origen.move(dest);        // ← sin `await`
//     const { bytes } = await readAndHash(origen.uri);
//
// y en `expo-file-system@57.0.1` **`move(destination, options?)` devuelve
// `Promise<void>`**. La lectura corría contra el movimiento nativo y el
// resultado salía a cara o cruz: el flujo E2E `02` fallaba ~1 de cada 2 corridas
// y el teléfono imprimía `FileNotFoundException … ENOENT`. La foto de un daño
// estructural se perdía mientras el brigadista creía que la había mandado.
//
// POR QUÉ ENGAÑA, y por eso hace falta un censo y no un comentario:
//   · las vecinas del mismo objeto —`delete()`, `create()`, `write()`— **sí son
//     síncronas**, así que la línea sin `await` no desentona al leerla;
//   · existe `moveSync()` aparte, y el nombre sin sufijo **parece** el síncrono;
//   · `tsc --noEmit` NO la caza: una promesa suelta no es un error de tipos, y
//     este árbol no tiene lint con información de tipos
//     (`@typescript-eslint/no-floating-promises` pide `projectService`).
//
// Se vigilan `move` y `copy`: son exactamente las dos que tienen gemela `*Sync`,
// que es lo que hace creer que la corta es la síncrona.
/// <reference types="node" />
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";

const SRC = resolve(process.cwd(), "src");

/** Las que devuelven `Promise` y tienen gemela `*Sync` que induce al error. */
const ASINCRONAS = ["move", "copy"] as const;

function fuentes(dir: string): string[] {
  return readdirSync(dir).flatMap((entrada) => {
    const p = join(dir, entrada);
    if (statSync(p).isDirectory()) {
      return fuentes(p);
    }
    return /\.tsx?$/.test(entrada) && !/\.test\.tsx?$/.test(entrada) ? [p] : [];
  });
}

/** Quita comentarios y cadenas: un ejemplo dentro de un comentario no es código. */
function soloCodigo(texto: string): string {
  return texto
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .replace(/(^|[^:])\/\/[^\n]*/g, "$1 ")
    .replace(/`(?:[^`\\]|\\.)*`/g, "``")
    .replace(/"(?:[^"\\]|\\.)*"/g, '""')
    .replace(/'(?:[^'\\]|\\.)*'/g, "''");
}

describe("[T-7.58] censo · ninguna promesa de expo-file-system se queda sin esperar", () => {
  it("todo `.move(`/`.copy(` de un fichero va precedido de `await` o `return`", () => {
    const sueltas: string[] = [];

    for (const fichero of fuentes(SRC)) {
      const crudo = readFileSync(fichero, "utf8");
      if (!crudo.includes("expo-file-system")) {
        continue;
      }
      const codigo = soloCodigo(crudo);
      for (const metodo of ASINCRONAS) {
        const patron = new RegExp(`\\.${metodo}\\s*\\(`, "g");
        for (const m of codigo.matchAll(patron)) {
          // Se camina hacia atrás por el RECEPTOR (`a.b[0].move(`) y se mira qué
          // hay justo antes. Buscarlo con un solo regex fallaba: el prefijo se
          // tragaba el propio `await` y el censo se acusaba a sí mismo.
          let i = m.index;
          while (i > 0 && /[\w$\].)]/.test(codigo[i - 1])) {
            i -= 1;
            if (/[).\]]/.test(codigo[i])) {
              // salta hacia atrás sobre un paréntesis/corchete equilibrado
              let nivel = codigo[i] === ")" ? 1 : codigo[i] === "]" ? 1 : 0;
              while (nivel > 0 && i > 0) {
                i -= 1;
                if (codigo[i] === ")" || codigo[i] === "]") nivel += 1;
                if (codigo[i] === "(" || codigo[i] === "[") nivel -= 1;
              }
            }
          }
          const antes = codigo.slice(Math.max(0, i - 40), i);
          if (/\b(await|return)\s+$/.test(antes)) {
            continue;
          }
          const linea = codigo.slice(0, m.index).split("\n").length;
          sueltas.push(
            `${relative(process.cwd(), fichero)}:${linea} → ${codigo.slice(i, m.index + m[0].length).trim()}`,
          );
        }
      }
    }

    if (sueltas.length > 0) {
      throw new Error(
        "PROMESA DE `expo-file-system` SIN ESPERAR. `move()` y `copy()` devuelven " +
          "`Promise<void>` (sus gemelas síncronas son `moveSync()`/`copySync()`), así que " +
          "lo que venga después corre CONTRA la operación nativa. Aquí eso significa leer " +
          "una foto de evidencia que todavía no se ha movido — y perderla.\n\n  " +
          sueltas.join("\n  "),
      );
    }
    expect(sueltas).toEqual([]);
  });
});
