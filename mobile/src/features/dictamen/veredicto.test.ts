/**
 * [T-6.26 · U-40] NI UN IDENTIFICADOR CRUDO EN LA PANTALLA DEL OCUPANTE.
 *
 * `timeline.ts` imprimía `Firmado (inhabit_monitor)` a quien sólo quiere saber
 * si puede volver a su casa. Y había un segundo riesgo, más silencioso: la
 * consola y la app rotulaban los mismos cuatro valores por su cuenta, así que
 * podían divergir sin que nada fallara.
 *
 * Este test es la mitad que sostiene la copia: compara el módulo contra
 * `shared/glossary/dictamen.json` EN LOS DOS SENTIDOS.
 */
/// <reference types="node" />
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { TEXTO_OCUPANTE, textoOcupante, VEREDICTOS } from "./veredicto";

interface Glosario {
  orden: string[];
  veredictos: Record<string, { operador: string; ocupante: string; tono: string; habitable: boolean }>;
}

const GLOSARIO: Glosario = JSON.parse(
  readFileSync(
    resolve(process.cwd(), "..", "shared", "glossary", "dictamen.json"),
    "utf8",
  ),
);

describe("[T-6.26] la copia móvil del glosario NO puede divergir", () => {
  it("los cuatro veredictos, y en el mismo orden", () => {
    expect([...VEREDICTOS]).toEqual(GLOSARIO.orden);
  });

  it("cada texto del ocupante es EL DEL GLOSARIO, byte a byte", () => {
    for (const v of VEREDICTOS) {
      expect(TEXTO_OCUPANTE[v]).toBe(GLOSARIO.veredictos[v].ocupante);
    }
  });

  it("y al revés: el glosario no tiene ninguno que aquí falte", () => {
    // Sin esta dirección, añadir un quinto veredicto al JSON dejaría la app
    // enseñando «DICTAMEN TÉCNICO EMITIDO» para siempre y en silencio.
    expect(Object.keys(GLOSARIO.veredictos).sort()).toEqual([...VEREDICTOS].sort());
  });
});

describe("[T-6.26] lo que se le dice al ocupante", () => {
  it("traduce los cuatro", () => {
    for (const v of VEREDICTOS) {
      expect(textoOcupante(v)).toBe(GLOSARIO.veredictos[v].ocupante);
      expect(textoOcupante(v)).not.toMatch(/_/);
    }
  });

  it("un status DESCONOCIDO no se imprime crudo ni se degrada a aprobado", () => {
    const t = textoOcupante("algo_que_no_existe");
    expect(t).not.toContain("algo_que_no_existe");
    expect(t).toBe("DICTAMEN TÉCNICO EMITIDO");
    expect(t).not.toMatch(/APROBADO|REINGRESO/);
  });

  it("sin dictamen lo dice, sin fingir uno", () => {
    expect(textoOcupante(null)).toBe("SIN DICTAMEN");
    expect(textoOcupante(undefined)).toBe("SIN DICTAMEN");
  });
});
