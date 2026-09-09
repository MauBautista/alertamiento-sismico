/**
 * [T-6.07] EL PASO 0 DEL ARRANQUE: lo único que hay antes de que React monte.
 *
 * Entre que el navegador pinta `index.html` y el primer frame de React no había
 * pantalla — fondo del navegador y silencio. Medido en la auditoría del
 * 2026-09-06: 0.5 s con el login dev en local, 1.3 s hasta la landing
 * desplegada. Suficiente para que alguien crea que la consola no arrancó, y en
 * una sala de operación eso se resuelve recargando a ciegas.
 *
 * Lo que este test defiende es lo que hace que ese paso 0 SIRVA:
 *
 * 1. que la marca esté DENTRO de `#root` (React la sustituye al montar: si
 *    viviera fuera, se quedaría pegada debajo de la consola para siempre);
 * 2. que no dependa de nada que todavía no haya cargado — sin `<link>` a una
 *    hoja, sin fuentes remotas, sin `var(--tk-*)`: la hoja que declara esos
 *    tokens viaja DENTRO del bundle que aún no está;
 * 3. y que por eso mismo los colores escritos a mano sean los DEL PAQUETE, no
 *    unos parecidos. Es la misma disciplina que el panel del gabinete, que
 *    tampoco puede importar `@takab/design-tokens` y por eso compara su copia.
 */
import { readFileSync } from "node:fs";
import path from "node:path";

import { cssVariables } from "@takab/design-tokens";
import { describe, expect, it } from "vitest";

const HTML = readFileSync(path.resolve(process.cwd(), "index.html"), "utf8");
const NOSCRIPT = /<noscript>([\s\S]*?)<\/noscript>/.exec(HTML)?.[1] ?? "";
/** El bloque de estilo DEL ARRANQUE, no el primero que aparezca: el
 * `<noscript>` trae el suyo, y buscarlo por posición ataría este test al orden
 * en que están escritos. */
const ESTILO_ARRANQUE =
  [...HTML.matchAll(/<style>([\s\S]*?)<\/style>/g)]
    .map((m) => m[1])
    .find((bloque) => /(^|\n)\s*\.boot\s*\{/.test(bloque)) ?? "";

/** El color tal cual se escribe en el HTML, en minúsculas. */
function token(nombre: keyof typeof cssVariables): string {
  return cssVariables[nombre].toLowerCase();
}

describe("marca de arranque · lo que se ve antes del primer frame", () => {
  it("vive DENTRO de #root, para que React la sustituya al montar", () => {
    const root = /<div id="root">([\s\S]*?)<\/div>\s*<\/div>/.exec(HTML);
    expect(
      root,
      "`#root` dejó de traer la marca de arranque: el paso 0 vuelve a ser mudo",
    ).not.toBeNull();
    expect(root![1]).toContain("TAKAB AILERT");
    // `role="status"` y no un `<h1>` mudo: un lector de pantalla anuncia que
    // algo está pasando en vez de leer un título y callarse.
    expect(root![1]).toContain('role="status"');
  });

  it("dice que está iniciando, no solo la marca", () => {
    expect(HTML).toMatch(/INICIANDO/);
  });

  it("sin JavaScript, la consola lo dice Y deslinda el alertamiento", () => {
    expect(NOSCRIPT, "sin `<noscript>` el navegador sin JS enseña una página en blanco").not.toBe(
      "",
    );
    expect(NOSCRIPT).toMatch(/necesita JavaScript/i);
    // Lo que de verdad importa saber: que el edificio sigue protegido aunque
    // esta pantalla no arranque (reglas de oro 1 y 2).
    expect(NOSCRIPT).toMatch(/NO depende de esta/i);
  });

  it("sin JavaScript APAGA el «INICIANDO…», que ya no va a iniciar nada", () => {
    // Medido en un navegador con el scripting apagado: se pintaban LOS DOS
    // bloques, y el de `#root` anunciaba el arranque de una consola que no iba
    // a arrancar, justo encima del texto que explica por qué. Un `<style>`
    // dentro de `<noscript>` solo se aplica en ese caso, y `#root .boot` gana
    // por especificidad de id esté donde esté escrito.
    const estilo = /<style>([\s\S]*?)<\/style>/.exec(NOSCRIPT)?.[1] ?? "";
    expect(estilo, "el `<noscript>` dejó de apagar el marcador de `#root`").toMatch(
      /#root\s+\.boot/,
    );
    expect(estilo).toMatch(/display:\s*none/);
  });

  it("no depende de NADA que todavía no haya cargado", () => {
    const body = HTML.slice(HTML.indexOf("<body>"));
    // Una hoja externa llegaría después del pintado: la marca saldría sin
    // estilo. El `<style>` va inline a propósito.
    expect(body).not.toMatch(/<link[^>]+stylesheet/);
    expect(body).toContain("<style>");
    // Y nada de custom properties: las declara la hoja que viaja en el bundle.
    expect(body.slice(0, body.indexOf("<script"))).not.toMatch(/var\(--tk-/);
  });

  it("los colores escritos a mano son los DEL PAQUETE, no unos parecidos", () => {
    // Sin esto, el día que la marca cambie de navy el arranque se queda con el
    // viejo y nadie lo ve: es la pantalla que menos gente mira dos veces.
    const style = ESTILO_ARRANQUE;
    expect(style, "el bloque de estilo del arranque desapareció").not.toBe("");
    expect(style).toContain(token("--tk-surface-0"));
    expect(style).toContain(token("--tk-fg-1"));
    expect(style).toContain(token("--tk-fg-3"));
    expect(style).toContain(token("--tk-cyan"));

    // Y NINGÚN otro color: un hex que no esté en el paquete es un color propio
    // de esta pantalla, que es exactamente lo que no puede tener.
    const delPaquete = new Set(
      Object.values(cssVariables)
        .filter((v) => /^#[0-9A-Fa-f]{6}$/.test(v))
        .map((v) => v.toLowerCase()),
    );
    // El barrido mira TODO el estilo inline, no solo el del arranque: un color
    // propio colado en el bloque del `<noscript>` sería el mismo defecto.
    const inline = [...HTML.matchAll(/<style>([\s\S]*?)<\/style>/g)].map((m) => m[1]).join("\n");
    const usados = [...inline.matchAll(/#[0-9a-f]{6}/g)].map((m) => m[0]);
    expect(usados.filter((c) => !delPaquete.has(c))).toEqual([]);
  });
});
