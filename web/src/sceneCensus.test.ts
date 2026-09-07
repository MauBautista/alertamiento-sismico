// [T-6.01] EL CENSO DE LA ESCENA: que nadie decida ni pinte la escena fuera de la tabla.
//
// `SCENE_PRECEDENCE` (`features/scene/scene.ts`) decide qué escena manda —alerta
// real > aviso > simulacro > mantenimiento > demo— y `SceneStrip` la pinta UNA
// vez, en el shell, encima de las seis rutas. Pero una tabla central sólo
// gobierna si nadie puede esquivarla desde su componente, y hay exactamente dos
// formas de esquivarla:
//
//   1. LEER una fuente de escena (`useActiveDrill`, `useMaintenanceWindows`,
//      `useDemoMode`, `useLiveIncidents`) desde una pantalla y decidir con ella.
//      Es lo que hacía `ConsolePage` con `hasLiveIncident={critical !== null}`:
//      dos booleanos a mano, y el badge «LA ALERTA REAL DOMINA» con cualquier
//      incidente crítico, incluido un aviso instrumental (U-28).
//   2. PINTAR un banner de escena desde una página. Es lo que hacía la propia
//      consola con los tres banners como hijos suyos: en `/fleet`, `/triage`,
//      `/tenants`, `/audit` y `/building` no había rastro de nada (U-04).
//
// Las dos señales son ESTRUCTURALES y se derivan del código, no de una lista:
//
//   · Quién LEE: el cierre de productores del censo de dato de servidor
//     (`test-utils/serverDataCensus.ts`), con las cuatro fuentes como únicos
//     transportes (`soloPropios`). Nadie se apunta a mano: un hook que envuelva
//     a `useActiveDrill` es productor, y el componente que lo llame, lector.
//   · Quién PINTA: los imports de valor que cruzan la frontera de
//     `features/scene/`. Los banners y la decisión (`resolveScene`,
//     `SCENE_PRECEDENCE`, `DEGRADES_UNDER_ALERT`) sólo pueden importarse desde
//     dentro; hacia fuera sólo salen `SceneStrip` (al shell) y los dos helpers
//     que CONSULTAN la tabla sin decidir (`sceneAlert`, `authorizes`).
//
// LAS LISTAS SE COMPARAN POR IGUALDAD, NUNCA POR CONTENCIÓN. Misma lección que
// `serverDataCensus.test.ts` y `statePrecedenceCensus.test.ts`: una excepción que
// puede crecer sola no es una excepción, es un agujero.

import { basename, relative, resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { SCENE_PRECEDENCE } from "./features/scene/scene";
import {
  censar,
  fuentesDeProduccion,
  type FuenteEntrada,
  type Transporte,
} from "./test-utils/serverDataCensus";
import { arbolDeLaPagina, parsear } from "./test-utils/statePrecedenceCensus";

const SRC = resolve(process.cwd(), "src");
const PRODUCCION = fuentesDeProduccion(SRC);
const MODS = parsear(PRODUCCION);

/** La carpeta de la escena: la única frontera que este censo vigila. */
const ESCENA = "features/scene";

/**
 * LAS CUATRO FUENTES de escena. Es lo ÚNICO escrito a mano en este censo, y es
 * un listado de TRANSPORTES, no de consumidores: los consumidores se derivan.
 */
const FUENTES: Transporte[] = [
  { file: resolve(SRC, "features/console/useLiveIncidents.ts"), export: "useLiveIncidents" },
  { file: resolve(SRC, "features/console/useActiveDrill.ts"), export: "useActiveDrill" },
  {
    file: resolve(SRC, "features/console/useMaintenanceWindows.ts"),
    export: "useMaintenanceWindows",
  },
  { file: resolve(SRC, "features/console/useDemoMode.ts"), export: "useDemoMode" },
];

const CENSO = censar(PRODUCCION, { root: SRC, transportes: FUENTES, soloPropios: true });

/* =====================================================================
   C-0 · NO-VACUIDAD — si el barrido no encuentra nada, el resto miente
   ===================================================================== */

describe("censo de escena · el barrido encuentra las fuentes", () => {
  it("las cuatro fuentes existen y alguien las consume", () => {
    // Las fuentes son TRANSPORTES: el cierre de productores contiene a quien las
    // llama, no a ellas. Si ninguna tuviera consumidor, el censo cuadraría con
    // una lista vacía y no vigilaría nada.
    for (const f of FUENTES) {
      expect(
        PRODUCCION.some((p) => p.path === f.file),
        `${f.file} desapareció`,
      ).toBe(true);
    }
    expect(CENSO.productores).toContain("features/scene/SceneStrip.tsx::SceneStrip");
    expect(CENSO.componentes.length).toBeGreaterThan(2);
  });

  it("la tabla que este censo defiende es la que decidió T-6.01", () => {
    expect([...SCENE_PRECEDENCE]).toEqual(["alert", "notice", "drill", "maintenance", "demo"]);
  });
});

/* =====================================================================
   C-1 · QUIÉN LEE la escena — y por qué tiene derecho
   ===================================================================== */

/**
 * Clave → razón. Sólo UNO lee para PINTAR escena: la franja. El resto lee el
 * mismo dato para otra cosa, y la razón dice cuál. Una pantalla nueva que llame
 * a una fuente sale roja y tiene que escribir aquí para qué la quiere.
 */
const LECTORES: Record<string, string> = {
  "features/scene/SceneStrip.tsx::SceneStrip":
    "LA FRANJA. El único componente que lee las cuatro fuentes para decidir la escena " +
    "(`resolveScene`) y pintarla, una vez, en el shell y encima de las seis rutas. Cada " +
    "fuente baja a su banner como prop; los banners no llaman a ningún hook.",
  "features/console/ConsolePage.tsx::ConsoleWall":
    "LA COLA DEL WALL. Lee incidentes para la tabla de incidentes abiertos, el sitio en foco " +
    "y la tarjeta detallada de la alerta (`AlertBanner`, con PGA). El incidente que define " +
    "la escena lo elige `sceneAlert()` de la tabla, no esta página: la tarjeta del wall y la " +
    "línea del shell hablan del mismo incidente. No monta ningún banner de escena.",
  "features/console/DrillControls.tsx::DrillControls":
    "LOS BOTONES. Lee el simulacro para GATEAR INICIAR SIMULACRO (`drill === null`, " +
    "`loading`) y disparar las mutaciones; pinta el fallo de INICIAR junto al botón. No " +
    "pinta banner: el simulacro vivo, armado o retenido lo declara la franja del shell.",
  "features/fleet/FleetPage.tsx::FleetPage":
    "LA ADMINISTRACIÓN. Lee las ventanas de mantenimiento para ABRIRLAS y para el badge " +
    "aditivo de cada gabinete tapado en /fleet, dentro de su propio marco. No decide escena " +
    "ni pinta el banner de alarmas mudas: ése lo pinta la franja, también en /fleet.",
};

describe("censo · quién lee una fuente de escena, y para qué (criterio 4)", () => {
  it("toda lectura lleva su razón escrita", () => {
    for (const [k, v] of Object.entries(LECTORES)) {
      expect(v.length, `la razón de ${k} es demasiado corta para ser una razón`).toBeGreaterThan(
        120,
      );
    }
  });

  it("cuadra con los lectores declarados, por igualdad", () => {
    const medido = CENSO.componentes.map((c) => c.clave).sort();
    const detalle = CENSO.componentes
      .map((c) => `  ${c.clave} — teñidos: ${c.tenidos.join(", ")}`)
      .join("\n");
    expect(
      medido,
      "COMPONENTES QUE LEEN `drill`, `maintenance`, `demo_mode` o los incidentes. Si es " +
        "para pintar escena, NO: la escena la pinta `SceneStrip` desde la tabla. Si es para " +
        `otra cosa, escribe la razón en LECTORES:\n${detalle}`,
    ).toEqual(Object.keys(LECTORES).sort());
  });
});

/* =====================================================================
   C-2 · QUIÉN PINTA la escena — lo que cruza la frontera de features/scene
   ===================================================================== */

/**
 * Imports de VALOR que salen de `features/scene/` hacia el resto del árbol de
 * producción: `fichero → ["módulo#export", …]`. Derivado del grafo de imports.
 */
function cruzanLaFrontera(
  mods: ReturnType<typeof parsear>,
  root: string,
  frontera: string,
): Record<string, string[]> {
  const out: Record<string, string[]> = {};
  const dentro = (file: string) => relative(root, file).startsWith(`${frontera}/`);
  for (const m of mods.values()) {
    if (dentro(m.file)) continue;
    const salidas = [...m.imports.values()]
      .filter((imp) => dentro(imp.target))
      .map((imp) => `${basename(imp.target).replace(/\.tsx?$/, "")}#${imp.name}`)
      .sort();
    if (salidas.length > 0) out[relative(root, m.file)] = [...new Set(salidas)];
  }
  return out;
}

/**
 * Lo ÚNICO que puede salir de la escena, y a dónde. `SceneStrip` al shell (es
 * quien la monta); `sceneAlert` a la consola (elige el incidente de su tarjeta
 * CON la tabla, no contra ella); `authorizes` a `AlertBanner` (viste la carcasa
 * según la tabla). Ni un banner, ni `resolveScene`, ni `DEGRADES_UNDER_ALERT`:
 * quien los importe desde fuera está decidiendo o pintando escena por su cuenta.
 */
const PINTORES: Record<string, string[]> = {
  "features/console/AlertBanner.tsx": ["scene#authorizes"],
  "features/console/ConsolePage.tsx": ["scene#sceneAlert"],
  "shell/AppShell.tsx": ["SceneStrip#default"],
};

describe("censo · nadie pinta ni decide escena fuera de la franja", () => {
  it("lo que cruza la frontera de features/scene es exactamente lo declarado", () => {
    expect(cruzanLaFrontera(MODS, SRC, ESCENA)).toEqual(PINTORES);
  });

  it("la franja cuelga del SHELL, no de una página", () => {
    const shell = arbolDeLaPagina(MODS, SRC, "shell/AppShell.tsx");
    for (const f of [
      "features/scene/SceneStrip.tsx",
      "features/scene/AlertLine.tsx",
      "features/scene/DrillBanner.tsx",
      "features/scene/MaintenanceBanner.tsx",
      "features/scene/DemoModeBanner.tsx",
    ]) {
      expect(shell, `${f} no cuelga del shell`).toContain(f);
    }
    // …y de la consola NO cuelga ninguno: era el defecto de U-04.
    const consola = arbolDeLaPagina(MODS, SRC, "features/console/ConsolePage.tsx");
    expect(consola.filter((f) => f.startsWith(`${ESCENA}/`))).toEqual([]);
  });

  it("el badge «LA ALERTA REAL DOMINA» sólo existe en la franja", () => {
    // Sin comentarios: la tabla explica el badge en su cabecera, y la prosa no
    // pinta nada.
    const sinComentarios = (t: string) =>
      t.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
    const donde = PRODUCCION.filter((f) =>
      sinComentarios(f.text).includes("LA ALERTA REAL DOMINA"),
    ).map((f) => relative(SRC, f.path));
    expect(donde).toEqual(["features/scene/DrillBanner.tsx"]);
  });
});

/* =====================================================================
   EL PROPIO ANALIZADOR — sin esto el censo podría estar leyendo aire
   ===================================================================== */

const RAIZ = "/censo";
const FUENTE_FALSA: Transporte[] = [{ file: "/censo/useDrill.ts", export: "useDrill" }];

function analizar(archivos: Record<string, string>) {
  const fuentes: FuenteEntrada[] = Object.entries(archivos).map(([path, text]) => ({ path, text }));
  return {
    censo: censar(fuentes, { root: RAIZ, transportes: FUENTE_FALSA, soloPropios: true }),
    mods: parsear(fuentes),
  };
}

describe("el analizador de escena · probado contra fuentes sintéticas", () => {
  it("caza a la pantalla que LLAMA a una fuente de escena, y no a la que recibe el dato por prop", () => {
    const { censo } = analizar({
      "/censo/useDrill.ts": `export function useDrill() { return {}; }`,
      "/censo/Pagina.tsx": `
        import { useDrill } from "./useDrill";
        import Banner from "./Banner";
        export default function Pagina() {
          const d = useDrill();
          return <Banner data={d} />;
        }`,
      "/censo/Banner.tsx": `
        export default function Banner({ data }) { return <div>{data.x}</div>; }`,
    });
    expect(censo.componentes.map((c) => c.clave)).toEqual(["Pagina.tsx::Pagina"]);
  });

  it("con `soloPropios` un `useQuery` cualquiera NO es fuente de escena", () => {
    const { censo } = analizar({
      "/censo/Otra.tsx": `
        import { useQuery } from "@tanstack/react-query";
        export default function Otra() {
          const q = useQuery({ queryKey: ["x"], queryFn: f });
          return <div>{q.data}</div>;
        }`,
    });
    expect(censo.componentes).toEqual([]);
  });

  it("sigue el cierre: un hook que envuelve a la fuente también tiñe", () => {
    const { censo } = analizar({
      "/censo/useDrill.ts": `export function useDrill() { return {}; }`,
      "/censo/useEscena.ts": `
        import { useDrill } from "./useDrill";
        export function useEscena() { return useDrill(); }`,
      "/censo/Pagina.tsx": `
        import { useEscena } from "./useEscena";
        export default function Pagina() { const e = useEscena(); return <p>{e.x}</p>; }`,
    });
    expect(censo.componentes.map((c) => c.clave)).toEqual(["Pagina.tsx::Pagina"]);
  });

  it("caza el import de un banner desde fuera de la frontera", () => {
    const { mods } = analizar({
      "/censo/features/scene/DrillBanner.tsx": `export default function DrillBanner() { return <p />; }`,
      "/censo/features/scene/scene.ts": `export function sceneAlert() { return null; }`,
      "/censo/features/fleet/FleetPage.tsx": `
        import DrillBanner from "../scene/DrillBanner";
        import { sceneAlert } from "../scene/scene";
        export default function FleetPage() { return <DrillBanner />; }`,
      "/censo/features/scene/SceneStrip.tsx": `
        import DrillBanner from "./DrillBanner";
        export default function SceneStrip() { return <DrillBanner />; }`,
    });
    // Lo de dentro de la frontera no cuenta; lo de fuera sale con nombre y export.
    expect(cruzanLaFrontera(mods, RAIZ, "features/scene")).toEqual({
      "features/fleet/FleetPage.tsx": ["DrillBanner#default", "scene#sceneAlert"],
    });
  });

  it("un import SÓLO de tipo no cruza nada", () => {
    const { mods } = analizar({
      "/censo/features/scene/scene.ts": `export type Scene = "normal"; export function f() {}`,
      "/censo/features/fleet/FleetPage.tsx": `
        import type { Scene } from "../scene/scene";
        export default function FleetPage(p: { s: Scene }) { return <p>{p.s}</p>; }`,
    });
    expect(cruzanLaFrontera(mods, RAIZ, "features/scene")).toEqual({});
  });
});
