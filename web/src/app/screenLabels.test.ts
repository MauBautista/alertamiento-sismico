import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * [T-2.64.a] Contrato RUTA ↔ PANTALLA.
 *
 * `data-screen-label="NN Texto"` es el nombre estable de cada pantalla: los
 * mockups del design system, los e2e y producto se refieren a ellas por ese
 * número, no por el copy del h1 (que cambia). Si dos pantallas comparten
 * número, "la 05" deja de identificar a una sola cosa y toda referencia
 * anterior queda ambigua.
 *
 * Este test existe por un defecto REAL: `/audit` (`AuditPage.tsx`) y
 * `/building/:siteId` (`BuildingPage.tsx`) declaraban AMBAS el prefijo "05".
 * Se detectó durante T-2.59 y se anotó como deuda en un comentario de
 * `e2e/layout.spec.ts` en lugar de arreglarse. Un comentario no para un merge;
 * este test sí.
 *
 * Vive en vitest y NO en e2e a propósito: `.github/workflows/e2e.yml` se
 * dispara por `workflow_dispatch` y su paso de specs lleva
 * `continue-on-error: true` — el e2e no es gate de merge. Todo assert que deba
 * bloquear un merge tiene que correr en la suite que sí lo es.
 *
 * Vive junto a `routes.tsx` porque la invariante no es "el marcado está bien":
 * es que el conjunto de pantallas numeradas y el conjunto de rutas de la app
 * sean el MISMO conjunto.
 */

const SRC = resolve(process.cwd(), "src");
const ROUTES_FILE = join(SRC, "app", "routes.tsx");

/**
 * Mismo recorrido que `styles/cssContract.test.ts:25-32`. Se replica en vez de
 * importarse porque allí vive dentro de un fichero `.test.ts`: importarlo
 * ejecutaría su módulo y registraría sus `describe` una segunda vez.
 */
function walk(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) walk(path, out);
    else out.push(path);
  }
  return out;
}

/** Marcado de producción. Los `.test.tsx` consultan etiquetas, no las declaran. */
const TSX = walk(SRC).filter((f) => f.endsWith(".tsx") && !f.includes(".test."));

const LABEL_RE = /data-screen-label="([^"]+)"/g;
/** Una PANTALLA de la serie: dos dígitos, un espacio, y el nombre. */
const NUMBERED_RE = /^(\d{2}) (.+)$/;

interface Declared {
  readonly file: string;
  readonly label: string;
}

const DECLARED: Declared[] = TSX.flatMap((file) =>
  [...readFileSync(file, "utf8").matchAll(LABEL_RE)].map((m) => ({ file, label: m[1] })),
);

const SCREENS = DECLARED.filter((d) => NUMBERED_RE.test(d.label));

/**
 * Etiquetas SIN número: quedan fuera del contrato POR DISEÑO, no por descuido.
 *
 * `data-screen-label` también marca regiones internas que los e2e necesitan
 * localizar pero que no son una pantalla con ruta propia — hoy la cola de
 * incidentes de `console/IncidentTable.tsx`. Numerarlas rompería la serie
 * (habría más números que rutas) y exigirlas en `routes.tsx` es imposible: no
 * tienen ruta. Quien lea esto y crea que falta un número: comprueba primero si
 * la cosa tiene entrada en `routes.tsx`.
 */
const REGIONS = DECLARED.filter((d) => !NUMBERED_RE.test(d.label));

/* =====================================================================
   LADO RUTAS — qué pantallas declara la app
   =====================================================================
   Toda ruta de pantalla se envuelve en `<RouteGuard routeKey="...">`: ese
   `routeKey` es la clave de la matriz de permisos (`RouteGuard.tsx:8`) y por
   tanto la lista canónica de pantallas navegables. Las rutas restantes con
   `element` —`/`, `/auth/callback`, el `*` de 404 y los dos envoltorios sin
   `path` (`RequireSession`, `AppShell`)— no son pantallas de la serie: no
   viven bajo el shell ni aparecen en la navegación.
   ===================================================================== */

const ROUTES_SRC = readFileSync(ROUTES_FILE, "utf8");

const IMPORTED_FROM = new Map<string, string>();
for (const m of ROUTES_SRC.matchAll(/^import\s+(\w+)\s+from\s+"([^"]+)";$/gm)) {
  IMPORTED_FROM.set(m[1], resolve(dirname(ROUTES_FILE), `${m[2]}.tsx`));
}

interface GuardedRoute {
  readonly routeKey: string;
  readonly component: string;
  readonly file: string | undefined;
}

const GUARDED: GuardedRoute[] = [
  ...ROUTES_SRC.matchAll(/<RouteGuard\s+routeKey="([^"]+)">\s*<(\w+)\s*\/>/g),
].map((m) => ({ routeKey: m[1], component: m[2], file: IMPORTED_FROM.get(m[2]) }));

const rel = (f: string) => relative(SRC, f);

/* =====================================================================
   EL CONTRATO
   ===================================================================== */

describe("contrato ruta↔pantalla — dos pantallas con el mismo número no son dos pantallas", () => {
  it("el escaneo encuentra marcado y rutas (si esto falla, el resto miente)", () => {
    expect(TSX.length, "no se escaneó ningún .tsx de producción").toBeGreaterThan(50);
    expect(GUARDED.length, "no se leyó ninguna ruta de routes.tsx").toBeGreaterThanOrEqual(5);
    expect(
      GUARDED.filter((g) => g.file === undefined),
      "hay rutas cuyo componente no se pudo resolver a un fichero: el parser de imports se quedó corto",
    ).toEqual([]);
  });

  it("cada prefijo numérico identifica a UNA sola pantalla", () => {
    const byPrefix = new Map<string, Declared[]>();
    for (const screen of SCREENS) {
      const prefix = NUMBERED_RE.exec(screen.label)![1];
      byPrefix.set(prefix, [...(byPrefix.get(prefix) ?? []), screen]);
    }

    const duplicated = [...byPrefix.entries()]
      .filter(([, list]) => list.length > 1)
      .map(
        ([prefix, list]) =>
          `${prefix} → ${list.map((d) => `${rel(d.file)} ("${d.label}")`).join(" · ")}`,
      );

    expect(
      duplicated,
      `prefijos de pantalla repetidos:\n  ${duplicated.join("\n  ")}\n` +
        "Renumera la pantalla más nueva — no dupliques el número.",
    ).toEqual([]);
  });

  it("la serie va de 01 hasta el total, sin huecos", () => {
    const numbers = SCREENS.map((s) => Number(NUMBERED_RE.exec(s.label)![1])).sort((a, b) => a - b);
    const expected = SCREENS.map((_, i) => i + 1);

    expect(
      numbers,
      `la serie de pantallas es ${numbers.join(", ")} y debería ser ${expected.join(", ")}. ` +
        "Un hueco significa que se borró una pantalla sin renumerar las de después.",
    ).toEqual(expected);
  });

  it("hay exactamente una pantalla numerada por cada ruta de la app", () => {
    const labelOfRoute = GUARDED.map((route) => {
      const found = [...readFileSync(route.file!, "utf8").matchAll(LABEL_RE)]
        .map((m) => m[1])
        .filter((label) => NUMBERED_RE.test(label));
      return { routeKey: route.routeKey, file: rel(route.file!), labels: found };
    });

    const broken = labelOfRoute
      .filter((r) => r.labels.length !== 1)
      .map((r) => `${r.routeKey} (${r.file}) declara ${r.labels.length}: [${r.labels.join(", ")}]`);
    expect(
      broken,
      `rutas sin exactamente un data-screen-label numerado:\n  ${broken.join("\n  ")}`,
    ).toEqual([]);

    // …y al revés: ninguna pantalla numerada puede vivir fuera de una ruta.
    const routeFiles = new Set(GUARDED.map((g) => g.file));
    const orphans = SCREENS.filter((s) => !routeFiles.has(s.file)).map(
      (s) => `"${s.label}" en ${rel(s.file)}`,
    );
    expect(
      orphans,
      `pantallas numeradas que no corresponden a ninguna ruta:\n  ${orphans.join("\n  ")}. ` +
        "Si no es una pantalla navegable, quítale el número (ver REGIONS en este fichero).",
    ).toEqual([]);

    expect(SCREENS.length, "sobran o faltan pantallas respecto a las rutas").toBe(GUARDED.length);
  });

  it("las etiquetas SIN número quedan fuera del contrato a propósito", () => {
    // Fijar la lista aquí es lo que impide que el siguiente lector las tome por
    // un bug de numeración. Si aparece una nueva, decide conscientemente si es
    // una pantalla (→ número + ruta) o una región (→ aquí).
    expect(REGIONS.map((r) => r.label).sort()).toEqual(["Incidents queue"]);
  });
});
