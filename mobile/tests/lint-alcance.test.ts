// [T-2.125] EL LINT DE MÓVIL COBRABA MENOS TERRENO DEL QUE PARECÍA.
//
// `expo lint` sin argumentos NO linta el proyecto: linta `src`, `app` y
// `components` — y sólo los que existan. Está escrito a fuego en el propio CLI
// (`DEFAULT_INPUTS`, `@expo/cli/build/src/lint/lintAsync.js`) y la ayuda del
// comando lo dice: «Lint all files in /src, /app, /components». En este árbol
// eso deja fuera `tests/**` ENTERO —18 ficheros, los que prueban las pantallas—
// más los config de la raíz.
//
// El daño nunca fue el error suelto que había ahí dentro. Fue que **nadie podía
// saber cuánto más había sin mirar**: es la misma familia que «67 tests se
// saltaban en silencio» (`T-2.58`/`T-2.59`) y que la imagen de consola que
// llevaba semanas sin construirse (`T-2.124`). Un gate que parece cubrir más de
// lo que cubre es peor que no tenerlo, porque se confía en él.
//
// ESTE TEST ES EL GATE DE VERDAD, y por qué vive aquí y no en el paso de lint:
// el job `mobile` de CI y el Makefile invocan `npx expo lint` **a pelo**, con lo
// que su alcance es el implícito. `npm run lint` ya pasa el alcance explícito
// (ver `package.json`), pero mientras esos dos sitios no lo usen, lo único que
// sí corre sobre todo el árbol en CI es `npm test`. Así que el lint de lo que
// queda fuera se corre AQUÍ, y el conjunto se calcula — no se enumera:
//
//   · `DEFAULT_INPUTS` se LEE del propio CLI de Expo. Si Expo lo cambia, esto se
//     entera; si se lo inventara aquí, este fichero sería la segunda lista que
//     diverge.
//   · Los ficheros salen de git (rastreados + nuevos sin ignorar), así que un
//     directorio nuevo —`e2e/`, `scripts/`— entra solo el día que exista.
//
// El día que CI pase a `npm run lint`, este test seguirá verde sin tocarlo: se
// limitará a re-lintar lo que ya se lintó, o nada.
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";

const RAIZ = resolve(__dirname, "..");

/** Extensiones que `expo lint` pasa a eslint por defecto (`--ext`). */
const LINTABLES = [".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"];

/** Dónde puede quedar el CLI de Expo según cómo haya aplanado npm el árbol. */
const CANDIDATOS_CLI = [
  join(RAIZ, "node_modules", "expo", "node_modules", "@expo", "cli"),
  join(RAIZ, "node_modules", "@expo", "cli"),
];

/**
 * Los directorios que `expo lint` linta cuando no se le pasa ninguno, LEÍDOS
 * del CLI de Expo. Es el productor de la regla; copiarlos aquí sería fundar la
 * misma divergencia que esta ficha cierra.
 */
export function defaultInputsDeExpo(): string[] {
  for (const base of CANDIDATOS_CLI) {
    const fichero = join(base, "build", "src", "lint", "lintAsync.js");
    if (!existsSync(fichero)) {
      continue;
    }
    const bloque = readFileSync(fichero, "utf8").split("DEFAULT_INPUTS = [")[1]?.split("]")[0];
    if (bloque === undefined) {
      throw new Error(`DEFAULT_INPUTS no está en ${fichero}: el CLI cambió, esto no está verde`);
    }
    return [...bloque.matchAll(/'([^']+)'|"([^"]+)"/g)].map((m) => m[1] ?? m[2]);
  }
  throw new Error(`No se encontró el CLI de Expo en ${CANDIDATOS_CLI.join(" ni ")}`);
}

/** Rastreados + nuevos sin ignorar: lo que hoy hay en el árbol de `mobile/`. */
function ficherosDelArbol(): string[] {
  const salida = execFileSync("git", ["ls-files", "--cached", "--others", "--exclude-standard"], {
    cwd: RAIZ,
    encoding: "utf8",
    maxBuffer: 32 * 1024 * 1024,
  });
  return salida.split("\n").filter((f) => f !== "" && LINTABLES.some((e) => f.endsWith(e)));
}

const DEFAULT_INPUTS = defaultInputsDeExpo();
const TODOS = ficherosDelArbol();
const FUERA_DEL_ALCANCE = TODOS.filter(
  (f) => !DEFAULT_INPUTS.some((dir) => f === dir || f.startsWith(`${dir}/`)),
);

describe("[T-2.125] el alcance del lint de móvil", () => {
  it("el censo no está vacío (si esto falla, el resto de este bloque miente)", () => {
    expect(DEFAULT_INPUTS).toContain("src");
    expect(TODOS.length).toBeGreaterThan(50);
  });

  it("`npm run lint` NO se apoya en el alcance implícito de `expo lint`", () => {
    // Un `"lint": "expo lint"` a secas es exactamente el defecto de esta ficha:
    // parece que linta el proyecto y linta tres directorios. El script tiene que
    // decir sobre qué corre.
    const pkg = JSON.parse(readFileSync(join(RAIZ, "package.json"), "utf8")) as {
      scripts: Record<string, string>;
    };
    expect(pkg.scripts.lint.trim()).not.toBe("expo lint");
    expect(pkg.scripts.lint).toMatch(/expo lint\s+\S/);
  });

  it("todo lo que queda fuera de ese alcance está limpio de errores Y de avisos", () => {
    if (FUERA_DEL_ALCANCE.length === 0) {
      // El alcance por defecto ya lo cubre todo: no hay nada que rescatar.
      return;
    }
    const eslint = join(RAIZ, "node_modules", ".bin", "eslint");
    expect(existsSync(eslint)).toBe(true);
    let salida = "";
    let codigo = 0;
    try {
      salida = execFileSync(
        eslint,
        [
          ...FUERA_DEL_ALCANCE,
          // Un fichero ignorado por `eslint.config.js` no es un hallazgo: se
          // calla en vez de contarse como aviso.
          "--no-warn-ignored",
          "--no-error-on-unmatched-pattern",
          // Los avisos también cuentan. Un aviso que nadie ve es un error que
          // todavía no ha pasado.
          "--max-warnings=0",
          "--no-cache",
        ],
        { cwd: RAIZ, encoding: "utf8", maxBuffer: 32 * 1024 * 1024 },
      );
    } catch (e) {
      const err = e as { status?: number; stdout?: string; stderr?: string };
      codigo = err.status ?? 1;
      salida = `${err.stdout ?? ""}${err.stderr ?? ""}`;
    }
    expect(
      `eslint sobre los ${FUERA_DEL_ALCANCE.length} ficheros fuera del alcance de \`expo lint\`:\n${salida}`,
    ).toBe(`eslint sobre los ${FUERA_DEL_ALCANCE.length} ficheros fuera del alcance de \`expo lint\`:\n`);
    expect(codigo).toBe(0);
  }, 180000);
});
