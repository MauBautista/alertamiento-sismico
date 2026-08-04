import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { cssVariables } from "@takab/design-tokens";
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
 * el marcado sí existía). Esa lista explícita ya NO es la red principal:
 * `cssContract.test.ts` (T-2.55) cruza TODOS los `className` del repo contra
 * TODAS las reglas. Se conserva porque nombra superficies concretas que se
 * entregaron rotas: si alguien borrara el escáner, estas seguirían vigiladas.
 *
 * [T-2.55] Al final del archivo se añaden las invariantes de la degradación
 * responsive, de la geografía de sobrepuestos (colisiones) y de las fugas de
 * token — todo lo que un navegador vería y jsdom no.
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
const APP = read("app.css");
const ALL = `${SOC}\n${TABS}\n${APP}`;

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

/**
 * Cuerpo de una `@media` cuyo prelude contiene `query`, con las llaves
 * balanceadas. `rulesFor` no distingue contexto (su regex cae siempre al bloque
 * más interno), así que sin esto no se puede afirmar que una declaración vive
 * DENTRO de un breakpoint y no suelta en la cascada — que es justo lo que
 * separa "degradación" de "rediseño".
 */
function mediaBody(css: string, query: string): string {
  const at = css.indexOf(`@media ${query}`);
  if (at < 0) return "";
  const open = css.indexOf("{", at);
  let depth = 0;
  for (let i = open; i < css.length; i += 1) {
    if (css[i] === "{") depth += 1;
    else if (css[i] === "}") {
      depth -= 1;
      if (depth === 0) return css.slice(open + 1, i);
    }
  }
  return "";
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

/* =====================================================================
   [T-2.55] DEGRADACIÓN RESPONSIVE, COLISIONES Y FUGAS DE TOKEN
   ===================================================================== */

describe("breakpoints — los tokens mandan y las @media los citan literales", () => {
  it("los tres tokens existen con el valor que la hoja lleva escrito a mano", () => {
    // Este par de aserciones ES el guardarraíl de la trampa documentada arriba
    // de las @media en soc.css: como una custom property NO es válida en el
    // prelude de una @media, el píxel va literal y la única forma de que no se
    // desincronice del token es cruzarlos aquí.
    expect(cssVariables["--tk-bp-md"]).toBe("1280px");
    expect(cssVariables["--tk-bp-lg"]).toBe("1600px");
    expect(cssVariables["--tk-bp-xl"]).toBe("1920px");
  });

  it.each([
    ["(max-width: 1599px)", "--tk-bp-lg"],
    ["(max-width: 1279px)", "--tk-bp-md"],
  ])("existe la @media %s (fuente: %s)", (query) => {
    expect(mediaBody(SOC, query)).not.toBe("");
  });

  it("≥1600 queda INTACTO: ningún corte se abre por encima del objetivo", () => {
    // Un `min-width` traería estilos que solo existen en pantallas grandes, y
    // eso sería un rediseño, no una degradación. 1920×1080 es la línea base.
    expect(SOC).not.toMatch(/@media[^{]*min-width/);
  });

  it("bajo 1280 el documento RECUPERA el scroll: nada puede quedar inalcanzable", () => {
    const narrow = mediaBody(SOC, "(max-width: 1279px)");
    expect(rulesFor(narrow, "body")).toMatch(/overflow:\s*auto/);
    // Sin soltar la altura fija del shell, `overflow: auto` no tendría nada que
    // scrollear: el contenido seguiría recortado dentro de los 100vh.
    expect(rulesFor(narrow, ".soc-app")).toMatch(/height:\s*auto/);
    expect(rulesFor(narrow, ".soc-shell")).toMatch(/grid-template-columns:\s*minmax\(0, 1fr\)/);
  });

  it("bajo 1280 el detalle es un CAJÓN superpuesto, no la cola del documento", () => {
    const drawer = rulesFor(mediaBody(SOC, "(max-width: 1279px)"), ".soc-shell > .soc-detail");
    expect(drawer).toMatch(/position:\s*fixed/);
    expect(drawer).toMatch(/z-index:\s*var\(--tk-z-modal\)/);
  });

  it("con poco alto se recortan paddings — el mapa no vuelve a su piso de 280 px", () => {
    const short = mediaBody(SOC, "(max-height: 800px)");
    expect(short).not.toBe("");
    expect(rulesFor(short, ".soc-shell")).toMatch(/padding:\s*8px/);
    expect(rulesFor(short, ".soc-topbar")).toMatch(/height:\s*52px/);
  });
});

describe("colisiones de sobrepuestos — se resuelven REUBICANDO, no con z-index", () => {
  it("cada esquina superior tiene UN dueño y ambos están acotados al 46 %", () => {
    const right = rulesFor(SOC, ".soc-stage__overlays");
    const left = rulesFor(SOC, ".soc-map__status");
    expect(right).toMatch(/position:\s*absolute/);
    expect(left).toMatch(/position:\s*absolute/);
    expect(right).toMatch(/right:\s*14px/);
    expect(left).toMatch(/left:\s*14px/);
    // 46 % + 46 % < 100 %: la no-superposición es ARITMÉTICA, no una apuesta
    // sobre cuánto texto cabe. `e2e/layout.spec.ts` lo mide en un navegador.
    expect(right).toMatch(/width:\s*min\(360px, 46%\)/);
    expect(left).toMatch(/max-width:\s*46%/);
  });

  it("son PILAS: dos avisos a la vez se apilan en vez de taparse", () => {
    for (const block of [
      rulesFor(SOC, ".soc-stage__overlays"),
      rulesFor(SOC, ".soc-map__status"),
    ]) {
      expect(block).toMatch(/display:\s*flex/);
      expect(block).toMatch(/flex-direction:\s*column/);
    }
  });

  it("la alerta y el badge de mapa degradado ya no se anclan por su cuenta", () => {
    // Si vuelven a traer `position: absolute` estarán otra vez fuera de la pila
    // y podrán aterrizar encima de cualquier cosa.
    expect(rulesFor(SOC, ".soc-alert")).not.toMatch(/position:\s*absolute/);
    expect(rulesFor(SOC, ".soc-map__degraded")).not.toMatch(/position:\s*absolute/);
  });

  it("la leyenda cede: se acota en alto y en ancho antes que trepar a la alerta", () => {
    const legends = rulesFor(SOC, ".soc-map__legends");
    expect(legends).toMatch(/max-height:\s*calc/);
    expect(legends).toMatch(/max-width:\s*46%/);
    expect(legends).toMatch(/overflow-y:\s*auto/);
  });

  it("la atribución baja a la IZQUIERDA y deja de cruzar todo el ancho", () => {
    const attribution = rulesFor(SOC, ".soc-map__attribution");
    expect(attribution).toMatch(/left:\s*12px/);
    expect(attribution).toMatch(/right:\s*auto/);
  });

  it("DATOS RETENIDOS reserva su banda en el wall en vez de tapar los KPIs", () => {
    // El atributo lo escribe el propio StateFrame, así que la reserva aparece y
    // desaparece con el estado: sin dato viejo no se pierde ni un píxel de mapa.
    expect(rulesFor(SOC, '.soc-wall[data-state="stale"]')).toMatch(/padding-top:\s*26px/);
  });
});

describe("fugas y grids — lo que siempre cae al fallback o se desborda en silencio", () => {
  it("no queda ni una referencia a `--soc-*`: ese prefijo NO EXISTE", () => {
    // Siete declaraciones citaban `var(--soc-fg-2, …)` y compañía. Como el
    // prefijo del design system es `--tk-`, TODAS caían al valor de respaldo
    // hardcodeado: cambiar un token no movía la comparativa histórica. Un fallo
    // que no rompe nada y por eso vivió dos ciclos.
    expect(ALL).not.toMatch(/var\(\s*--soc-/);
  });

  it("ninguna reja reparte fracciones sin `minmax(0, …)`", () => {
    // `1fr` tiene suelo `auto`: una celda con contenido indivisible (una tabla,
    // un nombre largo, un <pre>) ENSANCHA la columna y desborda la reja entera
    // en vez de recortarse. Con `minmax(0, 1fr)` la celda cede y scrollea.
    const offenders = [...ALL.matchAll(/grid-template-columns:([^;]*);/g)]
      .map((m) => m[1].trim())
      .filter((value) => /(^|[\s(,])1fr/.test(value.replace(/minmax\([^)]*\)/g, "")));
    expect(offenders, `rejas con 1fr desnudo: ${offenders.join(" | ")}`).toEqual([]);
  });

  it("los tokens de ancho de columna se USAN (estaban definidos y muertos)", () => {
    // Un token que nadie consume no es un token: es documentación que miente.
    // Ambos existían desde el design system con un valor que NO era el que la
    // consola servía, así que el número real vivía duplicado en la hoja.
    expect(rulesFor(SOC, ".soc-shell")).toMatch(/var\(--tk-detail-w\)/);
    expect(cssVariables["--tk-detail-w"]).toBe("380px");
    expect(rulesFor(TABS, ".mt__grid")).toMatch(/var\(--tk-sidebar-w\)/);
    expect(cssVariables["--tk-sidebar-w"]).toBe("360px");
  });

  it("la escala z de los sobrepuestos sale de tokens, no de números sueltos", () => {
    expect(cssVariables["--tk-z-map-overlay"]).toBe("10");
    expect(cssVariables["--tk-z-map-status"]).toBe("20");
    expect(rulesFor(SOC, ".soc-map__legends")).toMatch(/z-index:\s*var\(--tk-z-map-overlay\)/);
    expect(rulesFor(SOC, ".soc-map__status")).toMatch(/z-index:\s*var\(--tk-z-map-status\)/);
    expect(rulesFor(SOC, ".soc-stage__overlays")).toMatch(/z-index:\s*var\(--tk-z-alert\)/);
  });
});

describe("sanidad del CSS — un error de sintaxis no lo grita nadie", () => {
  // Al limpiar CSS muerto en T-2.55 se dejó un comentario SIN CERRAR: el
  // navegador no protesta, no hay build que falle y el resultado es que el
  // siguiente bloque de reglas deja de existir en silencio. En una hoja donde
  // una regla ausente puede ser un panel invisible, eso no puede depender de
  // que alguien mire el diff.
  it.each([
    ["soc.css", SOC],
    ["soc-tabs.css", TABS],
    ["app.css", APP],
  ])("%s: llaves balanceadas y sin comentarios abiertos", (name, stripped) => {
    const raw = readFileSync(resolve(process.cwd(), "src/styles", name), "utf8");
    // `read()` retira los comentarios BIEN formados; si el conteo de aperturas
    // no cuadra con el de cierres, hay uno abierto tragándose reglas.
    expect((raw.match(/\/\*/g) ?? []).length, `${name}: comentario sin cerrar`).toBe(
      (raw.match(/\*\//g) ?? []).length,
    );
    const open = (stripped.match(/\{/g) ?? []).length;
    const close = (stripped.match(/\}/g) ?? []).length;
    expect(open, `${name}: llaves descuadradas`).toBe(close);
  });
});
