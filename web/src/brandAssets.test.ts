import { existsSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * La consola sirve SUS iconos de marca, y el marcado los pide de verdad.
 *
 * POR QUÉ ESTE TEST EXISTE
 * ------------------------
 * `index.html` no declaraba ningún icono: la consola SOC —un producto que se
 * enseña a clientes en una pantalla grande— salía en la pestaña con el icono
 * genérico del navegador. Eso no lo caza ningún test de componente, porque
 * `index.html` no pasa por React: es la plantilla que Vite copia.
 *
 * Se cruzan las DOS mitades a propósito. Cada una falla sola y en silencio:
 * un `<link>` sin fichero deja la pestaña con el icono por defecto, y un
 * fichero en `public/` que nadie enlaza no lo pide ningún navegador. Comprobar
 * solo una da verde con el defecto puesto.
 *
 * Los ficheros se DERIVAN de `shared/brand` con `shared/brand/generar.py`; si
 * este test se pone rojo, lo que falta es correr el generador, no dibujar un
 * PNG a mano.
 */

const RAIZ = resolve(__dirname, "..");
const HTML = readFileSync(join(RAIZ, "index.html"), "utf8");

/** Cabecera IHDR del PNG: ancho y alto en bytes fijos, sin dependencias. */
function tamañoPng(ruta: string): [number, number] {
  const crudo = readFileSync(ruta);
  expect(crudo.subarray(0, 8)).toEqual(
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
  );
  return [crudo.readUInt32BE(16), crudo.readUInt32BE(20)];
}

const ICONOS: Array<{ href: string; tamaño?: [number, number] }> = [
  { href: "/favicon.ico" },
  { href: "/icon-192.png", tamaño: [192, 192] },
  { href: "/icon-512.png", tamaño: [512, 512] },
  { href: "/apple-touch-icon.png", tamaño: [180, 180] },
];

describe("iconos de marca de la consola", () => {
  it("index.html enlaza cada icono Y el fichero existe en public/", () => {
    for (const { href } of ICONOS) {
      expect(HTML, `index.html no enlaza ${href}`).toContain(`href="${href}"`);
      const ruta = join(RAIZ, "public", href.replace(/^\//, ""));
      expect(existsSync(ruta), `enlazado pero ausente: public${href}`).toBe(true);
    }
  });

  it("los PNG tienen el tamaño que declara su <link>", () => {
    for (const { href, tamaño } of ICONOS) {
      if (!tamaño) continue;
      expect(tamañoPng(join(RAIZ, "public", href.replace(/^\//, "")))).toEqual(tamaño);
    }
  });

  it("el .ico no es un stub: lleva sus tres tamaños dibujados", () => {
    const ico = readFileSync(join(RAIZ, "public", "favicon.ico"));
    // Cabecera ICONDIR: bytes 4-5 = número de imágenes dentro.
    expect(ico.readUInt16LE(4)).toBe(3);
    expect(ico.byteLength).toBeGreaterThan(1000);
  });

  it("la pestaña nombra el PRODUCTO, no solo la empresa", () => {
    // Decía «TAKAB» a secas, que es la empresa. Con varias consolas abiertas
    // —y el operador de un SOC tiene varias— eso no distingue nada.
    const titulo = /<title>([^<]+)<\/title>/.exec(HTML)?.[1] ?? "";
    expect(titulo).toContain("TAKAB Ailert");
  });

  it("el logotipo que importan las pantallas es el del producto", () => {
    const logotipo = join(RAIZ, "src", "assets", "logotipo-takab-ailert.png");
    expect(existsSync(logotipo), "falta el logotipo derivado de shared/brand").toBe(true);
    const [ancho] = tamañoPng(logotipo);
    // La pantalla de login lo pinta a 220 px de ancho; por debajo de 2x se ve
    // blando en cualquier portátil moderno.
    expect(ancho).toBeGreaterThanOrEqual(440);
  });

  it("las tres piezas de la marca existen y tienen resolución para su hueco", () => {
    const pieza = (n: string) => join(RAIZ, "src", "assets", n);
    for (const n of [
      "imagotipo-takab-ailert.png",
      "logotipo-takab-ailert.png",
      "isotipo-takab-ailert.png",
    ]) {
      expect(existsSync(pieza(n)), `falta ${n}: corre shared/brand/generar.py`).toBe(true);
    }
    // El imagotipo se pinta a 220 px de ancho en login/estados ⇒ 2x mínimo.
    expect(tamañoPng(pieza("imagotipo-takab-ailert.png"))[0]).toBeGreaterThanOrEqual(440);
    // El isotipo se pinta a 40 px de ALTO en la topbar ⇒ 2x mínimo por el alto.
    expect(tamañoPng(pieza("isotipo-takab-ailert.png"))[1]).toBeGreaterThanOrEqual(80);
  });

  it("la topbar compone el imagotipo con sus DOS piezas, no con una aplastada", () => {
    // El imagotipo plano a 40 px de alto —lo que da la topbar de 64— encoge la
    // palabra hasta perderla. Por eso la topbar sirve símbolo y palabra por
    // separado, cada uno a su altura. Si alguien vuelve a meter una sola
    // imagen, la marca se degrada sin que nada más se queje.
    const topbar = readFileSync(join(RAIZ, "src", "shell", "Topbar.tsx"), "utf8");
    expect(topbar).toContain("soc-brand__mark");
    expect(topbar).toContain("soc-brand__logo");
    expect(topbar).toContain("isotipo-takab-ailert.png");
    expect(topbar).toContain("logotipo-takab-ailert.png");

    const css = readFileSync(join(RAIZ, "src", "styles", "soc.css"), "utf8");
    const alto = (clase: string) =>
      Number(new RegExp(`\\.${clase}\\s*\\{[^}]*height:\\s*(\\d+)px`).exec(css)?.[1] ?? "0");
    // El símbolo manda sobre la palabra: si se igualan o se invierten, deja de
    // ser una composición y vuelve a ser un logotipo con un adorno delante.
    expect(alto("soc-brand__mark")).toBeGreaterThan(alto("soc-brand__logo"));
    // Y ninguna de las dos puede pasarse de la fila de 64 px.
    expect(alto("soc-brand__mark")).toBeLessThanOrEqual(64);
  });

  it("las pantallas grandes usan el imagotipo COMPLETO", () => {
    // Ahí el hueco es de ancho, no de alto: cabe entero y es la marca completa.
    for (const ruta of [
      ["src", "pages", "LoginPage.tsx"],
      ["src", "pages", "StatusScreens.tsx"],
      ["src", "app", "DegradedSessionScreen.tsx"],
    ]) {
      const fuente = readFileSync(join(RAIZ, ...ruta), "utf8");
      expect(fuente, `${ruta.join("/")} no usa el imagotipo`).toContain(
        "imagotipo-takab-ailert.png",
      );
    }
  });
});
