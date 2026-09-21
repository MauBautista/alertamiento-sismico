// [T-7.24] CENSO DERIVADO: ninguna prop de `MapPanel` se queda sin alimentar.
//
// EL DEFECTO QUE CIERRA, medido: `MapPanel` estrenó `shakemap`/`shakemapError`,
// `shakemap.ts` estrenó sus builders, `soc.css` estrenó las muestras de la
// leyenda y `MapPanel.test.tsx` estrenó nueve pruebas… y el único montaje de
// producción —`ConsolePage.tsx`— no pasaba ninguna de las dos props. Como la
// leyenda y el botón de capa cuelgan de `shakemap !== undefined`, el resultado
// es que NINGÚN operador podía ver el mapa de la sacudida: existía sólo dentro
// de los tests. Una capa que nadie alimenta es una capa que no existe.
//
// POR QUÉ UN CENSO Y NO UNA PRUEBA DE ESAS DOS PROPS: la lista de hoy no impide
// la undécima de mañana. Aquí se cruza el CONJUNTO COMPLETO de props que
// `MapPanel` declara contra el CONJUNTO COMPLETO de atributos que le pasa la
// consola. Cualquier prop que nazca desconectada sale por aquí, se llame como se
// llame — la misma forma de guarda que `sdkTypeParity.test.ts`.
//
// ⚠️ Es una guarda de TEXTO sobre dos ficheros, a propósito: lo que vigila es
// justamente lo que ningún test de componente puede ver, porque el test monta
// `MapPanel` a mano y le pasa lo que quiere.

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const DIR = resolve(process.cwd(), "src/features/console");

function leer(nombre: string): string {
  // Los comentarios se retiran ANTES de escanear: los docblocks de `MapPanel`
  // citan nombres de prop en prosa, y contarlos daría por declarada —o por
  // pasada— una prop que sólo se menciona.
  return readFileSync(resolve(DIR, nombre), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
}

/** Las props que `MapPanel` DECLARA, de su propia interfaz. */
function propsDeclaradas(): string[] {
  const src = leer("MapPanel.tsx");
  const m = /export interface MapPanelProps \{([\s\S]*?)\n\}/.exec(src);
  expect(m, "no se encontró `export interface MapPanelProps`").not.toBeNull();
  const cuerpo = m![1].replace(/\/\/.*/g, "");
  return [...cuerpo.matchAll(/^ {2}(\w+)\??:/gm)].map((x) => x[1]).sort();
}

/** Los atributos que la CONSOLA le pasa en su único montaje de producción. */
function propsPasadas(): string[] {
  const src = leer("ConsolePage.tsx");
  const abre = src.indexOf("<MapPanel");
  expect(abre, "la consola ya no monta <MapPanel>").toBeGreaterThan(-1);
  // Se recorre hasta el cierre del elemento contando llaves: un atributo puede
  // llevar dentro una expresión con `>` (`a > b`, una flecha…) y cortar por el
  // primer `>` leería medio elemento.
  let i = abre + "<MapPanel".length;
  let llaves = 0;
  const atributos: string[] = [];
  let pendiente = "";
  for (; i < src.length; i += 1) {
    const c = src[i];
    if (c === "{") llaves += 1;
    else if (c === "}") llaves -= 1;
    else if (llaves === 0) {
      if (c === ">") break;
      pendiente += c;
    }
  }
  for (const m of pendiente.matchAll(/([A-Za-z_]\w*)\s*=\s*$/gm)) atributos.push(m[1]);
  // El barrido de arriba sólo ve los atributos cuyo `=` cierra la línea (el
  // estilo de Prettier en este repositorio). El de abajo recoge el resto.
  for (const m of pendiente.matchAll(/(?:^|\s)([A-Za-z_]\w*)\s*=/g)) atributos.push(m[1]);
  return [...new Set(atributos)].sort();
}

describe("[T-7.24] toda prop de MapPanel llega ALIMENTADA desde la consola", () => {
  it("el escáner lee de verdad las dos listas (sin esto, el censo sería aire)", () => {
    // Un censo que devuelve vacío pasa siempre. Se ancla contra props que
    // existen desde T-1.27 y T-2.28, no contra las de esta tarea.
    const declaradas = propsDeclaradas();
    const pasadas = propsPasadas();
    expect(declaradas).toContain("sites");
    expect(declaradas).toContain("catalog");
    expect(declaradas.length).toBeGreaterThan(8);
    expect(pasadas).toContain("sites");
    expect(pasadas).toContain("onViewportChange");
  });

  it("ninguna prop declarada se queda sin pasar", () => {
    const pasadas = new Set(propsPasadas());
    const huerfanas = propsDeclaradas().filter((p) => !pasadas.has(p));
    expect(
      huerfanas,
      "una prop que el único montaje de producción no pasa es una capa que ningún operador ve",
    ).toEqual([]);
  });

  it("y el mapa de la sacudida lo alimenta el HOOK, no una constante de la página", () => {
    // Que la prop esté escrita no basta: `shakemap={undefined}` pasaría el censo
    // de arriba. Lo que tiene que haber es una consulta al endpoint.
    const consola = leer("ConsolePage.tsx");
    expect(consola).toMatch(/import \{ useShakemap \} from "\.\/useShakemap"/);
    expect(consola).toMatch(/useShakemap\(focusIncident\?\.incident_id \?\? null\)/);
    expect(leer("useShakemap.ts")).toContain("/incidents/{incident_id}/shakemap");
  });
});
