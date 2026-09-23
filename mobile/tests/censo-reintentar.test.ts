// [T-8.11] EL ERROR TIENE SALIDA: todo `StateFrame` ofrece REINTENTAR.
//
// Medido al auditar para la presentación: 10 de las 15 pantallas con
// `StateFrame` pintaban «SIN CONEXIÓN CON EL SERVIDOR» y NINGÚN botón. El marco
// solo dibuja REINTENTAR si recibe `onRetry` (`ui/StateFrame.tsx`), y todas las
// que se lo callaban tenían a mano el `refetch` de su consulta. En una sala con
// la red a medias, la única salida era cambiar de pestaña y volver — y eso no
// siempre re-consulta.
//
// Este censo exige `onRetry` en todo `<StateFrame` de producción. La deuda se
// declara por fichero y se compara por IGUALDAD: si alguien la salda, el test
// se pone rojo y obliga a borrar su línea.

/// <reference types="node" />
import { relative, resolve } from "node:path";

import { fuentesDeProduccion } from "@/test-utils/screenStateCensus";

const SRC = resolve(__dirname, "..", "src");

/**
 * Pantallas que todavía no ofrecen REINTENTAR, y por qué. Las tres quedaron
 * fuera del carril de T-8.11 (sus ficheros eran de otro carril o solo se podían
 * tocar para la respuesta al toque); las tres tienen con qué reintentar.
 */
const DEUDA: Record<string, string> = {
  "app/dictamen.tsx": "fuera del carril de T-8.11",
  "app/panic.tsx": "fuera del carril de T-8.11 (solo respuesta al toque)",
  "app/onboarding/privacidad.tsx": "fuera del carril de T-8.11 (tiene `cargar`)",
};

function sinComentarios(texto: string): string {
  return texto
    .replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, " "))
    .replace(/(^|[^:])\/\/[^\n]*/g, (m, antes: string) => antes + " ".repeat(m.length - antes.length));
}

/** Etiquetas `<StateFrame …>` (la apertura, hasta el `>` a profundidad 0). */
function marcos(texto: string): string[] {
  const out: string[] = [];
  let desde = 0;
  for (;;) {
    const i = texto.indexOf("<StateFrame", desde);
    if (i < 0) {
      return out;
    }
    desde = i + 1;
    if (!/[\s/>]/.test(texto[i + "<StateFrame".length] ?? "")) {
      continue;
    }
    let profundidad = 0;
    let j = i + "<StateFrame".length;
    for (; j < texto.length; j += 1) {
      const c = texto[j];
      if (c === "{" || c === "(" || c === "[") {
        profundidad += 1;
      } else if (c === "}" || c === ")" || c === "]") {
        profundidad -= 1;
      } else if (c === ">" && profundidad === 0 && texto[j - 1] !== "=") {
        break;
      }
    }
    out.push(texto.slice(i, j));
  }
}

const CON_MARCO = fuentesDeProduccion(SRC)
  .filter((f) => relative(SRC, f.path) !== "ui/StateFrame.tsx")
  .map((f) => ({ ruta: relative(SRC, f.path), marcos: marcos(sinComentarios(f.text)) }))
  .filter((f) => f.marcos.length > 0);

describe("censo · el error de un StateFrame ofrece REINTENTAR", () => {
  it("el barrido encuentra las pantallas (si no, no afirma nada)", () => {
    expect(CON_MARCO.length).toBeGreaterThanOrEqual(15);
  });

  it("toda pantalla con marco declara `onRetry`, salvo la deuda declarada", () => {
    const sinSalida = CON_MARCO.filter((f) => f.marcos.some((m) => !/\bonRetry=/.test(m)))
      .map((f) => f.ruta)
      .sort();
    expect(sinSalida).toEqual(Object.keys(DEUDA).sort());
  });

  it("el analizador distingue un marco con salida de uno sin ella", () => {
    expect(marcos('<StateFrame error={e} onRetry={() => q.refetch()} loading={l}>')[0]).toMatch(
      /onRetry=/,
    );
    expect(marcos("<StateFrame error={e} loading={l}>")[0]).not.toMatch(/onRetry=/);
    expect(marcos("// <StateFrame sin nada>\n".replace(/\/\/.*/, ""))).toHaveLength(0);
  });
});
