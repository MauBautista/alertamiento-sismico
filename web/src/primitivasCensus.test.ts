// [T-6.13] UNA TABLA, UNA TARJETA, UN BOTÓN — el censo de las primitivas.
//
// Lo que medía la auditoría (U-24) antes de esta ficha, contado a mano sobre
// `web/src`:
//
//   · **Tres sistemas de clases de tabla.** Seis `<table>` en el árbol: tres
//     colgaban de `.soc-table` y tres traían el suyo propio —`fleet__admintable`,
//     `bld__table`, `audit__table`—, cada uno redeclarando `width`,
//     `border-collapse`, el `th` y el `td` con valores casi iguales. Casi: los
//     tres divergían en el tamaño (11, 11 y 11.5 px) sin que nadie lo hubiera
//     decidido.
//   · **Veintiuna `soc-card` escritas a mano** —seis de ellas en `DetailPanel`—,
//     cada una repitiendo la misma cabecera de tres niveles y, las que llevan
//     icono, un `style` en línea para ponerlo al lado del título.
//   · **72 `soc-btn` sueltos en 30 ficheros**, con la variante escrita a mano en
//     el `className` cada vez.
//   · **La regla «hay lectura conocida y falló ⇒ está retenida» copiada.** La
//     auditoría contó dos banners; este censo, escrito para cazar la forma y no
//     los nombres, encontró CINCO: los tres de la franja de escena y las dos del
//     panel de clasificación.
//
// Una copia diverge; lo hicieron las tres tablas. Este censo no vigila el estilo:
// vigila que **exista un solo sitio donde cambiarlo**.
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const SRC = path.resolve(process.cwd(), "src");

/** Todo `.ts`/`.tsx` de PRODUCCIÓN bajo `src/` (un test no pinta pantalla). */
function fuentes(dir = SRC): string[] {
  const out: string[] = [];
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) out.push(...fuentes(p));
    else if (/\.tsx?$/.test(e.name) && !/\.test\.tsx?$/.test(e.name)) out.push(p);
  }
  return out;
}

const ARCHIVOS = fuentes().map((f) => ({
  ruta: path.relative(SRC, f).replaceAll(path.sep, "/"),
  src: readFileSync(f, "utf8"),
}));

/** Ficheros que INCUMPLEN `regla`, salvo los que son la propia primitiva. */
function infractores(regla: RegExp, duenos: string[]): string[] {
  return ARCHIVOS.filter(({ ruta, src }) => !duenos.includes(ruta) && regla.test(src))
    .map(({ ruta, src }) => {
      const linea = src.split("\n").findIndex((l) => new RegExp(regla.source).test(l)) + 1;
      return `${ruta}:${linea}`;
    })
    .sort();
}

describe("[T-6.13] el barrido encuentra el árbol (si esto falla, el resto miente)", () => {
  it("hay pantallas que barrer y las primitivas existen", () => {
    expect(ARCHIVOS.length).toBeGreaterThan(80);
    for (const p of ["components/Table.tsx", "components/Card.tsx", "components/Button.tsx"]) {
      expect(
        ARCHIVOS.map((a) => a.ruta),
        `falta la primitiva ${p}`,
      ).toContain(p);
    }
  });
});

describe("[T-6.13] ninguna pantalla declara una tabla, una tarjeta o un botón por su cuenta", () => {
  it("`<table>` sólo lo escribe `components/Table.tsx`", () => {
    expect(infractores(/<table[\s>]/, ["components/Table.tsx"])).toEqual([]);
  });

  it("`soc-card` sólo lo escribe `components/Card.tsx`", () => {
    expect(infractores(/\bsoc-card\b/, ["components/Card.tsx"])).toEqual([]);
  });

  it("`soc-btn` sólo lo escribe `components/Button.tsx`", () => {
    expect(infractores(/\bsoc-btn\b/, ["components/Button.tsx"])).toEqual([]);
  });
});

describe("[T-6.13] las clases de las tablas viejas se RETIRARON, no se quedaron de adorno", () => {
  // Los comentarios se retiran antes de barrer: contar la prosa que EXPLICA la
  // retirada como si fuera la regla retirada dejaría el censo imposible de pasar
  // (misma cautela que `cssContract.test.ts`).
  const HOJAS = readdirSync(path.join(SRC, "styles"))
    .filter((f) => f.endsWith(".css"))
    .map((f) => ({
      nombre: `styles/${f}`,
      texto: readFileSync(path.join(SRC, "styles", f), "utf8").replace(/\/\*[\s\S]*?\*\//g, ""),
    }));
  const MARCADO = ARCHIVOS.map((a) => ({
    nombre: a.ruta,
    texto: a.src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, ""),
  }));

  it.each(["fleet__admintable", "bld__table", "audit__table"])(
    "`%s` no queda ni en las hojas ni en el marcado",
    (clase) => {
      // `\b` al final distingue la clase de la tabla (`audit__table`) del envoltorio
      // que la rodea y que SIGUE vivo (`audit__tablewrap`).
      const re = new RegExp(`\\b${clase}\\b`);
      const restos = [...HOJAS, ...MARCADO].filter((x) => re.test(x.texto)).map((x) => x.nombre);
      expect(restos, "una clase muerta en la hoja es una regla que nadie sabe si aplica").toEqual(
        [],
      );
    },
  );
});

describe("[T-6.13] «conocido y falló ⇒ retenido» se calcula en UN solo sitio", () => {
  it("`staleDeLectura` existe y es una función pura de la escena", () => {
    const helper = ARCHIVOS.find((a) => a.ruta === "components/staleDeLectura.ts");
    expect(helper, "falta `components/staleDeLectura.ts`").toBeDefined();
    expect(helper!.src).toMatch(/export function staleDeLectura\(/);
  });

  it("los tres banners de la escena la consumen, y ninguno rehace la cuenta", () => {
    const BANNERS = [
      "features/scene/DrillBanner.tsx",
      "features/scene/MaintenanceBanner.tsx",
      "features/scene/DemoModeBanner.tsx",
    ];
    const sinUsar = BANNERS.filter(
      (b) => !ARCHIVOS.find((a) => a.ruta === b)?.src.includes("staleDeLectura"),
    );
    expect(sinUsar).toEqual([]);

    // La forma que se copiaba: `readError … && conocido ? updatedAt : null`.
    const copias = ARCHIVOS.filter(
      (a) =>
        a.ruta !== "components/staleDeLectura.ts" &&
        /readError[^;\n]*\?\s*updatedAt\s*:\s*null/.test(a.src),
    ).map((a) => a.ruta);
    expect(copias, "la regla volvió a escribirse a mano fuera del helper").toEqual([]);
  });
});
