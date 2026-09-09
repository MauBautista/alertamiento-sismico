/**
 * [T-6.10] CONTRATO DE MOVIMIENTO SOBRE LA HOJA, no sobre el DOM.
 *
 * `motion.spec.ts` (T-2.56) comprueba en un navegador real que la preferencia
 * apaga lo que anima. Lo que no puede comprobar es la COBERTURA: un selector
 * nuevo con `transition:` no rompe ningún caso de aquel spec, simplemente se
 * queda fuera del interruptor. Medido en la auditoría del 2026-09-06:
 * `prefers-reduced-motion` alcanzaba **2 de 18 transiciones**, y la única que
 * transporta un DATO —la barra de carga del UPS— seguía animando bajo
 * reducción. Un porcentaje de batería que se desliza es un dato que llega
 * tarde a propósito.
 *
 * La forma de cerrarlo sin volver a enumerar: **la duración de toda transición
 * de estas hojas es un token, y la reducción pone esos tokens a cero**. Así el
 * interruptor cubre lo que no se ha escrito todavía. Este archivo vigila las
 * dos mitades del trato —que nadie escriba una duración a mano, y que la
 * anulación cubra todos los tokens que se usan— porque cualquiera de las dos
 * sola es letra muerta.
 */
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

import { cssVariables } from "@takab/design-tokens";
import { describe, expect, it } from "vitest";

const DIR = path.resolve(process.cwd(), "src", "styles");

/** Las hojas de la consola, en el orden en que `main.tsx` las importa. */
const HOJAS = ["colors_and_type.css", "soc.css", "soc-tabs.css", "app.css", "privacy.css"] as const;

/** Texto de una hoja SIN comentarios: un ejemplo en prosa no es una regla. */
function hoja(nombre: string): string {
  return readFileSync(path.join(DIR, nombre), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
}

/** `[{ hoja, linea, decl }]` de todas las declaraciones de una propiedad. */
function declaraciones(prop: "transition" | "animation"): Array<{
  hoja: string;
  linea: number;
  decl: string;
}> {
  const re = new RegExp(`(?:^|[;{\\s])${prop}:\\s*([^;}]+)`, "g");
  return HOJAS.flatMap((nombre) => {
    const css = hoja(nombre);
    return [...css.matchAll(re)].map((m) => ({
      hoja: nombre,
      linea: css.slice(0, m.index).split("\n").length,
      decl: m[1].trim(),
    }));
  });
}

/** Cuerpos de TODOS los bloques `@media (prefers-reduced-motion: reduce)`. */
function bloquesDeReduccion(): string {
  return HOJAS.flatMap((nombre) => {
    const css = hoja(nombre);
    const out: string[] = [];
    const re = /@media[^{]*prefers-reduced-motion:\s*reduce[^{]*\{/g;
    for (const m of css.matchAll(re)) {
      let i = (m.index ?? 0) + m[0].length;
      let nivel = 1;
      const desde = i;
      while (i < css.length && nivel > 0) {
        if (css[i] === "{") nivel++;
        else if (css[i] === "}") nivel--;
        i++;
      }
      out.push(css.slice(desde, i - 1));
    }
    return out;
  }).join("\n");
}

describe("[T-6.10] nada anima una propiedad que nadie eligió", () => {
  it("cero `transition: all` en las hojas de la consola", () => {
    // `all` anima CUALQUIER propiedad futura del selector, incluido un color de
    // estado: el día que un `--crit` entre por hover, el rojo llegaría
    // deslizándose. Una transición se declara sobre lo que se quiere mover.
    const ofensores = declaraciones("transition")
      .filter((d) => /^all\b/.test(d.decl))
      .map((d) => `${d.hoja}:${d.linea} → transition: ${d.decl}`);
    expect(
      ofensores,
      `enumera las propiedades que de verdad se mueven:\n${ofensores.join("\n")}`,
    ).toEqual([]);
  });
});

describe("[T-6.10] toda duración de la consola sale de un token", () => {
  it.each(["transition", "animation"] as const)("`%s:` no lleva ni un número a mano", (prop) => {
    // 14 literales `120ms` duplicaban `--tk-dur-fast`, que vale exactamente eso.
    // Duplicado no es solo desorden: es que la reducción de abajo NO los alcanza.
    const ofensores = declaraciones(prop)
      .filter((d) => /(?:^|[\s(,])[\d.]+m?s\b/.test(d.decl))
      .map((d) => `${d.hoja}:${d.linea} → ${prop}: ${d.decl}`);
    expect(
      ofensores,
      `usa un token de duración (\`--tk-dur-*\`):\n${ofensores.join("\n")}`,
    ).toEqual([]);
  });

  it("y ese token EXISTE en el paquete", () => {
    const citados = new Set(
      [...declaraciones("transition"), ...declaraciones("animation")].flatMap((d) =>
        [...d.decl.matchAll(/var\((--tk-[a-z0-9-]+)/g)].map((m) => m[1]),
      ),
    );
    const fantasma = [...citados].filter((n) => !(n in cssVariables));
    expect(fantasma, "token de movimiento que no existe en @takab/design-tokens").toEqual([]);
  });
});

describe("[T-6.10] la reducción es un interruptor DERIVADO, no una lista", () => {
  const reduccion = bloquesDeReduccion();

  it("hay bloque de reducción (sin esto, todo lo de abajo comprueba aire)", () => {
    expect(reduccion.length).toBeGreaterThan(0);
  });

  it("anula TODOS los tokens de duración que usan las transiciones de la hoja", () => {
    // Esta es la mitad que hace que el interruptor cubra lo que aún no se ha
    // escrito: quien mañana añada `transition: opacity var(--tk-dur-base)` queda
    // dentro sin tocar nada. Si usara un token que la reducción no anula, sale
    // por aquí.
    const usados = new Set(
      declaraciones("transition").flatMap((d) =>
        [...d.decl.matchAll(/var\((--tk-dur-[a-z0-9-]+)/g)].map((m) => m[1]),
      ),
    );
    // Guarda del censo: si un refactor dejara las hojas sin transiciones —o sin
    // tokens en ellas— este bloque pasaría en verde sin mirar nada.
    expect(declaraciones("transition").length, "no quedan transiciones que mirar").toBeGreaterThan(
      10,
    );
    expect(usados.size, "ninguna transición usa un token: el censo mira aire").toBeGreaterThan(0);
    const sinAnular = [...usados].filter(
      (token) => !new RegExp(`${token}:\\s*0m?s\\s*;`).test(reduccion),
    );
    expect(
      sinAnular,
      `la reducción no pone a cero:\n${sinAnular.join("\n")}\n` +
        "Añádelos al `:root` del bloque `prefers-reduced-motion`.",
    ).toEqual([]);
  });

  it("los tokens de la consola se anulan en un `:root`, que es lo único que gana a `tokens.css`", () => {
    // `tokens.css` se importa ANTES (main.tsx) y declara los mismos nombres en
    // `:root`. Una `@media` NO añade especificidad —lo aprendió T-2.59—: lo que
    // hace ganar a esta anulación es el ORDEN. Si alguien la bajara de `:root`
    // a un selector más suelto, o moviera el import, quedaría en letra muerta.
    expect(reduccion).toMatch(/:root\s*\{/);
    const main = readFileSync(path.resolve(process.cwd(), "src", "main.tsx"), "utf8");
    const tokens = main.indexOf("design-tokens/css/tokens.css");
    const soc = main.indexOf("./styles/soc.css");
    expect(tokens, "no se importa el paquete de tokens").toBeGreaterThanOrEqual(0);
    expect(soc, "no se importa soc.css").toBeGreaterThanOrEqual(0);
    expect(tokens, "`soc.css` dejó de entrar DESPUÉS: la anulación no gana").toBeLessThan(soc);
  });

  it("todo selector que ANIMA se apaga: los keyframes no los alcanza el token", () => {
    // Un `animation:` con duración cero seguiría con su `animation-name` puesto
    // y, con `infinite`, algunos motores lo dejan en el primer frame en vez de
    // en el reposo. Los keyframes se apagan por selector Y se les fija el
    // estado de reposo — que es lo que separa «se apaga» de «desaparece».
    const anima = declaraciones("animation").filter((d) => !/^none\b/.test(d.decl));
    expect(anima.length, "no hay animaciones: el censo mira aire").toBeGreaterThan(1);

    const selectoresApagados = reduccion
      .split("}")
      .filter((b) => /animation:\s*none/.test(b))
      .flatMap((b) => (b.split("{")[0] ?? "").split(",").map((s) => s.trim()))
      .filter((s) => s.length > 0);

    // Cada regla que anima tiene que tener su selector en esa lista.
    const sinApagar: string[] = [];
    for (const d of anima) {
      const css = hoja(d.hoja);
      const antes = css.slice(0, css.split("\n").slice(0, d.linea).join("\n").length);
      const selector = (antes.slice(antes.lastIndexOf("}") + 1).split("{")[0] ?? "").trim();
      const cubierto = selectoresApagados.some((s) => s === selector);
      if (!cubierto) sinApagar.push(`${d.hoja}:${d.linea} → ${selector}`);
    }
    expect(
      sinApagar,
      `estos selectores animan y la reducción no los apaga:\n${sinApagar.join("\n")}`,
    ).toEqual([]);
  });
});

describe("[T-6.10 · U-23] un latido es una AFIRMACIÓN, y nunca se escribe a fuego", () => {
  it("`soc-dot--pulse` sale siempre de una condición, jamás de una clase pelada", () => {
    // El defecto de esta ficha era exactamente ese: la clase colgaba de `kind`,
    // que es el veredicto del servidor y no la edad del dato. La forma de que no
    // vuelva no es acordarse: es que escribirla sin condición no compile en
    // verde. Qué condición sea la correcta lo miden los tests del componente;
    // aquí sólo se exige que HAYA una.
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

    const productores: string[] = [];
    const pelados: string[] = [];
    for (const f of tsx) {
      const src = readFileSync(f, "utf8");
      for (const m of src.matchAll(/soc-dot--pulse/g)) {
        const rel = path.relative(dir, f);
        const linea = src.slice(0, m.index).split("\n").length;
        productores.push(`${rel}:${linea}`);
        const ventana = src.slice(Math.max(0, (m.index ?? 0) - 90), (m.index ?? 0) + 40);
        if (!(ventana.includes("?") && ventana.includes(":"))) pelados.push(`${rel}:${linea}`);
      }
    }
    expect(productores.length, "nadie pinta el halo: el censo mira aire").toBeGreaterThan(0);
    expect(
      pelados,
      `el halo se pinta sin condición aquí:\n${pelados.join("\n")}\n` +
        "Un halo que late siempre afirma «llega ahora» sobre cualquier dato.",
    ).toEqual([]);
  });
});
