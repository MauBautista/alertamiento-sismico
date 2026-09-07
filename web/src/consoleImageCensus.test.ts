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

/* =====================================================================
   [T-6.05] EL GATE DEL LOGIN DEV EN LA IMAGEN
   =====================================================================
   El servidor está cerrado con test (sin JWKS inline `main.create_app` no monta
   `/dev/token`). El CLIENTE dependía de UNA línea del Dockerfile —
   `ENV VITE_DEV_TOKEN_ENABLED=false`— que ningún test bloqueante leía: un `true`
   tecleado, la línea borrada, o un `ARG` homónimo añadido de buena fe (que es el
   primer paso natural hacia `ENV X=${X}` y un `--build-arg` que nadie audita)
   habrían pintado el panel LOGIN DEV en la consola desplegada contra un endpoint
   que no existe. Hoy no es visible en producción (U-16, medido); desde aquí, está
   defendido: el job `web` corre este fichero en cada PR.

   Lo que se exige, y por qué cada cosa:
   - la etapa de BUILD (la que corre `npm run build`) fija la variable a `false`
     ANTES de ese RUN — Vite congela `import.meta.env` en el build, un ENV posterior
     no sirve de nada;
   - el valor es el literal `false`: ni `true`, ni `${…}` (eso lo haría venir del
     `--build-arg`), ni vacío;
   - no existe `ARG VITE_DEV_TOKEN_ENABLED` en NINGUNA etapa;
   - `.dockerignore` sigue excluyendo `web/.env*`: el segundo cerrojo (T-1.62), por
     si un día la variable dejara de declararse y volviera a heredarse del laptop.
   ===================================================================== */

export const FLAG_LOGIN_DEV = "VITE_DEV_TOKEN_ENABLED";
const DOCKERIGNORE = join(RAIZ, ".dockerignore");

/**
 * Instrucciones del Dockerfile con las continuaciones (`\`) plegadas y sin
 * comentarios ni líneas vacías. Cada elemento es UNA instrucción completa.
 */
export function instrucciones(dockerfile: string): string[] {
  const out: string[] = [];
  let acumulada = "";
  for (const cruda of dockerfile.split("\n")) {
    const linea = cruda.replace(/\r$/, "");
    if (acumulada === "" && (linea.trim() === "" || linea.trim().startsWith("#"))) continue;
    if (linea.trimEnd().endsWith("\\")) {
      acumulada += linea.trimEnd().slice(0, -1) + " ";
      continue;
    }
    out.push((acumulada + linea).trim().replace(/\s+/g, " "));
    acumulada = "";
  }
  if (acumulada.trim() !== "") out.push(acumulada.trim().replace(/\s+/g, " "));
  return out;
}

export interface Etapa {
  /** `AS nombre`, o null si la etapa no se nombró. */
  nombre: string | null;
  /** Instrucciones de la etapa, en orden (la propia FROM incluida). */
  lineas: string[];
}

/** Las etapas (`FROM …`) del Dockerfile; los `ARG` globales previos van en la primera. */
export function etapas(dockerfile: string): Etapa[] {
  const out: Etapa[] = [];
  let pendientes: string[] = [];
  for (const ins of instrucciones(dockerfile)) {
    if (/^FROM\s/i.test(ins)) {
      const as = /\sAS\s+(\S+)\s*$/i.exec(ins);
      out.push({ nombre: as ? as[1] : null, lineas: [...pendientes, ins] });
      pendientes = [];
    } else if (out.length === 0) {
      pendientes.push(ins);
    } else {
      out[out.length - 1].lineas.push(ins);
    }
  }
  return out;
}

/** Variables de una instrucción `ENV` (formas `K=V K2=V2` y `K V`), sin comillas. */
export function variablesDeEnv(instruccion: string): Map<string, string> {
  const vars = new Map<string, string>();
  const cuerpo = instruccion.replace(/^ENV\s+/i, "");
  if (!cuerpo.includes("=")) {
    const [clave, ...resto] = cuerpo.split(/\s+/);
    vars.set(clave, resto.join(" "));
    return vars;
  }
  for (const par of cuerpo.match(/[^\s=]+=(?:"[^"]*"|'[^']*'|\S*)/g) ?? []) {
    const i = par.indexOf("=");
    vars.set(par.slice(0, i), par.slice(i + 1).replace(/^(["'])(.*)\1$/, "$2"));
  }
  return vars;
}

/**
 * Defectos del gate del LOGIN DEV en un Dockerfile. Vacío = la imagen no puede
 * pintar el panel. Cada cadena dice QUÉ y DÓNDE, para que el rojo se lea solo.
 */
export function auditarGateLoginDev(dockerfile: string): string[] {
  const defectos: string[] = [];
  const todas = etapas(dockerfile);
  const build = todas.filter((e) => e.lineas.some((l) => /^RUN\b.*npm run build/.test(l)));
  if (build.length !== 1) {
    defectos.push(
      `se esperaba UNA etapa que corra \`npm run build\` y hay ${build.length}: el gate no sabe ` +
        "dónde mirar",
    );
  }
  for (const etapa of todas) {
    for (const l of etapa.lineas) {
      if (new RegExp(`^ARG\\s+${FLAG_LOGIN_DEV}(=|\\s|$)`).test(l)) {
        defectos.push(
          `\`${l}\` (etapa ${etapa.nombre ?? "sin nombre"}): un ARG con ese nombre abre la puerta ` +
            "a `--build-arg`; la variable se fija, no se parametriza",
        );
      }
      if (new RegExp(`\\$\\{?${FLAG_LOGIN_DEV}\\b`).test(l)) {
        defectos.push(`\`${l}\`: la variable se interpola, así que su valor vendría de fuera`);
      }
    }
  }
  if (build.length === 1) {
    const lineas = build[0].lineas;
    const iBuild = lineas.findIndex((l) => /^RUN\b.*npm run build/.test(l));
    let valor: string | undefined;
    let despues = false;
    lineas.forEach((l, i) => {
      if (!/^ENV\s/i.test(l)) return;
      const v = variablesDeEnv(l).get(FLAG_LOGIN_DEV);
      if (v === undefined) return;
      if (i < iBuild) valor = v;
      else despues = true;
    });
    if (valor === undefined) {
      defectos.push(
        despues
          ? `\`ENV ${FLAG_LOGIN_DEV}\` va DESPUÉS del \`npm run build\`: Vite ya congeló ` +
              "import.meta.env y la imagen se construye con el valor heredado"
          : `falta \`ENV ${FLAG_LOGIN_DEV}=false\` en la etapa de build: lo que no se declara, ` +
              "se hereda (T-1.62)",
      );
    } else if (valor !== "false") {
      defectos.push(
        `\`ENV ${FLAG_LOGIN_DEV}=${valor}\`: la imagen de producción pintaría el panel LOGIN DEV ` +
          "contra un endpoint que la nube no monta",
      );
    }
  }
  return defectos;
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

describe("[T-6.05] el gate del LOGIN DEV en la imagen lo lee un test bloqueante", () => {
  const REAL = readFileSync(DOCKERFILE, "utf8");

  it("la imagen real fija VITE_DEV_TOKEN_ENABLED=false en el build y no tiene ARG homónimo", () => {
    expect(auditarGateLoginDev(REAL)).toEqual([]);
  });

  it(".dockerignore sigue excluyendo web/.env*: el segundo cerrojo de T-1.62", () => {
    const reglas = readFileSync(DOCKERIGNORE, "utf8")
      .split("\n")
      .map((l) => l.trim())
      .filter((l) => l !== "" && !l.startsWith("#"));
    expect(reglas).toEqual(expect.arrayContaining(["web/.env", "web/.env.*"]));
  });

  // ---- mutaciones sobre el fichero REAL: cada una tiene que poner esto en rojo ----

  // La PRIMERA aparición de `VITE_DEV_TOKEN_ENABLED=false` en el fichero real está en
  // un comentario: una mutación ingenua sólo cambiaría la prosa y el gate seguiría
  // (con razón) en verde. Se muta la línea del ENV: la que lleva la continuación.
  const LINEA_ENV = new RegExp(`^(\\s+)${FLAG_LOGIN_DEV}=false( \\\\)$`, "m");

  it("un `true` tecleado se caza", () => {
    const mutado = REAL.replace(LINEA_ENV, `$1${FLAG_LOGIN_DEV}=true$2`);
    expect(mutado).not.toBe(REAL);
    expect(auditarGateLoginDev(mutado).join("\n")).toMatch(/=true/);
  });

  it("borrar la línea se caza (lo que no se declara, se hereda)", () => {
    const mutado = REAL.replace(new RegExp(`\\s*${FLAG_LOGIN_DEV}=false \\\\\n`), "\n");
    expect(mutado).not.toBe(REAL);
    expect(auditarGateLoginDev(mutado).join("\n")).toMatch(/falta `ENV/);
  });

  it("un ARG homónimo añadido de buena fe se caza, aunque el ENV siga en false", () => {
    const mutado = REAL.replace(
      'ARG VITE_COGNITO_AUTHORITY=""',
      `ARG ${FLAG_LOGIN_DEV}=false\nARG VITE_COGNITO_AUTHORITY=""`,
    );
    expect(mutado).not.toBe(REAL);
    expect(auditarGateLoginDev(mutado).join("\n")).toMatch(/ARG .*--build-arg/);
  });

  it("parametrizarla (`ENV X=${X}`) se caza por las dos vías", () => {
    const mutado = REAL.replace(LINEA_ENV, `$1${FLAG_LOGIN_DEV}=\${${FLAG_LOGIN_DEV}}$2`);
    expect(mutado).not.toBe(REAL);
    const defectos = auditarGateLoginDev(mutado);
    expect(defectos.join("\n")).toMatch(/se interpola/);
    expect(defectos.join("\n")).toMatch(/pintaría el panel/);
  });

  it("moverla DESPUÉS del `npm run build` se caza: Vite ya congeló import.meta.env", () => {
    const sinLinea = REAL.replace(new RegExp(`\\s*${FLAG_LOGIN_DEV}=false \\\\\n`), "\n");
    const mutado = sinLinea.replace(
      /(RUN cd web && npm run build[^\n]*\n)/,
      `$1ENV ${FLAG_LOGIN_DEV}=false\n`,
    );
    expect(mutado).not.toBe(sinLinea);
    expect(auditarGateLoginDev(mutado).join("\n")).toMatch(/DESPUÉS/);
  });

  // ---- el analizador, sobre formas que Docker acepta y un regex ingenuo no ----

  it("pliega las continuaciones: el ENV multilínea real trae sus siete variables", () => {
    const build = etapas(REAL).find((e) => e.nombre === "build");
    expect(build).toBeDefined();
    const env = build!.lineas.filter((l) => /^ENV\s/.test(l));
    expect(env).toHaveLength(1);
    const vars = variablesDeEnv(env[0]);
    expect(vars.get(FLAG_LOGIN_DEV)).toBe("false");
    expect(vars.get("VITE_API_BASE_URL")).toBe("/api");
    expect(vars.size).toBe(7);
  });

  it("entiende la forma legada `ENV CLAVE valor` y las comillas", () => {
    expect(variablesDeEnv("ENV VITE_DEV_TOKEN_ENABLED false").get(FLAG_LOGIN_DEV)).toBe("false");
    expect(variablesDeEnv("ENV A=\"x y\" B='z'")).toEqual(
      new Map([
        ["A", "x y"],
        ["B", "z"],
      ]),
    );
  });

  it("reparte los ARG globales (antes del primer FROM) en la primera etapa y los caza", () => {
    const df = [
      `ARG ${FLAG_LOGIN_DEV}`,
      "FROM node:22-slim AS build",
      `ENV ${FLAG_LOGIN_DEV}=false`,
      "RUN cd web && npm run build",
      "FROM caddy:2-alpine",
    ].join("\n");
    expect(etapas(df)[0].lineas[0]).toBe(`ARG ${FLAG_LOGIN_DEV}`);
    expect(auditarGateLoginDev(df).join("\n")).toMatch(/ARG/);
  });

  it("sin etapa de build no afirma nada en verde: lo dice", () => {
    expect(auditarGateLoginDev("FROM caddy:2-alpine\nCOPY dist /srv").join("\n")).toMatch(
      /UNA etapa/,
    );
  });
});
