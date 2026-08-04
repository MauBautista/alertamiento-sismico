import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * [T-2.55] Contrato CLASE↔REGLA: ningún `className` del marcado puede quedarse
 * sin una sola regla en las hojas.
 *
 * Este test existe por un defecto REAL y repetido: T-1.72 entregó el alta de
 * clientes y T-1.73 la tarjeta de visibilidad con el marcado completo y CERO
 * estilos. Nadie lo notó durante semanas porque en jsdom todo "existe" y en el
 * navegador el formulario simplemente se veía con los defaults del sistema
 * dentro de una consola industrial oscura — feo, no roto. Un test de componente
 * jamás lo caza: `getByText` pasa igual. La única forma de verlo sin ojos
 * humanos es cruzar las dos fuentes.
 *
 * Al escribirlo aparecieron SIETE clases más en la misma situación (bloques
 * `.acuse`, `.inspection`, `.postevent`, `.timeline`, `.users`, más
 * `.soc-map__legend--layers` y `.fleet-card__completeness`). Se arreglaron
 * escribiendo su regla: relajar el test habría sido tapar el hallazgo.
 */

const SRC = resolve(process.cwd(), "src");

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) walk(path, out);
    else out.push(path);
  }
  return out;
}

const ALL_FILES = walk(SRC);
/** Marcado de producción. Los `.test.tsx` quedan fuera: consultan clases, no las declaran. */
const TSX = ALL_FILES.filter((f) => f.endsWith(".tsx") && !f.includes(".test."));
const CSS_FILES = ALL_FILES.filter((f) => f.endsWith(".css"));

/* =====================================================================
   LADO CSS — qué clases declara la hoja
   ===================================================================== */

/**
 * Se retiran comentarios Y `url(...)`/`@import` ANTES de escanear:
 *
 * - Los comentarios de estas hojas citan CSS literal con llaves y con nombres
 *   de clase (documentan el porqué de cada regla). Contarlos daría por
 *   declarada una clase que solo se menciona en prosa — el test pasaría en
 *   VERDE FALSO justo en el caso que vigila. Es la misma trampa que documenta
 *   `layoutInvariants.test.ts`.
 * - Sin quitar las URL, `fonts.googleapis.com` y `Geist_wght_.ttf` aportarían
 *   las "clases" `com`, `googleapis` y `ttf`.
 */
function cssText(): string {
  return CSS_FILES.map((f) =>
    readFileSync(f, "utf8")
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/@import[^;]*;/g, "")
      .replace(/url\([^)]*\)/g, ""),
  ).join("\n");
}

const CSS = cssText();
const DEFINED = new Set<string>();
for (const match of CSS.matchAll(/\.(-?[_a-zA-Z][\w-]*)/g)) DEFINED.add(match[1]);

/* =====================================================================
   LADO TSX — qué clases escribe el marcado
   =====================================================================
   No vale un `/className="([^"]*)"/`: la consola compone casi todo con
   template literals (`fleet-card--${pill}`) y el regex ingenuo devuelve basura
   como `${pill}` o `!==`. Se recorre el fuente con un lexer mínimo que sabe
   dónde empieza y acaba cada literal y cada interpolación.
   ===================================================================== */

interface Harvest {
  /** Clases COMPLETAS: deben tener regla exacta. */
  full: Set<string>;
  /** Trozo pegado por la izquierda a una interpolación (`fleet-card--${x}`). */
  prefix: Set<string>;
  /** Trozo pegado por la derecha a una interpolación (`${x}-on`). */
  suffix: Set<string>;
}

const IDENT = /^[A-Za-z][\w-]*$/;
/** Forma de clase BEM: descarta los brazos de un ternario ("ok", "crit"). */
const BEMISH = /[-_]/;

function skipQuoted(src: string, i: number): number {
  const quote = src[i];
  i += 1;
  while (i < src.length) {
    if (src[i] === "\\") {
      i += 2;
      continue;
    }
    if (src[i] === quote) return i + 1;
    i += 1;
  }
  return i;
}

/** `i` apunta a `{`; devuelve el índice DESPUÉS de su `}`. */
function skipBalanced(src: string, i: number): number {
  let depth = 0;
  while (i < src.length) {
    const c = src[i];
    if (c === '"' || c === "'") {
      i = skipQuoted(src, i);
      continue;
    }
    if (c === "`") {
      i = parseTemplate(src, i).end;
      continue;
    }
    if (c === "/" && src[i + 1] === "/") {
      while (i < src.length && src[i] !== "\n") i += 1;
      continue;
    }
    if (c === "/" && src[i + 1] === "*") {
      const end = src.indexOf("*/", i + 2);
      i = end < 0 ? src.length : end + 2;
      continue;
    }
    if (c === "{") depth += 1;
    else if (c === "}") {
      depth -= 1;
      if (depth === 0) return i + 1;
    }
    i += 1;
  }
  return i;
}

interface TemplateChunk {
  text: string;
  gluedLeft: boolean;
  gluedRight: boolean;
}

function parseTemplate(
  src: string,
  start: number,
): { end: number; chunks: TemplateChunk[]; exprs: [number, number][] } {
  let i = start + 1;
  const chunks: TemplateChunk[] = [];
  const exprs: [number, number][] = [];
  let text = "";
  let gluedLeft = false;
  while (i < src.length) {
    const c = src[i];
    if (c === "\\") {
      text += src[i + 1] ?? "";
      i += 2;
      continue;
    }
    if (c === "`") {
      chunks.push({ text, gluedLeft, gluedRight: false });
      return { end: i + 1, chunks, exprs };
    }
    if (c === "$" && src[i + 1] === "{") {
      chunks.push({ text, gluedLeft, gluedRight: true });
      text = "";
      gluedLeft = true;
      const end = skipBalanced(src, i + 1);
      exprs.push([i + 2, end - 1]);
      i = end;
      continue;
    }
    text += c;
    i += 1;
  }
  chunks.push({ text, gluedLeft, gluedRight: false });
  return { end: i, chunks, exprs };
}

/**
 * `depth` 0 = literal directo del atributo (`cls("a b", x)`); >0 = dentro de una
 * interpolación, donde solo se aceptan tokens con forma de clase.
 */
function harvest(src: string, from: number, to: number, depth: number, sink: Harvest): void {
  let i = from;
  while (i < to) {
    const c = src[i];
    if (c === "/" && src[i + 1] === "/") {
      while (i < to && src[i] !== "\n") i += 1;
      continue;
    }
    if (c === "/" && src[i + 1] === "*") {
      const end = src.indexOf("*/", i + 2);
      i = end < 0 ? to : end + 2;
      continue;
    }
    if (c === '"' || c === "'") {
      const end = skipQuoted(src, i);
      for (const token of src.slice(i + 1, end - 1).split(/\s+/)) {
        if (!IDENT.test(token)) continue;
        if (depth === 0 || BEMISH.test(token)) sink.full.add(token);
      }
      i = end;
      continue;
    }
    if (c === "`") {
      const tpl = parseTemplate(src, i);
      for (const chunk of tpl.chunks) {
        const tokens = chunk.text.split(/\s+/).filter(Boolean);
        const startsGlued = chunk.gluedLeft && !/^\s/.test(chunk.text);
        const endsGlued = chunk.gluedRight && !/\s$/.test(chunk.text);
        tokens.forEach((token, k) => {
          const isLast = k === tokens.length - 1 && endsGlued;
          const isFirst = k === 0 && startsGlued;
          if (!IDENT.test(token) && !isLast) return;
          if (isLast) sink.prefix.add(token);
          else if (isFirst) sink.suffix.add(token);
          else if (depth === 0 || BEMISH.test(token)) sink.full.add(token);
        });
      }
      for (const [s, e] of tpl.exprs) harvest(src, s, e, depth + 1, sink);
      i = tpl.end;
      continue;
    }
    i += 1;
  }
}

function classNamesOf(src: string): Harvest {
  const sink: Harvest = { full: new Set(), prefix: new Set(), suffix: new Set() };
  const re = /\bclassName\s*=\s*/g;
  let match: RegExpExecArray | null;
  while ((match = re.exec(src)) !== null) {
    const i = match.index + match[0].length;
    const c = src[i];
    if (c === '"' || c === "'") {
      const end = skipQuoted(src, i);
      for (const token of src.slice(i + 1, end - 1).split(/\s+/)) {
        if (IDENT.test(token)) sink.full.add(token);
      }
    } else if (c === "{") {
      harvest(src, i + 1, skipBalanced(src, i) - 1, 0, sink);
    }
  }
  return sink;
}

/* =====================================================================
   EL CONTRATO
   ===================================================================== */

describe("contrato clase↔regla — un className sin CSS es una pantalla sin estilo", () => {
  it("el escaneo encuentra marcado y hojas (si esto falla, el resto miente)", () => {
    expect(TSX.length).toBeGreaterThan(50);
    expect(CSS_FILES.length).toBeGreaterThanOrEqual(4);
    expect(DEFINED.size).toBeGreaterThan(400);
  });

  it("no confunde prosa con declaración: los comentarios se retiran antes de escanear", () => {
    // `soc.css` documenta en un comentario la fuga `--soc-*` que T-2.55 cerró, y
    // `cssContract` se cita a sí mismo en varios. Ninguna clase puede entrar por ahí.
    expect(CSS).not.toContain("[T-2.55]");
  });

  it.each(TSX.map((f) => [relative(SRC, f), f] as const))(
    "%s: cada className tiene regla",
    (_label, file) => {
      const found = classNamesOf(readFileSync(file, "utf8"));
      const defined = [...DEFINED];

      const missing = [...found.full].filter((c) => !DEFINED.has(c));
      expect(
        missing,
        `clases sin ninguna regla CSS: ${missing.join(", ")}. ` +
          "Escribe su regla — no la quites de la lista.",
      ).toEqual([]);

      // Un trozo pegado a una interpolación (`fleet-card--${pill}`) no se puede
      // resolver estáticamente: se exige que exista la FAMILIA, que es lo que
      // detecta un modificador entero sin estilar.
      const orphanPrefix = [...found.prefix].filter(
        (c) => !DEFINED.has(c) && !defined.some((d) => d.startsWith(c)),
      );
      expect(
        orphanPrefix,
        `prefijos de clase sin ninguna familia en el CSS: ${orphanPrefix.join(", ")}`,
      ).toEqual([]);

      const orphanSuffix = [...found.suffix].filter(
        (c) => !DEFINED.has(c) && !defined.some((d) => d.endsWith(c)),
      );
      expect(
        orphanSuffix,
        `sufijos de clase sin ninguna familia en el CSS: ${orphanSuffix.join(", ")}`,
      ).toEqual([]);
    },
  );
});

describe("el propio escáner — sin esto el contrato podría estar leyendo aire", () => {
  const scan = (src: string) => classNamesOf(src);

  it("atributo literal simple", () => {
    expect([...scan('<div className="soc-card soc-card--wide" />').full]).toEqual([
      "soc-card",
      "soc-card--wide",
    ]);
  });

  it("template: el trozo pegado a la interpolación es PREFIJO, no clase", () => {
    const out = scan("<div className={`fleet-card fleet-card--${pill}`} />");
    expect([...out.full]).toEqual(["fleet-card"]);
    expect([...out.prefix]).toEqual(["fleet-card--"]);
  });

  it("template: lo separado por espacio de la interpolación sí es clase completa", () => {
    const out = scan("<div className={`soc-dot ${on ? \"soc-dot--pulse\" : ''}`} />");
    expect(out.full.has("soc-dot")).toBe(true);
    expect(out.full.has("soc-dot--pulse")).toBe(true);
  });

  it("dentro de `${}` los brazos que no tienen forma de clase se ignoran", () => {
    const out = scan('<div className={`soc-pill soc-pill--${ok ? "ok" : "crit"}`} />');
    expect(out.full.has("ok")).toBe(false);
    expect(out.full.has("crit")).toBe(false);
    expect(out.prefix.has("soc-pill--")).toBe(true);
  });

  it("expresión con llamada: los literales de `cls(...)` son clases completas", () => {
    const out = scan('<div className={cls("soc-stateframe soc-stateframe--status", extra)} />');
    expect([...out.full].sort()).toEqual(["soc-stateframe", "soc-stateframe--status"]);
  });

  it("no se traga los operadores del ternario como si fueran clases", () => {
    const out = scan('<td className={`soc-mono ${sev !== "info" ? "soc-table__pga" : ""}`} />');
    expect([...out.full].sort()).toEqual(["soc-mono", "soc-table__pga"]);
  });
});
