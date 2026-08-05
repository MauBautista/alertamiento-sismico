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
 *
 * [F3] Una auditoría demostró que buena parte de esa red era TEATRO: las
 * aserciones buscaban el valor esperado como SUBCADENA del bloque, así que
 * "es exactamente una columna" pasaba con dos columnas. Desde aquí las
 * afirmaciones de igualdad se escriben con `toBe` sobre `declValue()` —que ancla
 * el nombre de la propiedad y el final del valor— y nunca con un regex suelto.
 * El porqué, con la mutación medida, está en el docblock de `declValues()`.
 *
 * [F4] Y una REauditoría demostró que ni así: `declValue` devolvía el PRIMER
 * valor declarado y el navegador aplica el ÚLTIMO. Con la suite completa en
 * verde se pudo reintroducir, literalmente, el bug que T-2.64.c acababa de
 * arreglar —la pista de 380 px reservada siempre— añadiendo un segundo bloque
 * `.soc-shell { … }` más abajo en la BASE de la hoja. Nadie borra un `;`, pero
 * en 1 733 líneas todo el mundo añade un bloque nuevo al final: es la vía de
 * regresión más probable que existe, y era invisible. El modelo de cascada que
 * lo cierra está en el docblock de `declValue()`.
 *
 * LO QUE SIGUE ESCAPANDO (medido, no supuesto — un "todo cerrado" falso es peor
 * que un agujero conocido):
 *
 *  · @media de RANGOS SOLAPADOS. `mediaBody("(max-width: 1279px)")` reúne todos
 *    los bloques de ESE prelude, pero un `@media (max-width: 1300px)` nuevo
 *    también aplica a 1279 y este archivo no lo mira. Se deja abierto a
 *    conciencia: fijar la lista de preludes convertiría cada breakpoint nuevo en
 *    un rojo, y añadir un breakpoint es un acto deliberado que se revisa —
 *    apilar un bloque más sobre un selector existente, que es lo que F4 cierra,
 *    no lo es.
 *  · `@supports` / `@container`: `baseScope` los recorta como cualquier at-rule
 *    y ningún ámbito los recupera. Hoy las hojas no usan ninguno.
 *  · Estilos que no viven en estas tres hojas: `colors_and_type.css`, los tokens
 *    y cualquier `style=` del marcado. Los dos primeros se importan ANTES de
 *    `soc.css`, así que pierden la cascada y no verlos es correcto; el atributo
 *    inline no lo cubre ningún test de hoja.
 *  · Esto sigue siendo LECTURA DE TEXTO, no layout. Que la hoja diga
 *    `minmax(0, 1fr)` no prueba que el mapa mida lo que debe: eso lo miden
 *    `e2e/layout.spec.ts` y `screens.spec.ts` en un navegador real.
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
/** Orden de `main.tsx`: soc.css → soc-tabs.css → app.css. Concatenar en ESE
 * orden no es cosmético: entre dos reglas de igual especificidad gana la última,
 * y la última es la del archivo importado después. T-2.58 cazó una @media muerta
 * desde T-1.54 exactamente por eso. */
const ALL = `${SOC}\n${TABS}\n${APP}`;

/**
 * La hoja SIN ninguna at-rule: lo que aplica en 1920×1080, la línea base del
 * producto.
 *
 * [F4] Es la mitad del arreglo de la reauditoría. `declValue` mezclaba dos
 * necesidades incompatibles —"el valor de la BASE" y "el que gana en este
 * ámbito"— y las resolvía con la misma heurística frágil ("el primero"), que
 * solo acertaba mientras las @media vivieran al final del archivo. Aquí se
 * separan: el ÁMBITO se recorta antes (`baseScope`/`mediaBody`) y el extractor
 * ya solo decide DENTRO de un ámbito homogéneo.
 *
 * Se recortan los bloques at-rule enteros en vez de truncar en la primera
 * `@media`: `soc.css` tiene 230 líneas de reglas base DESPUÉS de su
 * `@media (prefers-reduced-motion)` de la línea 1301, y truncar allí las
 * volvería invisibles — un `null` silencioso donde hay una declaración real, que
 * es la misma familia de mentira que este archivo existe para cazar.
 *
 * `@keyframes` cae con el resto: sus `from`/`to` no son selectores del layout.
 */
function baseScope(css: string): string {
  let out = "";
  let i = 0;
  while (i < css.length) {
    const at = css.indexOf("@", i);
    if (at < 0) return out + css.slice(i);
    out += css.slice(i, at);
    // Un `@` solo abre at-rule al principio de una regla; dentro de un valor
    // (`content: "@"`) es texto, y tratarlo como at-rule se comería la regla
    // siguiente entera.
    const previo = css.slice(0, at).trimEnd().slice(-1);
    if (!/^@[a-zA-Z-]/.test(css.slice(at)) || !(previo === "" || "};{".includes(previo))) {
      out += "@";
      i = at + 1;
      continue;
    }
    const brace = css.indexOf("{", at);
    const semi = css.indexOf(";", at);
    if (brace < 0 || (semi >= 0 && semi < brace)) {
      // at-rule sin bloque: `@import …;`, `@charset …;`
      i = semi >= 0 ? semi + 1 : css.length;
      continue;
    }
    let depth = 0;
    let j = brace;
    for (; j < css.length; j += 1) {
      if (css[j] === "{") depth += 1;
      else if (css[j] === "}") {
        depth -= 1;
        if (depth === 0) break;
      }
    }
    i = j + 1;
  }
  return out;
}

/**
 * Lo que las TRES hojas aplican en la pantalla grande, en orden de import.
 *
 * [F4] Las afirmaciones de valor van sobre esto y no sobre `baseScope(SOC)`: la
 * pregunta que hacen no es "¿qué dice soc.css?" sino "¿qué pinta el navegador?",
 * y en ese orden la última palabra la tiene `app.css`. Se midió: una regla
 * `.soc-shell { grid-template-columns: … }` añadida a `app.css` gana la cascada
 * y con el ámbito acotado a soc.css era invisible.
 */
const ALL_BASE = [SOC, TABS, APP].map(baseScope).join("\n");

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

/**
 * TODOS los valores que `block` declara para `prop`, en orden de aparición y con
 * los espacios normalizados. Vacío si no la declara.
 *
 * [F3] Nace de una auditoría que demostró que la red de este archivo era TEATRO.
 * `toMatch(/grid-template-columns:\s*minmax\(0, 1fr\)\s*;?/)` NO afirma "una sola
 * pista": ante `minmax(0, 1fr) 320px` el `\s*` se come el espacio y el `;?` casa
 * VACÍO al llegar al `3`, así que pasa igual. El auditor mutó
 * `@media (max-width: 1279px) > .soc-shell[data-detail="open"]` a dos pistas y
 * los 67 tests de este archivo siguieron VERDES — la regresión que el test dice
 * vigilar entraba sin ruido.
 *
 * El defecto tiene una segunda cara, la del NOMBRE: `/height:\s*52px/` lo
 * satisface `min-height: 52px`, y `/right:\s*14px/` lo satisface
 * `margin-right: 14px`. Otra propiedad, otro comportamiento, test verde. Por eso
 * el nombre se ancla a un principio de declaración (inicio del bloque, `;`, `{`,
 * `}` o salto de línea — un `-` delante NO es frontera) y el valor termina en su
 * `;` o en el fin del bloque.
 *
 * REGLA DEL ARCHIVO desde F3: una afirmación de IGUALDAD se escribe con `toBe`
 * sobre este extractor, jamás con un regex de subcadena. Los regex sueltos
 * quedan para las aserciones NEGATIVAS (`.not.toMatch`), de las que este archivo
 * tiene CUATRO —el `min-width` prohibido, `.soc-alert`, `.soc-map__degraded` y
 * el prefijo `--soc-`—: ahí pasarse de amplio solo puede hacer fallar el test,
 * nunca dejar pasar la regresión.
 *
 * [F4] `!important` NO forma parte del valor: es un modificador de cascada. Se
 * separa aquí para que `declValue` pueda modelarlo (ver su docblock) y para que
 * `padding: 8px !important` no se lea como un valor distinto de `padding: 8px`,
 * que fue una falsa alarma medida por la reauditoría (mutación M-08).
 */
function declarations(block: string, prop: string): { valor: string; important: boolean }[] {
  const re = new RegExp(String.raw`(?:^|[;{}\n])\s*${prop}\s*:([^;{}]*)`, "g");
  return [...block.matchAll(re)].map((m) => {
    const crudo = m[1].replace(/\s+/g, " ").trim();
    return {
      valor: crudo.replace(/\s*!\s*important$/i, "").trim(),
      important: /!\s*important$/i.test(crudo),
    };
  });
}

function declValues(block: string, prop: string): string[] {
  return declarations(block, prop).map((d) => d.valor);
}

/**
 * El valor de `prop` que GANA en este ámbito, o `null` si no se declara.
 *
 * [F4] Devolvía el PRIMERO. El navegador aplica el ÚLTIMO, y `rulesFor` está
 * construido a propósito para concatenar varios bloques del mismo selector (su
 * propio docblock lo dice), así que `declValue` elegía justo el que la cascada
 * descarta. La reauditoría lo midió: un segundo bloque
 * `.soc-shell { grid-template-columns: minmax(0,1fr) var(--tk-detail-w) }`
 * añadido en la BASE reintroducía el bug de T-2.64.c —408 px de mapa regalados a
 * una columna vacía— con los 1 162 tests de la suite en verde, incluido el
 * describe que dice vigilarlo. Cinco mutaciones de esa forma pasaban.
 *
 * POR QUÉ "EL ÚLTIMO" RESPETA LA ESPECIFICIDAD Y NO SOLO EL ORDEN: `rulesFor`
 * agrupa por selector EXACTO (`parts.includes(selector)`, no una subcadena), así
 * que todos los bloques que concatena tienen —por construcción— la misma
 * especificidad. Con la especificidad constante, la cascada se decide solo por
 * orden de fuente, y ahí gana el último. `.soc-shell[data-detail="open"]` (0,2,0)
 * NUNCA entra en el grupo de `.soc-shell` (0,1,0): son dos ámbitos distintos, y
 * que el atributo gane aunque esté antes se asserta aparte —exigiendo que el
 * selector pelado NO declare la propiedad en ese breakpoint (`toBeNull`)—, que
 * es la única forma de afirmarlo sin implementar un motor de cascada.
 *
 * `!important` sí puede romper el orden: una declaración importante ANTERIOR
 * gana a una normal posterior. Sin modelarlo, un `!important` colado arriba
 * quedaría enmascarado por el bloque canónico de abajo y el test daría verde
 * mientras el navegador pinta otra cosa. Se elige el último importante si lo
 * hay; si no, el último normal.
 *
 * El ÁMBITO se recorta ANTES de llamar aquí: `ALL_BASE` para lo que vale en
 * 1920, `mediaBody()` para lo que vale bajo un breakpoint. Pasar `SOC` entero
 * mezclaría base y @media en el mismo grupo y afirmaría de la pantalla grande lo
 * que solo vale bajo 1280.
 */
function declValue(block: string, prop: string): string | null {
  const decls = declarations(block, prop);
  if (decls.length === 0) return null;
  const importantes = decls.filter((d) => d.important);
  const pila = importantes.length > 0 ? importantes : decls;
  return pila[pila.length - 1].valor;
}

/**
 * Cuerpo de TODAS las `@media` cuyo prelude empieza por `query`, concatenadas en
 * orden de fuente y con las llaves balanceadas. `rulesFor` no distingue contexto
 * (su regex cae siempre al bloque más interno), así que sin esto no se puede
 * afirmar que una declaración vive DENTRO de un breakpoint y no suelta en la
 * cascada — que es justo lo que separa "degradación" de "rediseño".
 *
 * [F4] Devolvía SOLO la primera coincidencia, que es el mismo agujero que tenía
 * `declValue` una capa más arriba: añadir un segundo
 * `@media (max-width: 1279px) { … }` al final de la hoja —el gesto más natural
 * del mundo al tocar una pantalla estrecha— dejaba fuera del test todo lo que
 * ese bloque declarase. Se concatenan todos y `declValue` decide dentro.
 *
 * El prefijo basta porque el archivo prohíbe `min-width` (hay una negación que
 * lo vigila): sin `and (min-width: …)` colgando detrás, un prelude que empieza
 * por `(max-width: 1279px)` ES ese ámbito y no un subconjunto suyo.
 */
function mediaBody(css: string, query: string): string {
  const cuerpos: string[] = [];
  let from = 0;
  for (;;) {
    const at = css.indexOf(`@media ${query}`, from);
    if (at < 0) break;
    const open = css.indexOf("{", at);
    if (open < 0) break;
    let depth = 0;
    let i = open;
    for (; i < css.length; i += 1) {
      if (css[i] === "{") depth += 1;
      else if (css[i] === "}") {
        depth -= 1;
        if (depth === 0) break;
      }
    }
    cuerpos.push(css.slice(open + 1, i));
    from = i + 1;
  }
  return cuerpos.join("\n");
}

describe("clipping — `body { overflow: hidden }` no perdona un contenedor sin scroll", () => {
  it("la premisa sigue en pie: el shell oculta el desbordamiento del body", () => {
    // Si algún día el body scrollea, estas invariantes dejan de ser críticas —
    // pero entonces este test debe REVISARSE, no borrarse.
    // Igualdad y no subcadena: `overflow` admite DOS valores, y `overflow: hidden
    // auto` —un body que SÍ scrollea en vertical, o sea la premisa rota— satisfacía
    // el regex sin anclar.
    // [F4] Sobre `ALL_BASE` y no `SOC`: bajo 1280 el body RECUPERA el scroll a
    // propósito, y esa declaración vive en una @media. Mezclarlas en el mismo
    // grupo haría que la del breakpoint —legítima— decidiera una afirmación
    // sobre la pantalla grande.
    expect(declValue(rulesFor(ALL_BASE, "body"), "overflow")).toBe("hidden");
  });

  it.each([
    [".mt", "Multi-Tenant"],
    [".fleet", "Flota Edge"],
    [".audit", "Auditoría"],
  ])("%s declara su propio scroll vertical (%s)", (selector) => {
    // Existencia, no igualdad: la declaración puede venir de cualquiera de las
    // tres hojas. Pero el VALOR se compara entero (`toContain` sobre la lista de
    // valores), no como subcadena del bloque.
    expect(declValues(rulesFor(ALL, selector), "overflow-y")).toContain("auto");
  });

  it(".mt__list scrollea y puede encogerse: era el bug de accesibilidad real", () => {
    const block = rulesFor(TABS, ".mt__list");
    expect(declValues(block, "overflow-y")).toContain("auto");
    // Sin `min-height: 0` un hijo flex NO baja de su altura de contenido y el
    // `overflow-y` nunca llega a activarse.
    expect(declValues(block, "min-height")).toContain("0");
  });

  it(".mt__detail conserva el scroll que ya tenía (no se rompió al arreglar la lista)", () => {
    const block = rulesFor(TABS, ".mt__detail");
    expect(declValues(block, "overflow-y")).toContain("auto");
    expect(declValues(block, "min-height")).toContain("0");
  });

  it.each([".mt > *", ".triage > *", ".soc-main > *", ".fleet > *", ".mt__detail > *"])(
    "%s está en la invariante flex-shrink: 0",
    (selector) => {
      // `/flex-shrink:\s*0/` lo satisfacía `flex-shrink: 0.5`, que SÍ encoge:
      // exactamente lo que la invariante prohíbe.
      expect(declValues(rulesFor(ALL, selector), "flex-shrink")).toContain("0");
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

/**
 * ¿Hay alguna regla que estile EL ELEMENTO que lleva `.cls`, y que declare algo?
 *
 * [F4] Comprobar que el NOMBRE aparece en la hoja no es comprobar que la clase
 * está estilada: la reauditoría vació `.mt__search { }` y el test siguió verde
 * (mutación M-26). Una regla vacía es exactamente el defecto que esta lista
 * existe para cazar —una superficie entregada con los estilos por defecto del
 * navegador dentro de una consola oscura—, solo que con las llaves puestas.
 * Endurecerlo es seguro y se verificó antes de hacerlo: las tres hojas no tienen
 * HOY ni un solo bloque sin declaraciones, así que nadie usa la regla vacía como
 * marcador a propósito.
 *
 * Y no basta con "hay una regla no vacía que la menciona": vaciar `.mt__search`
 * seguía pasando gracias a `.mt__search input`, que estila al HIJO. Se exige que
 * la clase sea el SUJETO del selector —el último compuesto—, así que valen
 * `.mt__new-submit:disabled` y `.mt .mt__search`, y no valen `.mt__search input`
 * ni `.audit__table th`. Medido: las 26 clases de la lista tienen hoy su regla de
 * sujeto con declaraciones.
 */
function hasRule(css: string, cls: string): boolean {
  const sujeto = new RegExp(String.raw`\.${cls}(?![\w-])[^\s>+~]*$`);
  for (const [, selectors, body] of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    if (!/[\w-]+\s*:\s*[^\s;]/.test(body)) continue;
    const parts = selectors.split(",").map((s) => s.trim().replace(/\s+/g, " "));
    if (parts.some((p) => sujeto.test(p))) return true;
  }
  return false;
}

describe("CSS huérfano — una clase en el marcado sin regla es una pantalla sin estilo", () => {
  it.each(MUST_HAVE_RULES)(".%s tiene al menos una regla", (cls) => {
    // [F3] La frontera importa y es del mismo defecto que el resto del archivo:
    // `toContain(".vis-form")` lo satisfacía la regla de `.vis-form__field`, así
    // que la lista podía "vigilar" clases sin una sola declaración propia. Se
    // exige que tras el nombre no siga otro carácter de clase.
    expect(hasRule(ALL, cls), `.${cls} no tiene ninguna regla con declaraciones`).toBe(true);
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
    // `overflow: auto hidden` (x scrollea, y NO) casaba con el regex viejo y deja
    // el documento tan inalcanzable como antes del arreglo.
    expect(declValue(rulesFor(narrow, "body"), "overflow")).toBe("auto");
    // Sin soltar la altura fija del shell, `overflow: auto` no tendría nada que
    // scrollear: el contenido seguiría recortado dentro de los 100vh. Y ojo:
    // `/height:\s*auto/` lo satisfacían `min-height: auto` y `max-height: auto`,
    // que dejan en pie el `height: 100vh` de la base.
    expect(declValue(rulesFor(narrow, ".soc-app"), "height")).toBe("auto");
    expect(declValue(rulesFor(narrow, ".soc-shell"), "grid-template-columns")).toBe(
      "minmax(0, 1fr)",
    );
  });

  it("bajo 1280 el detalle es un CAJÓN superpuesto, no la cola del documento", () => {
    const drawer = rulesFor(mediaBody(SOC, "(max-width: 1279px)"), ".soc-shell > .soc-detail");
    expect(declValue(drawer, "position")).toBe("fixed");
    expect(declValue(drawer, "z-index")).toBe("var(--tk-z-modal)");
  });

  it("con poco alto se recortan paddings — el mapa no vuelve a su piso de 280 px", () => {
    const short = mediaBody(SOC, "(max-height: 800px)");
    expect(short).not.toBe("");
    // `padding` es un atajo de hasta cuatro valores: `/padding:\s*8px/` lo
    // satisfacía `padding: 8px 40px`, que no recorta ni un píxel en horizontal.
    //
    // [F4] Esta línea era la FALSA ALARMA de la reauditoría (M-08): con
    // `padding: 8px !important` —que no cambia un solo píxel: ya era el último
    // bloque que declara padding— el test se ponía rojo, porque el extractor
    // metía el modificador de cascada dentro del valor. Rojo de más no es un
    // agujero, pero sí es ruido que enseña a desconfiar del test. Desde F4
    // `declarations()` separa `!important` del valor y esto queda verde,
    // mientras el `!important` sigue contando donde SÍ decide algo: elegir qué
    // declaración gana (ver `declValue`).
    expect(declValue(rulesFor(short, ".soc-shell"), "padding")).toBe("8px");
    // Y `/height:\s*52px/` lo satisfacía `min-height: 52px`: la barra no bajaría
    // de 64 px y el recorte por alto sería letra muerta.
    expect(declValue(rulesFor(short, ".soc-topbar"), "height")).toBe("52px");
  });
});

describe("colisiones de sobrepuestos — se resuelven REUBICANDO, no con z-index", () => {
  it("cada esquina superior tiene UN dueño y ambos están acotados al 46 %", () => {
    const right = rulesFor(ALL_BASE, ".soc-stage__overlays");
    const left = rulesFor(ALL_BASE, ".soc-map__status");
    expect(declValue(right, "position")).toBe("absolute");
    expect(declValue(left, "position")).toBe("absolute");
    // El nombre va anclado: `/right:\s*14px/` lo satisfacía `margin-right: 14px`,
    // que no ancla NADA a la esquina — el aviso volvería a flotar donde cayera.
    expect(declValue(right, "right")).toBe("14px");
    expect(declValue(left, "left")).toBe("14px");
    // 46 % + 46 % < 100 %: la no-superposición es ARITMÉTICA, no una apuesta
    // sobre cuánto texto cabe. `e2e/layout.spec.ts` lo mide en un navegador.
    // Aquí `width` y `max-width` son propiedades DISTINTAS y el aritmético
    // depende de cuál sea: el regex viejo las confundía (`/width:\s*…/` casa
    // dentro de `max-width:`).
    expect(declValue(right, "width")).toBe("min(360px, 46%)");
    expect(declValue(left, "max-width")).toBe("46%");
  });

  it("son PILAS: dos avisos a la vez se apilan en vez de taparse", () => {
    for (const block of [
      rulesFor(ALL_BASE, ".soc-stage__overlays"),
      rulesFor(ALL_BASE, ".soc-map__status"),
    ]) {
      expect(declValue(block, "display")).toBe("flex");
      expect(declValue(block, "flex-direction")).toBe("column");
    }
  });

  it("la alerta y el badge de mapa degradado ya no se anclan por su cuenta", () => {
    // Si vuelven a traer `position: absolute` estarán otra vez fuera de la pila
    // y podrán aterrizar encima de cualquier cosa.
    //
    // Las CUATRO negaciones del archivo —esta pareja, el `min-width` prohibido y
    // el prefijo `--soc-`— se quedan con regex ancho a propósito: en una
    // negación, pasarse de amplio solo puede hacer fallar el test de más — nunca
    // dejar pasar la regresión. El defecto de F3 es de las afirmaciones.
    //
    // Y van sobre `SOC` completo, no sobre `ALL_BASE`: un `position: absolute`
    // dentro de una @media saca al elemento de la pila igual de bien, y en una
    // negación abarcar de más nunca deja pasar la regresión.
    const alerta = rulesFor(SOC, ".soc-alert");
    const degradado = rulesFor(SOC, ".soc-map__degraded");
    // [F4] Guarda de no-vacuidad: una negación sobre una cadena VACÍA pasa
    // siempre. Si alguien renombrara la clase, el test seguiría verde sin vigilar
    // nada. `cssContract.test.ts` caza el renombre por otra vía, pero una red que
    // depende de que la otra red exista no es una red — es una coincidencia.
    expect(alerta, ".soc-alert perdió su regla: la negación pasaría vacía").not.toBe("");
    expect(degradado, ".soc-map__degraded perdió su regla: la negación pasaría vacía").not.toBe("");
    expect(alerta).not.toMatch(/position:\s*absolute/);
    expect(degradado).not.toMatch(/position:\s*absolute/);
  });

  it("la leyenda cede: se acota en alto y en ancho antes que trepar a la alerta", () => {
    const legends = rulesFor(ALL_BASE, ".soc-map__legends");
    // El tope es laxo a propósito —se exige que HAYA cota calculada, no un píxel
    // concreto—, pero sobre el valor extraído y anclado con `^`: así lo laxo es
    // una decisión y no un descuido del regex.
    expect(declValue(legends, "max-height")).toMatch(/^calc\(/);
    expect(declValue(legends, "max-width")).toBe("46%");
    expect(declValue(legends, "overflow-y")).toBe("auto");
  });

  it("la atribución baja a la IZQUIERDA y deja de cruzar todo el ancho", () => {
    const attribution = rulesFor(ALL_BASE, ".soc-map__attribution");
    // `/left:\s*12px/` lo satisfacía `border-left: 12px solid …`.
    expect(declValue(attribution, "left")).toBe("12px");
    expect(declValue(attribution, "right")).toBe("auto");
  });

  it("DATOS RETENIDOS reserva su banda en el wall en vez de tapar los KPIs", () => {
    // El atributo lo escribe el propio StateFrame, así que la reserva aparece y
    // desaparece con el estado: sin dato viejo no se pierde ni un píxel de mapa.
    expect(declValue(rulesFor(ALL_BASE, '.soc-wall[data-state="stale"]'), "padding-top")).toBe(
      "26px",
    );
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
    // El barrido NO exige el `;` final: con `/…([^;]*);/` una declaración que
    // cerrara el bloque sin punto y coma quedaba fuera del escaneo en silencio,
    // que es la forma exacta en que un ofensor se cuela.
    const offenders = [...ALL.matchAll(/grid-template-columns:([^;{}]*)/g)]
      .map((m) => m[1].trim())
      .filter((value) => /(^|[\s(,])1fr/.test(value.replace(/minmax\([^)]*\)/g, "")));
    expect(offenders, `rejas con 1fr desnudo: ${offenders.join(" | ")}`).toEqual([]);
  });

  it("los tokens de ancho de columna se USAN (estaban definidos y muertos)", () => {
    // Un token que nadie consume no es un token: es documentación que miente.
    // Ambos existían desde el design system con un valor que NO era el que la
    // consola servía, así que el número real vivía duplicado en la hoja.
    // Aquí sí se busca una PARTE del valor (el token entre varias pistas), pero
    // sobre el valor ya extraído de su propiedad: no sobre el bloque entero, donde
    // el token podría venir de cualquier otra declaración.
    expect(
      declValue(rulesFor(ALL_BASE, '.soc-shell[data-detail="open"]'), "grid-template-columns"),
    ).toContain("var(--tk-detail-w)");
    expect(cssVariables["--tk-detail-w"]).toBe("380px");
    expect(declValue(rulesFor(ALL_BASE, ".mt__grid"), "grid-template-columns")).toContain(
      "var(--tk-sidebar-w)",
    );
    expect(cssVariables["--tk-sidebar-w"]).toBe("360px");
  });

  it("la escala z de los sobrepuestos sale de tokens, no de números sueltos", () => {
    expect(cssVariables["--tk-z-map-overlay"]).toBe("10");
    expect(cssVariables["--tk-z-map-status"]).toBe("20");
    expect(declValue(rulesFor(ALL_BASE, ".soc-map__legends"), "z-index")).toBe(
      "var(--tk-z-map-overlay)",
    );
    expect(declValue(rulesFor(ALL_BASE, ".soc-map__status"), "z-index")).toBe(
      "var(--tk-z-map-status)",
    );
    expect(declValue(rulesFor(ALL_BASE, ".soc-stage__overlays"), "z-index")).toBe(
      "var(--tk-z-alert)",
    );
  });
});

/**
 * [T-2.64.c] La pista del detalle se RESERVABA siempre.
 *
 * `.soc-shell` declaraba `minmax(0,1fr) var(--tk-detail-w)` en la base, pero
 * `ConsolePage` monta `<DetailPanel>` solo con `detailOpen && focusSiteId`. El
 * resultado medido: 380 px + 14 de gap + 14 de padding = 408 px de mapa
 * regalados a una columna VACÍA en el estado por defecto de la pantalla más
 * usada del producto (320 + 10 + 10 = 340 px entre 1280 y 1599).
 *
 * El ancho no cambia; cambia CUÁNDO se aplica. El interruptor es un atributo
 * `data-*` y no una clase modificadora a propósito: `cssContract.test.ts` exige
 * una regla CSS para todo `className` del marcado, y una clase de estado
 * inflaría ese contrato sin aportar nada.
 *
 * [F3] ESTE ARCHIVO VIGILA SOLO LA MITAD CSS. La otra mitad —que `ConsolePage`
 * EMITA el atributo, con la misma condición que monta `<DetailPanel>`— se
 * asserta en `src/features/console/ConsolePage.test.tsx`, porque aquí solo se
 * lee el TEXTO de la hoja y jamás se renderiza el componente. Si alguna de las
 * dos mitades se toca, hay que mirar la otra.
 */
describe("la columna de detalle solo existe cuando hay detalle que mostrar", () => {
  it("`.soc-shell` pelado es UNA columna: sin sitio en foco no se reserva nada", () => {
    // [F4] ESTA es la aserción que la reauditoría volvió a demostrar vacía, y la
    // más grave de las cinco: con `declValue` leyendo el PRIMER valor bastaba
    // añadir un segundo `.soc-shell { grid-template-columns: minmax(0,1fr)
    // var(--tk-detail-w) }` MÁS ABAJO en la base para reintroducir literalmente
    // el bug de T-2.64.c —408 px de mapa regalados a una columna vacía— con la
    // suite entera en verde. El navegador aplica el último; ahora el test también.
    const columnas = declValue(rulesFor(ALL_BASE, ".soc-shell"), "grid-template-columns");
    expect(columnas, ".soc-shell no declara columnas").not.toBeNull();
    expect(columnas, "la pista del detalle vuelve a estar reservada en el estado por defecto").toBe(
      "minmax(0, 1fr)",
    );
  });

  it('`[data-detail="open"]` es lo ÚNICO que abre la segunda pista', () => {
    expect(
      declValue(rulesFor(ALL_BASE, '.soc-shell[data-detail="open"]'), "grid-template-columns"),
    ).toBe("minmax(0, 1fr) var(--tk-detail-w)");
  });

  it("y son los DOS ÚNICOS selectores de las tres hojas que deciden ese ancho", () => {
    // [F4] `rulesFor` agrupa por selector EXACTO. Eso es justo lo que permite
    // comparar valores sin escribir un motor de cascada —dentro de un grupo la
    // especificidad es constante, así que basta el orden— y es también su punto
    // ciego: `.soc-app .soc-shell` (0,2,0) le gana a `.soc-shell` (0,1,0) en el
    // navegador y no entra en NINGÚN grupo que este archivo mire. La reauditoría
    // lo confirmó: con esa regla añadida, la pista de 380 px volvía a reservarse
    // siempre y los 67 tests seguían verdes.
    //
    // No se arregla comparando valores; se arregla prohibiendo al tercero en
    // discordia. El ancho del shell lo deciden estos dos selectores y nadie más,
    // así que cualquier otro que se meta —con más especificidad, con menos, o
    // desde otra hoja— sale por aquí.
    const decisores = new Set<string>();
    for (const [, selectors, body] of ALL.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
      if (declValues(body, "grid-template-columns").length === 0) continue;
      for (const parte of selectors.split(",").map((s) => s.trim().replace(/\s+/g, " "))) {
        if (/\.soc-shell(?![\w-])/.test(parte)) decisores.add(parte);
      }
    }
    expect([...decisores].sort()).toEqual([".soc-shell", '.soc-shell[data-detail="open"]']);

    // Y el atajo esquiva el contrato entero: `grid-template: auto / minmax(0,1fr)
    // 380px` fija las columnas sin escribir nunca `grid-template-columns`, así
    // que se escaparía de TODAS las igualdades de este archivo y también del
    // barrido de `1fr` desnudo. Hoy las hojas no lo usan (medido); se prohíbe
    // para que siga siendo verdad. Se lista al ofensor en vez de negar a secas:
    // un `.toEqual([])` dice QUÉ se coló, un `.not.toMatch` solo que algo lo hizo.
    const atajos = (ALL.match(/(?:^|[;{}\n])\s*grid(?:-template)?\s*:[^;{}]*/g) ?? []).map((d) =>
      d.trim(),
    );
    expect(atajos, "el atajo `grid`/`grid-template` esquiva el contrato de rejas").toEqual([]);
  });

  it("entre 1280 y 1599 el recorte a 320 px cuelga del MISMO selector con atributo", () => {
    // Si el 320 px se quedara en `.soc-shell` pelado, esa regla (0,1,0) perdería
    // contra `.soc-shell[data-detail="open"]` (0,2,0) de la base y el detalle
    // volvería a medir 380 px en el rango donde justamente no cabe.
    const medio = mediaBody(SOC, "(max-width: 1599px)");
    expect(
      declValue(rulesFor(medio, '.soc-shell[data-detail="open"]'), "grid-template-columns"),
    ).toBe("minmax(0, 1fr) 320px");
    expect(
      declValue(rulesFor(medio, ".soc-shell"), "grid-template-columns"),
      "el ancho del detalle no puede vivir en el selector sin atributo: lo pisa la base",
    ).toBeNull();
  });

  it("bajo 1280 el cajón gana también con el detalle ABIERTO", () => {
    // Misma trampa de especificidad, al revés: `.soc-shell { minmax(0,1fr) }`
    // dentro de la @media no basta para revertir la base con atributo.
    //
    // [F3] ESTA es la aserción que el auditor demostró vacía: con
    // `/grid-template-columns:\s*minmax\(0, 1fr\)\s*;?/` el valor
    // `minmax(0, 1fr) 320px` pasaba —el `;?` casa vacío al llegar al `3`— y los
    // 67 tests del archivo seguían verdes con la segunda pista reservada bajo
    // 1280, donde el detalle ya es cajón fijo: una franja VACÍA robándole ancho
    // al mapa. Con igualdad no hay dónde esconder la pista de más.
    const angosto = mediaBody(SOC, "(max-width: 1279px)");
    expect(
      declValue(rulesFor(angosto, '.soc-shell[data-detail="open"]'), "grid-template-columns"),
      "bajo 1280 el shell abierto reserva una segunda pista para un cajón que ya no vive en la reja",
    ).toBe("minmax(0, 1fr)");
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

describe("reglas muertas — la @media que nunca gana", () => {
  // [T-2.58] `soc.css` llevaba desde T-1.54 un bloque
  // `@media (max-width:1100px) { .mt,.fleet,.audit,.triage { overflow-y: visible } }`
  // que jamás se aplicó: `main.tsx` importa `soc-tabs.css` DESPUÉS, y allí esos
  // mismos selectores declaran `overflow-y: auto` sin media query. Una @media no
  // añade especificidad, así que la regla posterior gana también dentro del rango.
  //
  // Medido en navegador a 640/900/1100 px: `auto` en los tres. El daño no es
  // visual hoy, es que la hoja DOCUMENTA una intención que el navegador ignora —
  // y el siguiente que lea el comentario creerá que la pantalla estrecha se
  // comporta de un modo en el que no se comporta.
  const CONTENEDORES = [".mt", ".fleet", ".audit", ".triage", ".bld"];

  it.each(CONTENEDORES)(
    "%s: si soc-tabs.css lo hace scrolleable, soc.css no puede fingir que lo revierte",
    (selector) => {
      // [F4] Aquí había un `if (!tabsScrollea) return;` — un gate que se apaga a
      // sí mismo EN SILENCIO. Y la comprobación se había debilitado a
      // `.includes("auto")`, que es igualdad exacta contra el valor extraído: con
      // `overflow-y: auto !important` en soc-tabs.css el gate se daba por no
      // aplicable y la regla muerta de soc.css pasaba inadvertida. Hoy queda
      // enmascarado porque otra aserción del archivo se pone roja ante ese
      // `!important`, pero eso es suerte, no diseño.
      //
      // Se cierra por los dos lados: `declarations()` ya separa `!important` del
      // valor, y la premisa se ASSERTA en vez de saltarse. Medido el 2026-08-05:
      // los CINCO contenedores declaran `overflow-y: auto` en soc-tabs.css. Si
      // uno deja de hacerlo, esto falla y hay que decidir a mano si sale de la
      // lista — que es justo la conversación que un `return` mudo se salta.
      const tabsScrollea = declValues(rulesFor(TABS, selector), "overflow-y").some((v) =>
        /^auto\b/.test(v),
      );
      expect(
        tabsScrollea,
        `${selector}: soc-tabs.css ya no lo hace scrolleable. El gate se quedaría ` +
          `mudo: revísalo y sácalo de CONTENEDORES a conciencia, no por omisión.`,
      ).toBe(true);

      expect(
        declValues(rulesFor(SOC, selector), "overflow-y"),
        `${selector}: soc.css declara overflow-y sobre un contenedor que ` +
          `soc-tabs.css ya hizo scrolleable. Como soc-tabs.css se importa después ` +
          `y sin media query, esa declaración NO se aplica nunca — es letra muerta ` +
          `que miente sobre el comportamiento real.`,
      ).toEqual([]);
    },
  );
});

describe("un botón apagado tiene que PARECER apagado", () => {
  // [T-2.59] `CONFIRMAR ACUSE` se pintaba deshabilitado con `opacity: 1`,
  // `cursor: pointer` y el CIAN PLENO de llamada a la acción: idéntico a cuando
  // sí se puede pulsar. Medido en navegador: `disabled=true` con
  // `background: rgb(0,191,255)`.
  //
  // Es el botón más consecuente del producto —el acuse de un incidente
  // sísmico—: parecer armado sin estarlo se lee como "el sistema no responde",
  // que es justo lo que nadie debe pensar en mitad de una emergencia. El resto
  // del repo ya tenía el idioma (`.fleet-card__diag:disabled`,
  // `.mt__new-submit:disabled`, `.vis-form__submit:disabled`…); faltaba aquí.
  it(".soc-confirm apagado baja opacidad y cambia el cursor", () => {
    const apagado = rulesFor(ALL_BASE, ".soc-confirm:disabled");
    expect(apagado, ".soc-confirm no tiene regla :disabled").not.toBe("");
    // Rango, no igualdad —cualquier fracción sirve—, pero anclado al valor
    // completo: sin el `^…$` lo satisfacía cualquier otra propiedad terminada en
    // `opacity` (`fill-opacity`, `stroke-opacity`), que no apaga nada.
    expect(
      declValue(apagado, "opacity"),
      "un botón apagado no puede quedarse a opacidad plena",
    ).toMatch(/^0?\.\d+$/);
    expect(declValue(apagado, "cursor"), "el cursor no puede seguir invitando a pulsar").toBe(
      "not-allowed",
    );
  });
});
