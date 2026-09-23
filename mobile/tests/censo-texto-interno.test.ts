// [T-8.11 · A-234] EL CLIENTE NO LEE CÓDIGOS DE TAREA.
//
// Medido al auditar para la presentación: el panel del táctico decía «VER
// DICTAMEN DE REINGRESO (2.7) →» —el número de sección de la especificación— y
// la Cuenta del ocupante, «Disponible para su perfil (decisión #7). El flujo de
// activación TOTP se habilita en T-2.14 (hardening)». Es el vocabulario del
// equipo pintado en el teléfono del cliente, y en una demostración se lee como
// una app a medio hacer.
//
// El censo barre el texto que la app puede PINTAR —texto de JSX y literales de
// cadena, sin comentarios— buscando las marcas del vocabulario interno: fichas
// (`T-2.14`), decisiones (`D-33`, «decisión #7»), secciones de un documento
// (`§3`, «(2.7)») y la jerga «hardening». En los comentarios siguen siendo
// bienvenidas: ahí son la trazabilidad. La deuda se compara por IGUALDAD.

/// <reference types="node" />
import { relative, resolve } from "node:path";

import { fuentesDeProduccion } from "@/test-utils/screenStateCensus";

const SRC = resolve(__dirname, "..", "src");

const MARCAS = /(\bT-\d+\.\d+|§\s*\d|decisi[oó]n #\d|\(\d\.\d+\)|\bhardening\b|\bD-\d{2}\b)/;

/**
 * Textos que aún las llevan, y por qué.
 *   · `ui/Pending.tsx`: el placeholder DEBE declarar su tarea (`mobile/AGENTS.md`)
 *     y hoy ninguna pantalla lo monta.
 *   · `app/denied.tsx`: «(RBAC §3)» — fuera del carril de T-8.11 (ese fichero
 *     solo se podía tocar para la respuesta al toque).
 */
const DEUDA = ["app/denied.tsx", "ui/Pending.tsx"];

function sinComentarios(texto: string): string {
  return texto
    .replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, " "))
    .replace(/(^|[^:])\/\/[^\n]*/g, (m, antes: string) => antes + " ".repeat(m.length - antes.length));
}

/** Texto de JSX (`>…<`) y literales de cadena de una fuente sin comentarios. */
function textos(fuente: string): string[] {
  const out: string[] = [];
  for (const m of sinComentarios(fuente).matchAll(/>([^<>{}]+)<|"([^"\n]*)"|`([^`]*)`|'([^'\n]*)'/g)) {
    const t = m[1] ?? m[2] ?? m[3] ?? m[4] ?? "";
    if (t.trim() !== "") {
      out.push(t);
    }
  }
  return out;
}

const PRODUCCION = fuentesDeProduccion(SRC);

describe("censo · el texto que se pinta no habla en códigos del equipo", () => {
  it("el barrido encuentra texto (si no, no afirma nada)", () => {
    expect(PRODUCCION.flatMap((f) => textos(f.text)).length).toBeGreaterThan(500);
  });

  it("ningún texto visible cita fichas, decisiones ni secciones, salvo la deuda declarada", () => {
    const con = PRODUCCION.filter((f) => textos(f.text).some((t) => MARCAS.test(t)))
      .map((f) => relative(SRC, f.path))
      .sort();
    expect(con).toEqual([...DEUDA].sort());
  });

  it("el analizador caza las marcas en el texto y las perdona en los comentarios", () => {
    expect(textos("<Text>VER DICTAMEN (2.7) →</Text>").some((t) => MARCAS.test(t))).toBe(true);
    expect(textos('const x = "se habilita en T-2.14";').some((t) => MARCAS.test(t))).toBe(true);
    expect(textos("// [T-2.14] trazabilidad\n/* D-33 */ <Text>Hola</Text>").some((t) => MARCAS.test(t))).toBe(
      false,
    );
  });
});
