/**
 * Los flujos de Maestro TIENEN QUE CARGAR.
 *
 * POR QUÉ ESTE TEST EXISTE
 * ------------------------
 * `03-dictamen-liberacion.yaml` —el flujo del dictamen firmado → reingreso
 * liberado— llevaba desde que se escribió **sin acreditarse nunca**, y la razón
 * no era el teléfono ni el entorno: llevaba `assertVisible` con un `timeout:`
 * dentro, propiedad que ese comando NO tiene. Maestro rechaza el fichero
 * ENTERO —«Unknown Property: timeout»— antes de ejecutar un solo paso, así que
 * el flujo no fallaba una aserción: no cargaba. Medido el 2026-09-12 con
 * Maestro 2.6.1, con el Pixel conectado y el estado sembrado a propósito.
 *
 * La espera se escribe con `extendedWaitUntil`, que es lo que hacen los otros
 * siete flujos. Este barrido existe para que el octavo no vuelva a nacer roto:
 * un flujo E2E que no carga se lee como «todavía no lo hemos corrido», y eso
 * puede durar meses.
 */
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

const RAIZ = join(__dirname, "..", ".maestro");

/** Comandos que NO admiten `timeout:` (la espera va en `extendedWaitUntil`). */
const SIN_TIMEOUT = ["assertVisible", "assertNotVisible", "assertTrue"];

function flujos(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
    e.isDirectory()
      ? flujos(join(dir, e.name))
      : e.name.endsWith(".yaml")
        ? [join(dir, e.name)]
        : [],
  );
}

describe("flujos de Maestro", () => {
  const ficheros = flujos(RAIZ);

  it("hay flujos que barrer (si no, este test no afirma nada)", () => {
    expect(ficheros.length).toBeGreaterThan(5);
  });

  it.each(ficheros.map((f) => [f.slice(RAIZ.length + 1), f]))(
    "%s no pone `timeout:` donde Maestro no lo acepta",
    (_nombre, ruta) => {
      const lineas = readFileSync(ruta, "utf8").split("\n");
      const malos: string[] = [];
      lineas.forEach((linea, i) => {
        const comando = /^\s*-\s+(\w+):\s*$/.exec(linea)?.[1];
        if (!comando || !SIN_TIMEOUT.includes(comando)) {
          return;
        }
        // El bloque del comando: las líneas indentadas que le siguen.
        for (let j = i + 1; j < lineas.length; j++) {
          if (!/^\s+\S/.test(lineas[j])) {
            break;
          }
          if (/^\s+timeout:/.test(lineas[j])) {
            malos.push(`${comando} en la línea ${j + 1}`);
          }
        }
      });
      expect(
        malos.join("; ") +
          (malos.length
            ? " — Maestro rechaza el fichero ENTERO y el flujo no llega a correr; usa extendedWaitUntil"
            : ""),
      ).toBe("");
    },
  );
});
