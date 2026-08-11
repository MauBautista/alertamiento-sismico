// EL CENSO DE LA IMAGEN DE CONSOLA: el árbol que ve `tsc` en el laptop no es el
// que ve la imagen.
//
// El 2026-08-11 un despliegue murió aquí. `T-2.75.a` añadió
// `shared/fixtures/notify-channels.json` —la MISMA fixture que leen los dos
// lados del contrato de canales: `api/tests/api/test_notify_channels.py` y el
// test de `NotificationChannels.tsx`— y `console.Dockerfile` no la copiaba.
// Resultado: `make cloud-images` reventó con
//   TS2307: Cannot find module '../../../../shared/fixtures/notify-channels.json'
// tras 5 minutos de build, y `make cloud-deploy` fue detrás con
// `manifest unknown`, porque el target construye las DOS imágenes y empuja al
// final: el fallo de la consola dejó también la imagen de api sin subir.
//
// POR QUÉ NO LO CAZÓ NADA ANTES, que es lo que esta prueba corrige:
// `make lint` y el job `web` corren `tsc --noEmit` sobre el checkout COMPLETO,
// donde `shared/fixtures/` existe. La imagen solo ve lo que se copia, así que
// era la única superficie capaz de notarlo — y la construye un único comando
// que nadie corre en un PR. El defecto vivió desde `6cef7d4` hasta el
// despliegue siguiente, en verde todo el camino.
//
// Es la MISMA familia que la trampa del bundle de móvil (`expo-router` barriendo
// los `*.test.tsx` de `src/app`): un fichero de PRUEBA rompiendo un artefacto de
// PRODUCCIÓN. Y la raíz es la misma: el `build` de la imagen corre
// `npm run build`, que encadena `tsc --noEmit` — o sea que typechequea también
// los tests, aunque la app no importe la fixture para nada.
//
// LO QUE ESTE CENSO NO ES: no valida que la imagen construya. Eso solo lo
// demuestra construirla. Valida la condición concreta que la rompió y que puede
// volver a romperla sin que nadie lo note: que `web/src` importe algo de fuera
// de `web/` que el Dockerfile no copia. Si mañana el fallo es otro (una versión
// de node, un lock desincronizado), este test seguirá verde y hará bien.

import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";

import { describe, expect, it } from "vitest";

const WEB = resolve(process.cwd());
const RAIZ = resolve(WEB, "..");
const SRC = join(WEB, "src");
const DOCKERFILE = join(RAIZ, "deploy", "cloud", "console.Dockerfile");

/** Extensiones que `tsc` resolverá para un import sin extensión. */
const EXTENSIONES = ["", ".ts", ".tsx", ".d.ts", ".json", "/index.ts", "/index.tsx"];

/**
 * Rutas que el Dockerfile copia DENTRO de la etapa de build, relativas a la
 * raíz del repo. Se ignoran las líneas `COPY --from=…` (etapa final: sirve el
 * `dist` ya construido, no participa del typecheck).
 */
export function rutasCopiadas(dockerfile: string): string[] {
  const copiadas: string[] = [];
  for (const linea of dockerfile.split("\n")) {
    const limpia = linea.trim();
    if (!limpia.toUpperCase().startsWith("COPY ") || limpia.includes("--from=")) {
      continue;
    }
    // `COPY <origen…> <destino>`: el último token es el destino.
    const tokens = limpia
      .slice(5)
      .split(/\s+/)
      .filter((t) => t.length > 0 && !t.startsWith("--"));
    copiadas.push(...tokens.slice(0, -1));
  }
  return copiadas;
}

/** ¿La ruta (relativa a la raíz) cae dentro de algo que se copió? */
export function estaCopiada(rutaRelativa: string, copiadas: string[]): boolean {
  return copiadas.some((c) => {
    const base = c.replace(/\/+$/, "");
    return rutaRelativa === base || rutaRelativa.startsWith(`${base}/`);
  });
}

function ficherosFuente(dir: string, acc: string[] = []): string[] {
  for (const entrada of readdirSync(dir)) {
    if (entrada === "node_modules") {
      continue;
    }
    const completa = join(dir, entrada);
    if (statSync(completa).isDirectory()) {
      ficherosFuente(completa, acc);
    } else if (/\.(ts|tsx)$/.test(entrada)) {
      acc.push(completa);
    }
  }
  return acc;
}

/** Especificadores relativos de un fichero: `import … from "…"` y `import("…")`. */
export function importsRelativos(fuente: string): string[] {
  const encontrados: string[] = [];
  const patrones = [
    /(?:^|\n)\s*import\s[^;]*?from\s*["'](\.[^"']*)["']/g,
    /(?:^|\n)\s*import\s*["'](\.[^"']*)["']/g,
    /import\s*\(\s*["'](\.[^"']*)["']\s*\)/g,
    /require\s*\(\s*["'](\.[^"']*)["']\s*\)/g,
  ];
  for (const patron of patrones) {
    for (const m of fuente.matchAll(patron)) {
      encontrados.push(m[1]);
    }
  }
  return encontrados;
}

/**
 * Los imports de `web/src` que SALEN de `web/`, como rutas relativas a la raíz
 * del repo. Ésta es la población: lo que vive dentro de `web/` viaja siempre,
 * porque el Dockerfile copia `web` entero.
 */
export function importsQueSalenDeWeb(ficheros: string[]): string[] {
  const fuera = new Set<string>();
  for (const fichero of ficheros) {
    for (const especificador of importsRelativos(readFileSync(fichero, "utf8"))) {
      const absoluto = resolve(dirname(fichero), especificador);
      if (absoluto.startsWith(`${WEB}/`)) {
        continue;
      }
      const resuelto = EXTENSIONES.map((ext) => `${absoluto}${ext}`).find((c) => existsSync(c));
      // Sin resolver a un fichero real no se puede afirmar nada: lo caza `tsc`,
      // que es quien sabe de resolución de módulos. Aquí no se inventa.
      if (resuelto !== undefined) {
        fuera.add(relative(RAIZ, resuelto));
      }
    }
  }
  return [...fuera].sort();
}

describe("la imagen de consola copia todo lo que `web/src` importa de fuera de web/", () => {
  it("ningún import que sale de web/ se queda fuera del Dockerfile", () => {
    const copiadas = rutasCopiadas(readFileSync(DOCKERFILE, "utf8"));
    const salientes = importsQueSalenDeWeb(ficherosFuente(SRC));
    const huerfanos = salientes.filter((r) => !estaCopiada(r, copiadas));

    expect(
      huerfanos,
      huerfanos.length === 0
        ? ""
        : `web/src importa esto de fuera de web/ y \`deploy/cloud/console.Dockerfile\` NO lo ` +
            `copia, así que \`make cloud-images\` morirá con TS2307 tras varios minutos de ` +
            `build:\n  ${huerfanos.join("\n  ")}\n` +
            `Arréglalo añadiendo su COPY en la etapa \`build\`, junto a shared/sdk-ts.`,
    ).toEqual([]);
  });

  it("la población no está vacía — si lo estuviera, este test pasaría por vacuidad", () => {
    // Control de no-vacuidad: hoy `shared/sdk-ts`, `shared/design-tokens` y
    // `shared/fixtures` se importan desde `web/src`. Si esto llega a 0, el
    // analizador dejó de ver imports y el test de arriba sería decorativo.
    expect(importsQueSalenDeWeb(ficherosFuente(SRC)).length).toBeGreaterThan(0);
  });
});

describe("el analizador, contra el caso real que rompió el despliegue", () => {
  const DOCKERFILE_SIN_FIXTURES = [
    "FROM node:22-slim AS build",
    "COPY shared/sdk-ts shared/sdk-ts",
    "COPY shared/design-tokens shared/design-tokens",
    "COPY web web",
    "FROM caddy:2-alpine",
    "COPY --from=build /repo/web/dist /srv",
  ].join("\n");

  it("lee las rutas de origen y descarta el destino", () => {
    expect(rutasCopiadas(DOCKERFILE_SIN_FIXTURES)).toEqual([
      "shared/sdk-ts",
      "shared/design-tokens",
      "web",
    ]);
  });

  it("IGNORA los COPY --from de la etapa final: no participan del typecheck", () => {
    expect(rutasCopiadas(DOCKERFILE_SIN_FIXTURES)).not.toContain("/repo/web/dist");
  });

  it("habría cazado el fallo real: la fixture no está cubierta", () => {
    const copiadas = rutasCopiadas(DOCKERFILE_SIN_FIXTURES);
    expect(estaCopiada("shared/fixtures/notify-channels.json", copiadas)).toBe(false);
  });

  it("y lo da por bueno en cuanto el COPY existe", () => {
    const copiadas = rutasCopiadas(
      `${DOCKERFILE_SIN_FIXTURES}\nCOPY shared/fixtures shared/fixtures`,
    );
    expect(estaCopiada("shared/fixtures/notify-channels.json", copiadas)).toBe(true);
  });

  it("no confunde un prefijo de nombre con un prefijo de ruta", () => {
    // `shared/fixtures-viejos` NO está cubierto por `COPY shared/fixtures`.
    const copiadas = ["shared/fixtures"];
    expect(estaCopiada("shared/fixtures-viejos/x.json", copiadas)).toBe(false);
    expect(estaCopiada("shared/fixtures/x.json", copiadas)).toBe(true);
  });

  it("reconoce las cuatro formas de importar", () => {
    const fuente = [
      'import a from "../uno";',
      'import "../dos";',
      'const c = await import("../tres");',
      'const d = require("../cuatro");',
      'import e from "@takab/sdk";',
      'import f from "./local";',
    ].join("\n");
    expect(importsRelativos(fuente)).toEqual(
      expect.arrayContaining(["../uno", "../dos", "../tres", "../cuatro", "./local"]),
    );
    expect(importsRelativos(fuente)).not.toContain("@takab/sdk");
  });
});
