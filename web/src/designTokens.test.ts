// T-2.01 — paridad del paquete de tokens: la consola migró a
// @takab/design-tokens SIN cambio visual. Este test ancla (1) que el CSS
// generado ≡ tokens.json, (2) los valores pre-migración (los que vivían en
// web/src/styles/colors_and_type.css hasta 1f3ab7f), (3) el drift gate del
// generador y (4) los contratos semánticos compartidos con el móvil.
import { execFileSync } from "node:child_process";
import { readdirSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";

import {
  cssVariables,
  DERIVED_STATE_PILL,
  INCIDENT_SEVERITY,
  KIND_COLOR,
  tokens,
  toNumber,
  UNKNOWN_DERIVED_STATE_KIND,
  UNKNOWN_SEVERITY_KIND,
} from "@takab/design-tokens";
import { describe, expect, it } from "vitest";

const require_ = createRequire(import.meta.url);
const pkgDir = path.dirname(require_.resolve("@takab/design-tokens/package.json"));
const tokensCss = readFileSync(path.join(pkgDir, "css", "tokens.css"), "utf8");

/** Parsea las declaraciones `--tk-*: valor;` del :root generado. */
function parseCssVariables(source: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [, name, value] of source.matchAll(/^\s*(--tk-[a-z0-9-]+):\s*(.+?);$/gm)) {
    out[name] = value;
  }
  return out;
}

describe("design tokens · paridad css ↔ json", () => {
  it("css/tokens.css contiene exactamente las variables de tokens.json", () => {
    expect(parseCssVariables(tokensCss)).toEqual(cssVariables);
  });

  it("el generador está en sincronía (drift gate)", () => {
    // Lanza el --check del paquete: si alguien editó el css a mano o cambió
    // tokens.json sin regenerar, esto revienta.
    expect(() =>
      execFileSync(process.execPath, [path.join("scripts", "gen-css.mjs"), "--check"], {
        cwd: pkgDir,
      }),
    ).not.toThrow();
  });
});

describe("design tokens · anclas de identidad visual (valores pre-migración)", () => {
  // Muestras de cada grupo, byte a byte contra lo que la consola servía antes
  // de T-2.01. Si un valor cambia aquí, ES un cambio visual deliberado.
  it.each([
    ["--tk-navy-700", "#1A3E62"],
    ["--tk-cyan", "#00BFFF"],
    ["--tk-status-normal", "#00E676"],
    ["--tk-status-warning", "#FFC107"],
    ["--tk-status-critical", "#FF5252"],
    ["--tk-fg-1", "#F0F2F5"],
    ["--tk-surface-0", "#0E2336"],
    ["--tk-border", "rgba(240, 242, 245, 0.08)"],
    ["--tk-text-base", "14px"],
    ["--tk-radius-pill", "999px"],
    ["--tk-dur-base", "180ms"],
    ["--tk-focus-ring", "0 0 0 2px var(--tk-navy-900), 0 0 0 4px var(--tk-cyan)"],
  ] as const)("%s = %s", (name, value) => {
    expect(cssVariables[name]).toBe(value);
  });

  it("la fuente de datos técnicos sigue siendo JetBrains Mono", () => {
    expect(cssVariables["--tk-font-mono"]).toContain("'JetBrains Mono'");
    expect(tokens.font.mono).toBe(cssVariables["--tk-font-mono"]);
  });

  it("la vista estructurada resuelve a los MISMOS valores que las CSS vars", () => {
    expect(tokens.color.status.critical).toBe(cssVariables["--tk-status-critical"]);
    expect(tokens.color.surface[0]).toBe(cssVariables["--tk-surface-0"]);
    expect(tokens.fontSize["5xl"]).toBe(cssVariables["--tk-text-5xl"]);
    expect(toNumber(tokens.fontSize.base)).toBe(14);
  });
});

/* =====================================================================
   [T-2.64.b] CONTRASTE — un rótulo que no se lee no es información
   ===================================================================== */

/**
 * Luminancia relativa de un `#RRGGBB` según WCAG 2.x (§ "relative luminance").
 * Solo colores SÓLIDOS: un token traslúcido no tiene contraste propio, lo
 * hereda de lo que tenga debajo, y aquí se afirma sobre pares deterministas.
 */
function relativeLuminance(hex: string): number {
  const match = /^#([0-9a-fA-F]{6})$/.exec(hex.trim());
  if (match === null) throw new Error(`no es un color sólido de 6 dígitos: ${hex}`);
  const rgb = match[1];
  const channels = [0, 2, 4].map((i) => Number.parseInt(rgb.slice(i, i + 2), 16) / 255);
  const linear = channels.map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
}

/** Razón de contraste WCAG: `(L_claro + 0.05) / (L_oscuro + 0.05)`. */
function contrastRatio(fg: string, bg: string): number {
  const a = relativeLuminance(fg);
  const b = relativeLuminance(bg);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

/** Umbral AA para texto normal (WCAG 1.4.3). No hay AA Large aquí: los grises
 * de la consola visten rótulos de 8–10 px, que es lo contrario de "texto
 * grande" (18 pt / 14 pt en negrita). */
const AA = 4.5;

/**
 * Los fondos REALES de la consola. `--tk-surface-3` queda fuera a propósito:
 * está definido en el paquete pero NINGUNA hoja lo usa como fondo — el test de
 * más abajo lo vigila. Si algún día se estrena, entra al contrato y el gris
 * tendrá que subir otra vez (sobre s3, `#8A9CB1` da 3.97:1).
 */
const FONDOS = ["--tk-surface-0", "--tk-surface-1", "--tk-surface-2"] as const;
const TEXTOS = ["--tk-fg-1", "--tk-fg-2", "--tk-fg-3"] as const;

describe("design tokens · contraste WCAG AA (rótulos de 8–10 px)", () => {
  it.each(TEXTOS.flatMap((fg) => FONDOS.map((bg) => [fg, bg] as const)))(
    "%s sobre %s alcanza AA",
    (fg, bg) => {
      const ratio = contrastRatio(cssVariables[fg], cssVariables[bg]);
      expect(
        ratio,
        `${fg} (${cssVariables[fg]}) sobre ${bg} (${cssVariables[bg]}) = ` +
          `${ratio.toFixed(2)}:1 — AA exige ${AA}:1 para texto normal`,
      ).toBeGreaterThanOrEqual(AA);
    },
  );

  it("la jerarquía tonal sobrevive al arreglo: fg-2 sigue por encima de fg-3", () => {
    // El riesgo de subir el terciario es aplastarlo contra el secundario y
    // perder el ESCALÓN: tres niveles que se leen igual no son tres niveles.
    const fg2 = contrastRatio(cssVariables["--tk-fg-2"], cssVariables["--tk-surface-1"]);
    const fg3 = contrastRatio(cssVariables["--tk-fg-3"], cssVariables["--tk-surface-1"]);
    expect(fg2 / fg3, `fg-2 ${fg2.toFixed(2)} vs fg-3 ${fg3.toFixed(2)}`).toBeGreaterThan(1.4);
  });

  it("`--tk-fg-disabled` está EXENTO a propósito y sigue por debajo de AA", () => {
    // WCAG 1.4.3 excluye explícitamente el texto de un control deshabilitado.
    // La exención se afirma en positivo para que nadie la "arregle" por error:
    // subir este token haría que un botón apagado parezca pulsable, que es el
    // defecto que T-2.59 cerró en `.soc-confirm`.
    for (const bg of FONDOS) {
      const ratio = contrastRatio(cssVariables["--tk-fg-disabled"], cssVariables[bg]);
      expect(ratio, `--tk-fg-disabled sobre ${bg} = ${ratio.toFixed(2)}:1`).toBeLessThan(AA);
    }
  });

  it("`--tk-surface-3` NO es fondo de nadie — por eso puede quedar fuera del contrato", () => {
    // Guardia de la EXCLUSIÓN, no del token. Sin esto la exención se pudre en
    // silencio: el día que alguien estrene s3 como fondo, los grises que este
    // test da por buenos caerían a 3.97:1 y nadie se enteraría.
    const dir = path.resolve(process.cwd(), "src", "styles");
    const ofensores = readdirSync(dir)
      .filter((name) => name.endsWith(".css"))
      .flatMap((name) => {
        const css = readFileSync(path.join(dir, name), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
        return [...css.matchAll(/background(?:-color)?\s*:[^;}]*--tk-surface-3[^;}]*/g)].map(
          (m) => `${name}: ${m[0].trim()}`,
        );
      });
    expect(
      ofensores,
      `--tk-surface-3 se estrenó como fondo. Añádelo a FONDOS y vuelve a ` +
        `calcular los grises:\n${ofensores.join("\n")}`,
    ).toEqual([]);
  });
});

/* =====================================================================
   [T-6.09] EL CONTRATO SOBRE LOS FONDOS QUE LA CONSOLA **COMPONE**
   =====================================================================
   El bloque de arriba mide tres fondos PLANOS. La consola no pinta tres:
   pinta esos tres y, encima, un tinte por cada estado —`--tk-status-*-08` y
   `--tk-status-*-15`, `--tk-cyan-08`— que es exactamente donde va el texto de
   ese estado. Ocho fondos reales contra tres bajo contrato, y la diferencia no
   era teórica: axe sin filtrar sobre las seis pantallas con el seed de
   demostración devolvió 44 nodos `color-contrast`, y 36 de ellos eran el mismo
   rojo anclado (`#FF5252`) haciendo de TINTA sobre su propio tinte —3.35:1 en
   una fila seleccionada de `/triage`, 3.76:1 en la píldora de la tarjeta
   crítica de flota, 4.23:1 en los enlaces de esa misma tarjeta.

   El rojo NO se mueve: es un ancla de identidad y lo defiende el bloque de
   anclas de arriba. Lo que se separa es el OFICIO: `--tk-status-critical`
   dibuja (bordes, barras, rellenos, el punto del mapa) y
   `--tk-status-critical-text` escribe. Los otros tres estados ya pasaban con
   holgura y por eso no estrenan tinta propia — una tinta por estado "por
   simetría" sería tres tokens que nadie necesita.
   ===================================================================== */

/** `rgba(r, g, b, a)` o `#RRGGBB` → [r, g, b, a]. */
function parseColor(value: string): [number, number, number, number] {
  if (value.startsWith("#")) {
    const [r, g, b] = [1, 3, 5].map((i) => parseInt(value.slice(i, i + 2), 16));
    return [r, g, b, 1];
  }
  const partes = /rgba?\(([^)]+)\)/.exec(value)?.[1].split(",").map(Number);
  if (partes === undefined) throw new Error(`color no reconocido: ${value}`);
  return [partes[0], partes[1], partes[2], partes[3] ?? 1];
}

/** Compone `fg` (con alfa) sobre `bg` opaco: lo que el navegador acaba pintando. */
function componer(fg: string, bg: string): string {
  const [r, g, b, a] = parseColor(fg);
  const base = parseColor(bg);
  const mezcla = [r, g, b].map((c, i) => Math.round(c * a + base[i] * (1 - a)));
  return `#${mezcla.map((c) => c.toString(16).padStart(2, "0")).join("")}`;
}

/** Ratio de contraste contra un fondo COMPUESTO (tinte sobre superficie). */
function ratioSobreTinte(ink: string, tinte: string, surface: string): number {
  return contrastRatio(ink, componer(tinte, surface));
}

/**
 * Los pares que la consola PINTA: cada estado escribe sobre su propio tinte, y
 * el tinte se compone sobre cualquiera de los tres fondos planos. No hay más
 * combinaciones porque no hay más tintes: el conjunto sale de `tokens.json`.
 */
const TINTA_SOBRE_SU_TINTE = [
  ["--tk-status-critical-text", "--tk-status-critical-08"],
  ["--tk-status-critical-text", "--tk-status-critical-15"],
  ["--tk-status-warning", "--tk-status-warning-08"],
  ["--tk-status-warning", "--tk-status-warning-15"],
  ["--tk-status-normal", "--tk-status-normal-08"],
  ["--tk-status-normal", "--tk-status-normal-15"],
  ["--tk-cyan", "--tk-cyan-08"],
  ["--tk-cyan", "--tk-cyan-15"],
] as const;

describe("[T-6.09] contraste sobre los fondos COMPUESTOS, no solo los tres planos", () => {
  it.each(
    TINTA_SOBRE_SU_TINTE.flatMap(([ink, tinte]) =>
      FONDOS.map((surface) => [ink, tinte, surface] as const),
    ),
  )("%s sobre %s compuesto en %s alcanza AA", (ink, tinte, surface) => {
    const ratio = ratioSobreTinte(cssVariables[ink], cssVariables[tinte], cssVariables[surface]);
    expect(
      ratio,
      `${ink} sobre ${tinte}/${surface} (= ${componer(cssVariables[tinte], cssVariables[surface])}) ` +
        `= ${ratio.toFixed(2)}:1 — AA exige ${AA}:1`,
    ).toBeGreaterThanOrEqual(AA);
  });

  it("NINGÚN tinte es SEGURO para el gris terciario; el secundario lo es siempre", () => {
    // La regla de la que salen los arreglos de esta ficha, afirmada en
    // positivo y DERIVADA del paquete: se recorren todos los tintes (`-08`,
    // `-15`) sobre los tres fondos, no una lista escrita a mano.
    //
    // «Seguro» quiere decir *en cualquier fondo*, que es lo único que se puede
    // prometer al escribir una hoja: una clase no sabe sobre qué superficie la
    // van a montar. Sobre el navy más oscuro algún tinte deja pasar al
    // terciario por poco (4.72–5.29:1); sobre `--tk-surface-2` el mismo tinte
    // lo hunde a 3.20. El secundario aguanta los 24 pares (4.99:1 el peor).
    //
    // Por eso el arreglo va donde está el tinte —la tinta sube a secundaria— y
    // NO en el token: para que el terciario pasara sobre un tinte habría que
    // llevarlo a `#98AABE`, y ahí el escalón fg-2/fg-3 baja de 1.56 a 1.32,
    // por debajo del 1.4 que exige el test de la jerarquía. Tres niveles que
    // se leen igual no son tres niveles.
    const tintes = Object.keys(cssVariables).filter(
      (n) =>
        /-(08|15)$/.test(n) && cssVariables[n as keyof typeof cssVariables].startsWith("rgba("),
    ) as Array<keyof typeof cssVariables>;
    expect(
      tintes.length,
      "el paquete se quedó sin tintes: este censo dejó de mirar nada",
    ).toBeGreaterThan(5);

    const seguros: string[] = [];
    const secundarioCae: string[] = [];
    for (const tinte of tintes) {
      let peor = Infinity;
      for (const surface of FONDOS) {
        const fondo = componer(cssVariables[tinte], cssVariables[surface]);
        peor = Math.min(peor, contrastRatio(cssVariables["--tk-fg-3"], fondo));
        const r2 = contrastRatio(cssVariables["--tk-fg-2"], fondo);
        if (r2 < AA) secundarioCae.push(`${tinte}/${surface} = ${r2.toFixed(2)}`);
      }
      if (peor >= AA) seguros.push(`${tinte} (peor caso ${peor.toFixed(2)})`);
    }
    expect(
      seguros,
      "un tinte pasó a ser seguro para el terciario en los tres fondos. Si es " +
        "real, el arreglo de esta ficha (subir la tinta a secundaria bajo " +
        `tinte) tiene una excepción que hay que escribir:\n${seguros.join("\n")}`,
    ).toEqual([]);
    expect(
      secundarioCae,
      `el gris SECUNDARIO dejó de ser la salida bajo tinte:\n${secundarioCae.join("\n")}`,
    ).toEqual([]);
  });

  it("el rojo ANCLADO se queda como está: dibuja, y por eso NO tiene que pasar AA", () => {
    // Afirmado en positivo para que nadie "arregle" el ancla: `#FF5252` sobre
    // `--tk-surface-2` da 4.10:1 y ese es justamente el motivo de que exista
    // una tinta aparte. Si alguien aclarara el ancla, este test lo diría.
    expect(cssVariables["--tk-status-critical"]).toBe("#FF5252");
    expect(
      contrastRatio(cssVariables["--tk-status-critical"], cssVariables["--tk-surface-2"]),
    ).toBeLessThan(AA);
  });

  it("la tinta crítica es OTRO tono del mismo rojo, no un rojo distinto", () => {
    // Que pase AA no basta: si la tinta derivara a naranja o a rosa, la
    // consola tendría dos "rojos de estado" y el operador vería dos cosas.
    const [r, g, b] = parseColor(cssVariables["--tk-status-critical-text"]);
    const [ar, ag] = parseColor(cssVariables["--tk-status-critical"]);
    expect(r, "la tinta crítica dejó de ser roja saturada").toBeGreaterThanOrEqual(ar);
    expect(Math.abs(g - b), `g=${g} b=${b}: el rojo se está yendo a un tono`).toBeLessThanOrEqual(
      12,
    );
    expect(g, "la tinta es MÁS CLARA que el ancla, ese es todo el cambio").toBeGreaterThan(ag);
  });
});

/* =====================================================================
   [T-6.09] CENSO DE OFICIO: quién DIBUJA y quién ESCRIBE
   =====================================================================
   Sin esto la separación dura una tarde. El día que alguien escriba
   `color: var(--tk-status-critical)` en una hoja vuelve el 3.76:1, y no lo
   ve nadie: un rojo sobre un tinte rojo se parece mucho a un rojo que pasa.
   El censo es sobre TODAS las hojas, no sobre las que hoy tienen el defecto.
   ===================================================================== */

/** Hojas de la consola, sin comentarios (un ejemplo en prosa no es una regla). */
function hojasSinComentarios(): Array<{ nombre: string; css: string }> {
  const dir = path.resolve(process.cwd(), "src", "styles");
  return readdirSync(dir)
    .filter((name) => name.endsWith(".css"))
    .map((nombre) => ({
      nombre,
      css: readFileSync(path.join(dir, nombre), "utf8").replace(/\/\*[\s\S]*?\*\//g, ""),
    }));
}

describe("[T-6.09] el rojo anclado DIBUJA; escribir es oficio de la tinta", () => {
  it("ninguna hoja usa `--tk-status-critical` como `color:`", () => {
    const ofensores = hojasSinComentarios().flatMap(({ nombre, css }) =>
      [...css.matchAll(/(?:^|[;{\s])color:\s*var\(--tk-status-critical\)/g)].map((m) => {
        const linea = css.slice(0, m.index).split("\n").length;
        return `${nombre}:${linea}`;
      }),
    );
    expect(
      ofensores,
      `el rojo anclado volvió a hacer de tinta (3.35–4.23:1 sobre sus propios ` +
        `tintes). Usa \`--tk-status-critical-text\`:\n${ofensores.join("\n")}`,
    ).toEqual([]);
  });

  it("tampoco lo usa como tinta desde un `style` de TSX", () => {
    // La hoja no es el único sitio donde se escribe un color: `IncidentTable`
    // pintaba la píldora del canal live y el aviso de canal degradado con un
    // `style` en línea, y ahí el censo de arriba no llega.
    //
    // El barrido acepta la INDIRECCIÓN, que es como estaba escrito el defecto
    // (`const pillColor = … ? "var(--tk-status-critical)"`): busca la palabra
    // `color` y el token dentro de la MISMA sentencia. Dibujar sigue estando
    // permitido —`stroke=`, un mapa de puntos del semáforo— porque en ninguno
    // de esos casos aparece la palabra.
    const dir = path.resolve(process.cwd(), "src");
    const tsx: string[] = [];
    const recorrer = (d: string): void => {
      for (const e of readdirSync(d, { withFileTypes: true })) {
        const full = path.join(d, e.name);
        if (e.isDirectory()) recorrer(full);
        else if (e.name.endsWith(".tsx") && !e.name.includes(".test.")) tsx.push(full);
      }
    };
    recorrer(dir);
    const ofensores = tsx.filter((f) =>
      /color[^;]{0,120}var\(--tk-status-critical\)/s.test(readFileSync(f, "utf8")),
    );
    expect(
      ofensores.map((f) => path.relative(dir, f)),
      "el rojo anclado hace de tinta desde un `style` en línea; usa `--tk-status-critical-text`",
    ).toEqual([]);
  });

  it("una tira de estado SÓLIDA lleva tinta oscura, no blanca", () => {
    // El defecto real: `.soc-alert__strip` —«ALERTA SÍSMICA · PROTÉJASE», el
    // texto más importante de la consola— pintaba `#fff` sobre `#FF5252`:
    // 2.85:1, el peor par del producto. Y axe nunca lo vio porque ninguna
    // corrida tenía una alerta en pantalla. La tira de AVISO ya lo hacía bien
    // (navy sobre ámbar) desde T-6.01; esto extiende esa regla a la de alerta.
    //
    // Solo se miran los bloques que ADEMÁS declaran `color`: una barra o un
    // relleno pintan el estado sin texto encima y no tienen nada que declarar.
    const solido = /background(?:-color)?:\s*var\(--tk-status-(critical|warning|normal)\)/;
    const ofensores = hojasSinComentarios().flatMap(({ nombre, css }) =>
      [...css.matchAll(/([^{}]+)\{([^}]*)\}/g)]
        .filter(([, , cuerpo]) => solido.test(cuerpo) && /(?:^|[;\s])color:/.test(cuerpo))
        .filter(([, , cuerpo]) => !/(?:^|[;\s])color:\s*var\(--tk-navy-900\)/.test(cuerpo))
        .map(([, selector]) => `${nombre}: ${selector.trim()}`),
    );
    expect(
      ofensores,
      `un fondo de estado SÓLIDO con tinta clara no pasa AA (blanco sobre el ` +
        `rojo anclado = 2.85:1). La tinta de una tira sólida es ` +
        `\`var(--tk-navy-900)\`:\n${ofensores.join("\n")}`,
    ).toEqual([]);
  });
});

/* =====================================================================
   [D2] TOKENS FANTASMA — la hoja cita `--tk-algo` que no existe
   ===================================================================== */

/**
 * Guardia DERIVADA, no enumerada.
 *
 * El defecto: `privacy.css` citaba `--tk-warn`, `--tk-accent`, `--tk-danger` y
 * `--tk-bg`, cuatro nombres que NO están en `@takab/design-tokens`. Como todas
 * llevaban fallback (`var(--tk-warn, #d9a441)`), el navegador pintaba el hex
 * duro y el banner quedaba fuera del design system SIN romper nada: el mismo
 * modo de fallo silencioso que la fuga `--soc-*` de T-2.55, que vivió dos ciclos.
 *
 * Enumerar los cuatro nombres de hoy no impide el quinto de mañana: lo que se
 * cruza es el CONJUNTO COMPLETO de `var(--tk-*)` de las hojas contra el
 * CONJUNTO COMPLETO de variables del paquete. Cualquier nombre nuevo que no
 * exista sale por aquí, se llame como se llame.
 *
 * El fallback es justamente lo que hace falta vigilarlo y no lo que lo excusa:
 * sin él la declaración se caería y alguien lo vería; con él la hoja miente en
 * silencio y el tema deja de mandar sobre ese color.
 */
const CSS_DIR = path.resolve(process.cwd(), "src", "styles");

/**
 * Deuda PAGADA (T-2.64.d, 2026-08-13). Aquí vivían las tres de `soc.css` que
 * la guardia sacó sola el 2026-08-08 y que aquel ciclo no podía tocar:
 * `--tk-amber`, `--tk-violet` y `--tk-text-2xs`. Se resolvieron contra el
 * paquete —renombrado el primero a `--tk-status-warning`, y creados
 * `--tk-status-maintenance` y `--tk-text-2xs`— así que la lista queda VACÍA.
 *
 * Se queda como constante vacía, y no como un `[]` suelto en la aserción, por
 * dos razones: la comparación sigue siendo de IGUALDAD (una excepción que
 * puede crecer sola no es una excepción, es un agujero) y el test de más abajo
 * vigila que nadie la vuelva a llenar. La salida legítima de una deuda nueva
 * es arreglarla o ponerla en una ficha, nunca añadir una línea aquí.
 */
const DEUDA_HEREDADA: string[] = [];

function tokensCitadosPorHoja(): string[] {
  const fuera = new Set<string>();
  for (const name of readdirSync(CSS_DIR).filter((f) => f.endsWith(".css"))) {
    // Los comentarios de estas hojas citan CSS literal (documentan el porqué de
    // cada regla): contarlos daría por usado un token que solo aparece en prosa.
    const css = readFileSync(path.join(CSS_DIR, name), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
    for (const [, token] of css.matchAll(/var\(\s*(--tk-[a-z0-9-]+)/g)) {
      if (!(token in cssVariables)) fuera.add(`${name}: ${token}`);
    }
  }
  return [...fuera].sort();
}

describe("design tokens · ninguna hoja cita un token que no existe", () => {
  it("el barrido encuentra hojas y tokens (si esto falla, el resto miente)", () => {
    // Sin esta guarda, un `CSS_DIR` mal resuelto daría cero ofensores y el test
    // pasaría en verde sin mirar nada — que es la forma exacta en que una red
    // deja de ser una red.
    const hojas = readdirSync(CSS_DIR).filter((f) => f.endsWith(".css"));
    expect(hojas.length).toBeGreaterThanOrEqual(4);
    expect(Object.keys(cssVariables).length).toBeGreaterThan(50);
  });

  it("toda `var(--tk-*)` de src/styles resuelve a una variable del paquete", () => {
    const desconocidos = tokensCitadosPorHoja();
    expect(
      desconocidos,
      "hojas que citan un token inexistente (siempre caen al fallback duro y el " +
        "tema deja de mandar). Busca el nombre REAL en " +
        "shared/design-tokens/css/tokens.css — no lo inventes, y no lo añadas a " +
        `DEUDA_HEREDADA:\n${desconocidos.join("\n")}`,
    ).toEqual(DEUDA_HEREDADA);
  });

  it("[T-2.64.d] la lista de excepciones sigue VACÍA — nadie la rellena por la puerta de atrás", () => {
    // Sin esto, el arreglo de T-2.64.d dura hasta el primer atajo: la guardia
    // seguiría siendo derivada y aun así admitiría un token fantasma nuevo con
    // solo añadirle una línea, que es exactamente cómo murió el `--soc-*` de
    // T-2.55. La deuda se paga o se ficha; no se apunta aquí.
    expect(
      DEUDA_HEREDADA,
      "la deuda de tokens fantasma se pagó en T-2.64.d. Si has llegado aquí " +
        "para añadir una línea, para: crea o renombra el token en " +
        "shared/design-tokens/tokens.json.",
    ).toEqual([]);
  });
});

describe("design tokens · contratos semánticos (web ≡ móvil)", () => {
  it("severidad de incidente → tono/etiqueta (contrato de SevTag)", () => {
    expect(INCIDENT_SEVERITY).toEqual({
      critical: { kind: "crit", label: "CRÍTICO" },
      warning: { kind: "warn", label: "ADVERTENCIA" },
      watch: { kind: "warn", label: "VIGILANCIA" },
      info: { kind: "ok", label: "NORMAL" },
    });
    // Desconocido ⇒ ámbar; jamás degradar a ok.
    expect(UNKNOWN_SEVERITY_KIND).toBe("warn");
  });

  it("derived_state → tono del pill (contrato de SiteCard)", () => {
    expect(DERIVED_STATE_PILL).toEqual({
      OPERATIVO: "ok",
      DEGRADADO: "warn",
      "SIN ENLACE": "crit",
    });
    expect(UNKNOWN_DERIVED_STATE_KIND).toBe("warn");
  });

  it("tono → color del semáforo resuelve a los tokens de status", () => {
    expect(KIND_COLOR).toEqual({
      ok: cssVariables["--tk-status-normal"],
      warn: cssVariables["--tk-status-warning"],
      crit: cssVariables["--tk-status-critical"],
    });
  });
});
