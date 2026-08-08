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
 * Deuda MEDIDA (2026-08-08) que este ciclo no puede tocar: `soc.css` está en
 * manos de otro trabajo en paralelo. Se listan una a una y la comparación es de
 * IGUALDAD, no de superconjunto: si alguien las arregla, este test se pone rojo
 * y obliga a borrar la línea — una excepción que puede crecer sola no es una
 * excepción, es un agujero. `--tk-amber` es `--tk-status-warning` (mismo
 * #FFC107), `--tk-violet` no tiene equivalente en el paquete y `--tk-text-2xs`
 * tampoco (la escala tipográfica empieza en `--tk-text-xs`).
 */
const DEUDA_HEREDADA = ["soc.css: --tk-amber", "soc.css: --tk-text-2xs", "soc.css: --tk-violet"];

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
