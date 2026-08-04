import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * [T-2.51] Contrato sobre la HOJA DE ESTILOS, no sobre el DOM.
 *
 * jsdom no hace layout: no mide, no scrollea y no sabe qué es un elemento
 * inalcanzable. Un test de componente jamás habría visto el bug que motivó esto
 * — `.mt__list` sin `overflow` dentro de `body { overflow: hidden }`, que con ~15
 * clientes dejaba los últimos FÍSICAMENTE inalcanzables: sin barra, sin rueda y
 * sin teclado. La única forma de fijarlo sin un navegador real es leer el CSS.
 *
 * El segundo bloque caza el otro defecto de la misma familia: clases escritas en
 * un `.tsx` que nunca recibieron una regla (T-1.72 y T-1.73 entregaron el alta de
 * clientes y la tarjeta de visibilidad con CERO estilos, y nadie lo notó porque
 * el marcado sí existía). T-2.55 generalizará esto a todos los `className` del
 * repo; aquí se cubre exactamente lo que estaba huérfano y lo que se añade ahora.
 */

/** Vitest corre con `cwd` en `web/`; la hoja se lee del DISCO, sin pasar por el
 * pipeline de Vite (que la transformaría y la haría inasertable).
 *
 * Los comentarios se retiran ANTES de parsear: esta hoja documenta el porqué de
 * cada regla y varios comentarios citan CSS literal con llaves
 * (p. ej. la premisa del body). Con ellos dentro, el escaneo por llaves se
 * desincroniza y el test empieza a mentir a partir de ahí.
 */
function read(name: string): string {
  return readFileSync(resolve(process.cwd(), "src/styles", name), "utf8").replace(
    /\/\*[\s\S]*?\*\//g,
    "",
  );
}

const SOC = read("soc.css");
const TABS = read("soc-tabs.css");
const ALL = `${SOC}\n${TABS}`;

/**
 * TODAS las declaraciones que la hoja aplica a `selector`, concatenadas.
 *
 * Es deliberadamente el conjunto completo y no el primer bloque: en una hoja de
 * 1 700 líneas una clase se declara varias veces (base arriba, corrección de
 * layout abajo) y quedarse con la primera daría un falso negativo justo en el
 * caso que este test vigila. También cubre las listas separadas por comas,
 * donde el selector buscado no es el primero.
 */
function rulesFor(css: string, selector: string): string {
  const found: string[] = [];
  for (const [, selectors, body] of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    const parts = selectors.split(",").map((s) => s.trim().replace(/\s+/g, " "));
    if (parts.includes(selector)) {
      found.push(body);
    }
  }
  return found.join("\n");
}

function declares(css: string, selector: string, decl: RegExp): boolean {
  return decl.test(rulesFor(css, selector));
}

describe("clipping — `body { overflow: hidden }` no perdona un contenedor sin scroll", () => {
  it("la premisa sigue en pie: el shell oculta el desbordamiento del body", () => {
    // Si algún día el body scrollea, estas invariantes dejan de ser críticas —
    // pero entonces este test debe REVISARSE, no borrarse.
    expect(rulesFor(SOC, "body")).toMatch(/overflow:\s*hidden/);
  });

  it.each([
    [".mt", "Multi-Tenant"],
    [".fleet", "Flota Edge"],
    [".audit", "Auditoría"],
  ])("%s declara su propio scroll vertical (%s)", (selector) => {
    expect(declares(ALL, selector, /overflow-y:\s*auto/)).toBe(true);
  });

  it(".mt__list scrollea y puede encogerse: era el bug de accesibilidad real", () => {
    const block = rulesFor(TABS, ".mt__list");
    expect(block).toMatch(/overflow-y:\s*auto/);
    // Sin `min-height: 0` un hijo flex NO baja de su altura de contenido y el
    // `overflow-y` nunca llega a activarse.
    expect(block).toMatch(/min-height:\s*0/);
  });

  it(".mt__detail conserva el scroll que ya tenía (no se rompió al arreglar la lista)", () => {
    const block = rulesFor(TABS, ".mt__detail");
    expect(block).toMatch(/overflow-y:\s*auto/);
    expect(block).toMatch(/min-height:\s*0/);
  });

  it.each([".mt > *", ".triage > *", ".soc-main > *", ".fleet > *", ".mt__detail > *"])(
    "%s está en la invariante flex-shrink: 0",
    (selector) => {
      expect(declares(ALL, selector, /flex-shrink:\s*0/)).toBe(true);
    },
  );
});

/**
 * Clases usadas en el marcado que DEBEN tener regla. La lista es explícita a
 * propósito: cada entrada es una superficie que se entregó (o se entrega ahora)
 * y que un usuario va a mirar.
 */
const MUST_HAVE_RULES = [
  // T-1.72 · alta de clientes (entregada sin una sola regla)
  "mt__new-btn",
  "mt__new-form",
  "mt__new-field",
  "mt__new-error",
  "mt__new-submit",
  // T-1.73 · visibilidad entre clientes (ídem)
  "vis-grants",
  "vis-grant",
  "vis-grant__target",
  "vis-grant__revoke",
  "vis-form",
  "vis-form__field",
  "vis-form__check",
  "vis-form__error",
  "vis-form__submit",
  // T-1.59 · resultado del autodiagnóstico, y el separador de metadatos
  "fleet-card__selftest",
  "tk-sep",
  // T-2.51/52/53/54 · lo que entra en este ciclo
  "mt__search",
  "mt-edit",
  "mt-edit__field",
  "mt-edit__warn",
  "audit__table",
  "audit__filters",
  "enroll__code",
  "enroll__fresh",
  "users__list",
  "users__scope",
];

describe("CSS huérfano — una clase en el marcado sin regla es una pantalla sin estilo", () => {
  it.each(MUST_HAVE_RULES)(".%s tiene al menos una regla", (cls) => {
    expect(ALL).toContain(`.${cls}`);
  });
});
