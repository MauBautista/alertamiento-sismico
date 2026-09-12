/**
 * [T-7.05 · C-4] LOS DOS EXTREMOS DEL DEEP-LINK, ATADOS.
 *
 * `/console?sitio=<site_id>` tiene dos mitades escritas en ficheros distintos: quien
 * CONSTRUYE la URL (el alta de hardware, aquí; el «volver» de triage, allá) y quien la
 * LEE (`ConsolePage`). El nombre del parámetro estaba tecleado a mano en las dos, y
 * nada las ataba: renombrarlo en la consola —con su propio test actualizado— dejaba a
 * los emisores en verde apuntando a una `/console` pelada. El operador aterrizaba en
 * el mapa sin nada seleccionado, que es exactamente el defecto que C-4 corrige.
 *
 * Por eso este censo no comprueba que el nombre sea «sitio»: comprueba que sea EL
 * MISMO que la consola lee. Si alguien lo renombra allí, esto se pone rojo aquí y el
 * emisor se entera antes de llegar a la demo.
 */
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { CONSOLE_SITE_PARAM, consoleSiteHref } from "./consoleSiteHref";

const SRC = path.resolve(process.cwd(), "src");
const CONSOLE_PAGE = path.join(SRC, "features/console/ConsolePage.tsx");

/**
 * Comentarios fuera ANTES de contar nada: un ejemplo comentado (`// searchParams.get(
 * "viejo")`) contaría como lectura real y el censo mediría prosa. Se quita el bloque
 * `/* … *\/` entero y el `//` de línea, salvo el de un `http://` (`:` delante).
 */
function sinComentarios(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/[^\n]*/g, "$1");
}

/** Nombres de parámetro que un fichero LEE de la URL. */
function paramsLeidos(src: string): string[] {
  return [...sinComentarios(src).matchAll(/searchParams\.get\(\s*"([^"]+)"\s*\)/g)].map(
    (m) => m[1],
  );
}

/** Nombres de parámetro que un fichero ESCRIBE a mano en una URL de `/console`. */
function paramsEscritos(src: string): string[] {
  return [...sinComentarios(src).matchAll(/\/console\?([A-Za-z_][A-Za-z0-9_]*)=/g)].map(
    (m) => m[1],
  );
}

/** Todo `.ts`/`.tsx` de PRODUCCIÓN bajo `src/` (un test no enlaza a ningún sitio). */
function fuentes(dir = SRC): string[] {
  const out: string[] = [];
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) out.push(...fuentes(p));
    else if (/\.tsx?$/.test(e.name) && !/\.test\.tsx?$/.test(e.name)) out.push(p);
  }
  return out;
}

describe("[T-7.05 · C-4] el barrido funciona (si esto falla, el resto del censo miente)", () => {
  it("la extracción reconoce las dos formas reales, y no la prosa de al lado", () => {
    expect(paramsLeidos('const x = searchParams.get("sitio");')).toEqual(["sitio"]);
    expect(paramsEscritos("to={`/console?sitio=${encodeURIComponent(id)}`}")).toEqual(["sitio"]);
    // Un ejemplo COMENTADO no cuenta como código (las dos formas de comentario).
    expect(paramsLeidos('// searchParams.get("viejo")')).toEqual([]);
    expect(paramsEscritos("/* enlazaba a /console?viejo=1 */")).toEqual([]);
    // …y un `//` de una URL no parte la línea en dos.
    expect(paramsLeidos('const u = "http://x/y"; const s = searchParams.get("sitio");')).toEqual([
      "sitio",
    ]);
  });

  it("hay árbol que barrer y la consola sigue leyendo la URL", () => {
    expect(fuentes().length).toBeGreaterThan(80);
    expect(paramsLeidos(readFileSync(CONSOLE_PAGE, "utf8")).length).toBeGreaterThan(0);
  });
});

describe("[T-7.05 · C-4] el nombre del parámetro sale de un solo sitio", () => {
  it("el que esta flota ESCRIBE es uno de los que la consola LEE", () => {
    const leidos = paramsLeidos(readFileSync(CONSOLE_PAGE, "utf8"));
    // Si esto falla, alguien renombró el parámetro en `ConsolePage` y el enlace del
    // alta aterriza en `/console` pelado: ajusta `CONSOLE_SITE_PARAM`, no este test.
    expect(leidos).toContain(CONSOLE_SITE_PARAM);
  });

  it("ningún fichero de producción escribe a mano un parámetro que la consola no lea", () => {
    const leidos = new Set(paramsLeidos(readFileSync(CONSOLE_PAGE, "utf8")));
    const huerfanos = fuentes()
      .map((f) => ({
        ruta: path.relative(SRC, f),
        escritos: paramsEscritos(readFileSync(f, "utf8")),
      }))
      .flatMap(({ ruta, escritos }) =>
        escritos.filter((p) => !leidos.has(p)).map((p) => `${ruta}: /console?${p}=`),
      );
    expect(huerfanos).toEqual([]);
  });

  it("dentro de `features/fleet` el nombre no se vuelve a teclear: se construye aquí", () => {
    const aMano = fuentes(path.join(SRC, "features/fleet"))
      .filter((f) => f !== path.join(SRC, "features/fleet/consoleSiteHref.ts"))
      .filter((f) => paramsEscritos(readFileSync(f, "utf8")).length > 0)
      .map((f) => path.relative(SRC, f));
    expect(aMano).toEqual([]);
  });
});

describe("[T-7.05 · C-4] la URL que construye vuelve a salir entera del otro lado", () => {
  it("un `site_id` normal da la forma que la consola espera", () => {
    expect(consoleSiteHref("33333333-3333-4333-8333-333333333333")).toBe(
      "/console?sitio=33333333-3333-4333-8333-333333333333",
    );
  });

  it("un identificador hostil viaja codificado y se recupera IGUAL", () => {
    // No se mide la codificación elegida (`+` o `%20` son ambas legales): se mide que
    // lo que llega al otro extremo sea el mismo identificador. Sin esto, un `&` o un
    // `/` en el id partiría la query y la consola abriría la ficha de otra cosa.
    const hostil = "sitio raro/1&x=2";
    const href = consoleSiteHref(hostil);
    const leido = new URLSearchParams(href.slice(href.indexOf("?"))).get(CONSOLE_SITE_PARAM);
    expect(leido).toBe(hostil);
  });
});
