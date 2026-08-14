/**
 * [T-2.140] EL COMP DE DISEÑO DEL PANEL TAMBIÉN PINTA, AUNQUE NO SE SIRVA.
 *
 * `T-2.137` unificó en `#A78BFA` los TRES violetas con los que se pintaba la
 * única señal que dice «este equipo NO va a alertar» —el banner de MODO PRUEBA
 * WR-1— porque los otros dos REPRUEBAN el contraste medido:
 *
 *   rol                                       #7C4DFF   #A78BFA   umbral
 *   texto del banner sobre su tinte (panel)     2.86      4.53      4.5 (AA)
 *   borde del banner contra su propio tinte     2.86      4.53      3.0 (no-texto)
 *
 * Arregló el panel que se sirve (`edge/takab_edge/local_api/index.html`, vigilado
 * por `edge/tests/test_local_api_panel.py`) y dejó fuera el COMP del que se
 * implementa: `takab-docs/design/edge-panel/Panel Gabinete.dc.html` conservaba
 * `rgba(124,77,255,0.16)`, `#7C4DFF` de borde y `#B79CFF` de texto — los tres
 * exactos que se retiraron, y ninguna guardia los miraba.
 *
 * Importa poco hoy —el comp no se sirve a nadie— y mucho el día que alguien
 * implemente una pantalla copiando de él: reintroduciría, de buena fe y sin que
 * nada se pusiera rojo, un color que YA se midió que no pasa. Un comp de diseño
 * no es documentación muerta: es la fuente de la que se copia.
 *
 * EL CENSO ES POR TONO, no por lista de hexes conocidos — mismo criterio que
 * `test_local_api_panel.py::_es_violeta`. Una lista sólo caza el violeta que ya
 * sabíamos que existía, y el defecto de `T-2.137` fue justamente un tercer tono
 * que nadie había enumerado.
 *
 * Vive en `web/` y no en `edge/` porque `takab-docs/design/` es design system, y
 * el design system se gobierna desde el paquete de tokens que esta suite ya lee.
 * Es una LECTURA en tiempo de test, no un `import`: no añade dependencia de build
 * de la consola (cf. `consoleImageCensus.test.ts`).
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const RAIZ = resolve(process.cwd(), "..");
const COMP = resolve(RAIZ, "takab-docs", "design", "edge-panel", "Panel Gabinete.dc.html");
const TOKENS = resolve(RAIZ, "shared", "design-tokens", "tokens.json");

function hexARgb(color: string): [number, number, number] {
  const crudo = color.replace("#", "");
  return [
    parseInt(crudo.slice(0, 2), 16),
    parseInt(crudo.slice(2, 4), 16),
    parseInt(crudo.slice(4, 6), 16),
  ];
}

/** Azul-violeta saturado: el rango del que hablan las dos pantallas. */
function esVioleta(r: number, g: number, b: number): boolean {
  return b > 120 && b - Math.max(r, g) > 40 && r > g;
}

/**
 * Todo violeta del comp —`#RRGGBB` y `rgba()`— con dónde aparece.
 *
 * Sin comentarios: citar el color que se retiró no es pintarlo, y contarlo
 * dejaría el censo imposible de documentar.
 */
export function violetasDelComp(fuente: string): Record<string, string> {
  const sinComentarios = fuente.replace(/<!--[\s\S]*?-->/g, "").replace(/\/\*[\s\S]*?\*\//g, "");
  const hallados: Record<string, string> = {};
  for (const m of sinComentarios.matchAll(/#[0-9a-fA-F]{6}/g)) {
    const [r, g, b] = hexARgb(m[0]);
    if (esVioleta(r, g, b)) {
      hallados[m[0].toUpperCase()] = "hex";
    }
  }
  for (const m of sinComentarios.matchAll(/rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/g)) {
    const [r, g, b] = [Number(m[1]), Number(m[2]), Number(m[3])];
    if (esVioleta(r, g, b)) {
      hallados[
        `#${[r, g, b]
          .map((v) => v.toString(16).padStart(2, "0"))
          .join("")
          .toUpperCase()}`
      ] = m[0];
    }
  }
  return hallados;
}

describe("[T-2.140] el comp del panel no conserva el violeta que reprueba", () => {
  const canonico = (JSON.parse(readFileSync(TOKENS, "utf8")) as Record<string, string>)[
    "--tk-status-maintenance"
  ].toUpperCase();

  it("el barrido encuentra algún violeta (si no, el resto de este bloque miente)", () => {
    expect(Object.keys(violetasDelComp(readFileSync(COMP, "utf8")))).not.toHaveLength(0);
  });

  it("UN solo violeta, y es `--tk-status-maintenance` del paquete", () => {
    const hallados = violetasDelComp(readFileSync(COMP, "utf8"));
    const intrusos = Object.entries(hallados).filter(([color]) => color !== canonico);
    expect(
      intrusos.map(([color, donde]) => `${color} (como ${donde})`),
      `el comp pinta un violeta que el design system retiró por contraste ` +
        `(vigente: ${canonico}). Un comp es la fuente de la que se copia: ` +
        `corregirlo aquí evita que la próxima pantalla nazca reprobando AA.`,
    ).toEqual([]);
  });

  it("el barrido SÍ ve un violeta escrito inline en el marcado", () => {
    // El tercer tono de `T-2.137` vivía inline en un `<span style="color:…">`,
    // invisible para cualquier guardia que sólo mire custom properties. Este
    // caso fija que el censo mira el marcado, no sólo la hoja.
    const hallados = violetasDelComp('<span style="color:#B79CFF">x</span>');
    expect(hallados).toEqual({ "#B79CFF": "hex" });
  });

  it("y no confunde el cian ni el ámbar del panel con un violeta", () => {
    expect(violetasDelComp("#00BFFF #FFC107 rgba(0,191,255,0.15)")).toEqual({});
  });
});
