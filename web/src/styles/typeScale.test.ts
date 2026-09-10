// [T-6.12] EL DATO ES LO MÁS GRANDE DE CADA PANTALLA — el contrato de la escala.
//
// Tres cosas se defienden aquí, y las tres salen de una MEDICIÓN, no de un gusto
// (todas hechas el 2026-09-10 contra `make soc-local`, 1920×1080, superadmin):
//
//  1. **El piso.** Convivían TRES pisos sin criterio —8.5, 9 y 9.5 px— en 64
//     declaraciones. Ninguno estaba declarado en ningún sitio: eran números
//     escritos a mano, y por eso nadie podía decir cuál era el correcto. El piso
//     ahora tiene nombre (`--tk-text-min`) y es el escalón MÁS BAJO de la escala:
//     no entra un cuarto número al sistema, se retira la costumbre de inventarlos.
//
//  2. **El nombre de la pantalla no compite con el dato.** Medido: en `/triage`,
//     `/tenants` y `/audit` el rótulo más grande de la pantalla era el `<h1>` con
//     el nombre de la pantalla (26 px), y en `/audit` el segundo más grande medía
//     13 px — la pantalla entera no tenía un dato que mirar. El título baja un
//     escalón por debajo de la métrica y la métrica sube a la que ya usa la
//     alerta para el PGA.
//
//  3. **Un `var()` que no existe no es un tamaño.** `var(--f-ui)` se cita 15
//     veces en `soc-tabs.css` y esa variable NO EXISTE en el paquete de tokens.
//     Un `font:` con una `var()` sin resolver es *invalid at computed-value time*:
//     la declaración ENTERA se cae, tamaño incluido. Medido en el navegador:
//     `.soc-demo-mode__txt` pedía `700 12px/1` y pintaba **16 px / 400**, el
//     heredado del `<body>`. La guarda vieja (`designTokens.test.ts`) sólo miraba
//     las `var(--tk-*)`, así que este agujero le pasaba por debajo. Aquí se cierra
//     para CUALQUIER prefijo.
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";

import { createRequire } from "node:module";

import { describe, expect, it } from "vitest";

const require_ = createRequire(import.meta.url);
const pkgDir = path.dirname(require_.resolve("@takab/design-tokens/package.json"));
const tokensJson = JSON.parse(readFileSync(path.join(pkgDir, "tokens.json"), "utf8")) as Record<
  string,
  string
>;

const CSS_DIR = path.resolve(process.cwd(), "src", "styles");
const SRC_DIR = path.resolve(process.cwd(), "src");

/** Hojas de la consola, con los comentarios fuera: un ejemplo en prosa no es una regla. */
function hojas(): Array<{ nombre: string; css: string }> {
  return readdirSync(CSS_DIR)
    .filter((f) => f.endsWith(".css"))
    .map((f) => ({
      nombre: f,
      css: readFileSync(path.join(CSS_DIR, f), "utf8").replace(/\/\*[\s\S]*?\*\//g, ""),
    }));
}

/** Todo `.ts`/`.tsx` de producción bajo `src/` (los tests no pintan pantalla). */
function fuentes(dir = SRC_DIR): string[] {
  const out: string[] = [];
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) out.push(...fuentes(p));
    else if (/\.tsx?$/.test(e.name) && !/\.test\.tsx?$/.test(e.name)) out.push(p);
  }
  return out;
}

function px(valor: string): number {
  return Number.parseFloat(valor.replace("px", ""));
}

/** Píxeles que acaba pintando un selector: resuelve el token que declara. */
function escalonDe(selector: string): number {
  const declarado = tamanoDe(selector);
  const token = /var\(\s*(--tk-text-[a-z0-9-]+)\s*\)/.exec(declarado)?.[1];
  expect(token, `${selector} no declara su tamaño con un token: «${declarado}»`).toBeDefined();
  return px(tokensJson[token as string]);
}

// ---------------------------------------------------------------------------
// 1 · El piso
// ---------------------------------------------------------------------------

describe("[T-6.12] el piso tipográfico tiene NOMBRE y es el escalón más bajo", () => {
  it("`--tk-text-min` existe y vale lo mismo que el escalón más bajo de la escala", () => {
    expect(tokensJson["--tk-text-min"]).toBe(tokensJson["--tk-text-2xs"]);
  });

  it("no hay ningún escalón de la escala por debajo del piso", () => {
    const escala = Object.entries(tokensJson).filter(
      ([k]) => k.startsWith("--tk-text-") && k !== "--tk-text-min",
    );
    const bajos = escala.filter(([, v]) => px(v) < px(tokensJson["--tk-text-min"]));
    expect(bajos).toEqual([]);
  });

  it("ninguna hoja de la consola declara un tamaño por debajo del piso", () => {
    const piso = px(tokensJson["--tk-text-min"]);
    const infractores: string[] = [];
    for (const { nombre, css } of hojas()) {
      const lineas = css.split("\n");
      lineas.forEach((linea, i) => {
        for (const m of linea.matchAll(/font(?:-size)?\s*:\s*([^;{}]+)/g)) {
          for (const n of m[1].matchAll(/(?<![\w.-])(\d+(?:\.\d+)?)px/g)) {
            if (Number.parseFloat(n[1]) < piso) {
              infractores.push(`${nombre}:${i + 1} → ${n[1]}px · ${linea.trim().slice(0, 70)}`);
            }
          }
        }
      });
    }
    expect(infractores, "un rótulo por debajo del piso es un rótulo que nadie lee").toEqual([]);
  });

  it("ni un solo `fontSize` escrito a mano en el TSX de producción", () => {
    const infractores: string[] = [];
    for (const f of fuentes()) {
      const src = readFileSync(f, "utf8");
      src.split("\n").forEach((linea, i) => {
        // Cubre las dos formas: el objeto de estilo (`fontSize: 9`) y el
        // atributo de SVG (`fontSize="8"`), que es igual de invisible al censo.
        if (/\bfontSize\s*[:=]/.test(linea)) {
          infractores.push(`${path.relative(SRC_DIR, f)}:${i + 1} · ${linea.trim().slice(0, 70)}`);
        }
      });
    }
    expect(
      infractores,
      "un tamaño inline no lo ve ningún censo: por eso escapaban cuatro pills de 9 px y un eje de 8",
    ).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// 2 · El dato manda sobre el nombre de la pantalla
// ---------------------------------------------------------------------------

/** El escalón de la MÉTRICA PRINCIPAL: el mismo que la alerta usa para el PGA. */
const METRICA = "--tk-text-2xl";
/** El escalón del NOMBRE de la pantalla: uno por debajo de la métrica. */
const TITULO = "--tk-text-xl";

/** Los cinco títulos de pantalla que se ven (el de `/console` es de lector de pantalla). */
const TITULOS_DE_PANTALLA = [
  ".fleet__title",
  ".triage__title",
  ".mt__title",
  ".audit__title",
  ".bld__title",
];

/** Los dos productores de KPI: la tira del wall y las tarjetas de flota. */
const VALORES_DE_KPI = [".soc-kpi__value", ".fleet__kpi-val"];
const ROTULOS_DE_KPI = [".soc-kpi__label", ".fleet__kpi-lbl"];

/** `font-size` declarado por un selector, mirando también el atajo `font:`. */
function tamanoDe(selector: string): string {
  for (const { css } of hojas()) {
    const re = new RegExp(`(^|[,}])\\s*${selector.replace(".", "\\.")}\\s*\\{([^}]*)\\}`, "m");
    const bloque = re.exec(css)?.[2];
    if (bloque === undefined) continue;
    const largo = /font-size\s*:\s*([^;]+)/.exec(bloque)?.[1];
    if (largo !== undefined) return largo.trim();
    const atajo = /font\s*:\s*([^;]+)/.exec(bloque)?.[1];
    if (atajo !== undefined) {
      const t = /var\(\s*(--tk-[a-z0-9-]+)\s*\)/.exec(atajo);
      if (t !== null) return `var(${t[1]})`;
      return atajo.trim();
    }
  }
  return "(sin regla)";
}

describe("[T-6.12] el nombre de la pantalla va por debajo de la métrica", () => {
  it("los cinco títulos visibles usan el MISMO escalón, y es un token", () => {
    const medidos = Object.fromEntries(TITULOS_DE_PANTALLA.map((s) => [s, tamanoDe(s)]));
    expect(medidos).toEqual(
      Object.fromEntries(TITULOS_DE_PANTALLA.map((s) => [s, `var(${TITULO})`])),
    );
  });

  it("ese escalón es estrictamente MENOR que el de la métrica principal", () => {
    expect(px(tokensJson[TITULO])).toBeLessThan(px(tokensJson[METRICA]));
  });

  it("los dos productores de KPI declaran el MISMO token, y es el de la métrica", () => {
    const medidos = Object.fromEntries(VALORES_DE_KPI.map((s) => [s, tamanoDe(s)]));
    expect(medidos).toEqual(Object.fromEntries(VALORES_DE_KPI.map((s) => [s, `var(${METRICA})`])));
  });

  // La tira del wall es la ÚNICA que baja de ese escalón, y baja por una medida,
  // no por gusto: once indicadores en una banda sobre el mapa se parten en filas
  // a 28 px y el mapa cae de 405 a 381 px en 1280×800, bajo el piso de 400 que
  // defienden `layout.spec.ts` y `smoke.spec.ts`. Si alguien abre una segunda
  // excepción, este censo la caza.
  it("la banda del wall es la ÚNICA excepción, y cae en un ESCALÓN, no en un número suelto", () => {
    const bajadas = hojas().flatMap(({ nombre, css }) =>
      [...css.matchAll(/([^{}]*\.soc-kpi__value[^{}]*)\{([^}]*)\}/g)]
        .filter((m) => /font(-size)?\s*:/.test(m[2]))
        .map((m) => ({ nombre, selector: m[1].trim().replace(/\s+/g, " ") })),
    );
    expect(bajadas.map((b) => b.selector)).toEqual([
      ".soc-kpis .soc-kpi__value",
      ".soc-kpi__value",
    ]);
    expect(tamanoDe(".soc-kpis .soc-kpi__value")).toBe("var(--tk-text-md)");
    // Y sigue estando por debajo de la métrica: la excepción es una BAJADA.
    expect(px(tokensJson["--tk-text-md"])).toBeLessThan(px(tokensJson[METRICA]));
    // El 15 px que había aquí no era ningún escalón de la escala. El que lo
    // sustituye sí, y es el más cercano por arriba: nadie perdió legibilidad.
    expect(px(tokensJson["--tk-text-md"])).toBeGreaterThan(15);
    expect(px(tokensJson["--tk-text-base"])).toBeLessThan(15);
  });

  it("y sus rótulos van al piso, los dos igual", () => {
    const medidos = Object.fromEntries(ROTULOS_DE_KPI.map((s) => [s, tamanoDe(s)]));
    expect(medidos).toEqual(
      Object.fromEntries(ROTULOS_DE_KPI.map((s) => [s, "var(--tk-text-min)"])),
    );
  });

  it("`/building` pinta el NOMBRE DEL SITIO en la métrica: el dato, no el rótulo de la pantalla", () => {
    expect(tamanoDe(".bld__name .site-label")).toBe(`var(${METRICA})`);
  });
});

// ---------------------------------------------------------------------------
// 3 · Ninguna `var()` fantasma
// ---------------------------------------------------------------------------

describe("[T-6.12] toda `var()` de las hojas resuelve — sea cual sea su prefijo", () => {
  it("el barrido encuentra hojas y `var()`s (si esto falla, el resto miente)", () => {
    const usos = hojas().flatMap(({ css }) => [...css.matchAll(/var\(\s*(--[a-z0-9-]+)/g)]);
    expect(hojas().length).toBeGreaterThan(3);
    expect(usos.length).toBeGreaterThan(200);
  });

  it("cero variables inventadas: la que no está en el paquete no pinta nada", () => {
    const fantasmas: string[] = [];
    for (const { nombre, css } of hojas()) {
      const lineas = css.split("\n");
      lineas.forEach((linea, i) => {
        for (const m of linea.matchAll(/var\(\s*(--[a-z0-9-]+)/g)) {
          if (!(m[1] in tokensJson)) {
            fantasmas.push(`${nombre}:${i + 1} → ${m[1]} · ${linea.trim().slice(0, 70)}`);
          }
        }
      });
    }
    expect(
      fantasmas,
      "un `font:` con una var() sin resolver TIRA la declaración entera: la regla no existe",
    ).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// 4 · El simulacro se lee a distancia sin comerse el mapa
// ---------------------------------------------------------------------------

describe("[T-6.12] el prefijo de estado del simulacro se lee de lejos", () => {
  it("ARMADO / EN CURSO se pintan en un escalón mayor que el resto de la tira", () => {
    expect(escalonDe(".soc-drill__estado")).toBeGreaterThan(escalonDe(".soc-drill"));
  });

  it("la tira EN REPOSO no engorda: sigue sin `font-size` propio y sin padding", () => {
    // `drill.spec.ts` fija el alto medido (<60 px) en el navegador; aquí se
    // defiende la causa de que ese alto no suba: el estado sólo aparece cuando
    // hay simulacro, y en reposo la tira no lo monta.
    const idle = hojas()
      .map(({ css }) => /\.soc-drill--idle\s*\{([^}]*)\}/.exec(css)?.[1])
      .find((b) => b !== undefined);
    expect(idle).toBeDefined();
    expect(idle).toContain("padding: 0");
    expect(idle).not.toContain("font-size");
  });
});
