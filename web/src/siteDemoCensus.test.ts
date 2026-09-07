// [T-6.04] EL CENSO DE LA CINTA DEMO: toda superficie que pinta un sitio pasa por la función.
//
// T-5.05 enseñó a la consola qué sitio es simulado (`esDeDemostracion`) y lo pintó
// en dos superficies. Las demás —la cola de incidentes, el triage, el detalle, el
// historial de simulacros— pintaban el mismo sitio sin marca (U-07), y un marcado
// a medias enseña la regla falsa «sin cinta ⇒ real».
//
// Una función central sólo gobierna si nadie puede pintar un sitio sin pasar por
// ella. Éste es el hermano de `serverDataCensus.test.ts` para ese hecho, y como
// él DERIVA la población en vez de enumerarla:
//
//   1. Qué ficheros PINTAN un sitio: los de producción cuyo marcado (fuera de
//      comentarios y tipos) toca un nombre o código de sitio —`site_name`,
//      `siteName`, `site.name`, `site.code`, `s.name`…—. Las formas están escritas
//      abajo (`TOKENS`), y son formas, no una lista de componentes: la pantalla
//      número siete entra sola el día que alguien escriba `row.siteName`.
//   2. Qué ficheros PASAN por la función: los que importan `SiteLabel`,
//      `siteLabelText` o `esDeDemostracion`.
//
// Todo fichero del grupo 1 tiene que estar en el grupo 2 o en `EXENTOS` con su
// razón escrita (comparado por IGUALDAD: una exención que ya no hace falta pone el
// censo rojo y obliga a borrarla; una nueva no entra sin explicarse).

import { relative, resolve } from "node:path";

import ts from "typescript";
import { describe, expect, it } from "vitest";

import { fuentesDeProduccion, type FuenteEntrada } from "./test-utils/serverDataCensus";

const SRC = resolve(process.cwd(), "src");
const PRODUCCION = fuentesDeProduccion(SRC).filter((f) => f.path.endsWith(".tsx"));

/**
 * Las FORMAS con las que este árbol nombra un sitio en el marcado. Se buscan en
 * el texto de los nodos JSX (expresiones y atributos), nunca en comentarios ni
 * en declaraciones de tipos: `siteName: string` en una interfaz no pinta nada.
 */
const TOKENS = [
  /\bsite_name\b/,
  /\bsiteName\b/,
  /\bsiteCode\b/,
  /\bsite_code\b/,
  /\bsite\??\.name\b/,
  /\bsite\??\.code\b/,
  /\bsite\.data\??\.name\b/,
  /\bfocusSite\??\.name\b/,
  /\bs\.name\b/,
  /\bs\.code\b/,
];

/** Lo que cuenta como «pasar por la función». */
const PUERTAS = new Set(["SiteLabel", "siteLabelText", "esDeDemostracion"]);

interface Pintor {
  fichero: string;
  /** `línea: texto` de cada expresión JSX que toca un sitio. */
  sitios: string[];
  pasaPorLaFuncion: boolean;
}

/** Expresiones JSX (contenedores `{…}` y valores de atributo) de un fichero. */
function expresionesJsx(sf: ts.SourceFile): ts.Node[] {
  const out: ts.Node[] = [];
  const visit = (n: ts.Node): void => {
    if (ts.isJsxExpression(n) && n.expression) out.push(n.expression);
    ts.forEachChild(n, visit);
  };
  visit(sf);
  return out;
}

function importaPuerta(sf: ts.SourceFile): boolean {
  for (const st of sf.statements) {
    if (!ts.isImportDeclaration(st) || !st.importClause || st.importClause.isTypeOnly) continue;
    const clause = st.importClause;
    if (clause.name && PUERTAS.has(clause.name.text)) return true;
    if (clause.namedBindings && ts.isNamedImports(clause.namedBindings)) {
      for (const el of clause.namedBindings.elements) {
        if (!el.isTypeOnly && PUERTAS.has((el.propertyName ?? el.name).text)) return true;
      }
    }
  }
  return false;
}

export function censarPintores(fuentes: FuenteEntrada[], root: string): Pintor[] {
  const out: Pintor[] = [];
  for (const { path, text } of fuentes) {
    const sf = ts.createSourceFile(path, text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
    const sitios: string[] = [];
    for (const expr of expresionesJsx(sf)) {
      const texto = expr.getText(sf);
      if (TOKENS.some((t) => t.test(texto))) {
        const linea = sf.getLineAndCharacterOfPosition(expr.getStart(sf)).line + 1;
        sitios.push(`${linea}: ${texto.replace(/\s+/g, " ").slice(0, 60)}`);
      }
    }
    if (sitios.length === 0) continue;
    out.push({ fichero: relative(root, path), sitios, pasaPorLaFuncion: importaPuerta(sf) });
  }
  return out.sort((a, b) => a.fichero.localeCompare(b.fichero));
}

/* =====================================================================
   LA DEUDA DECLARADA — quién toca un sitio en el marcado sin pasar por la función
   ===================================================================== */

/**
 * Fichero → por qué toca un nombre de sitio en el marcado y NO pinta la cinta.
 * Sólo caben dos clases de razón: (a) no PINTA el sitio (lo edita, lo pasa a un
 * hijo que sí lo pinta) o (b) el token casa con algo que no es un sitio.
 */
const EXENTOS: Record<string, string> = {
  "features/console/ConsolePage.tsx":
    "(a) REPARTO. El wall no pinta ningún nombre: resuelve `siteInfoOf` (nombre + coords + CÓDIGO) " +
    "para la cola y pasa `siteName`/`siteCode` a `AlertBanner`, `DetailPanel` y `EpicenterModal`, " +
    "que sí pintan con `SiteLabel`/`siteLabelText`. Lo que se vigila aquí es que el código VIAJE: " +
    "si dejara de pasarlo, el hijo pintaría sin cinta y sus propios tests lo dirían.",
  "features/fleet/GatewayAcuse.tsx":
    "(a) TÍTULO YA ROTULADO. Recibe `siteName` como TEXTO desde `FleetAdmin`, que lo construye con " +
    "`siteLabelText(site.name, site.code)`: la cinta viaja pegada al nombre (« · DEMO»). El " +
    "formulario no conoce el código porque no lo necesita; conocerlo sería una segunda verdad.",
  "features/fleet/GatewayForm.tsx":
    "(a) TÍTULO YA ROTULADO. Igual que GatewayAcuse: `FleetAdmin` le pasa " +
    "`siteLabelText(editing.site.name, editing.site.code)` y el título del formulario lo imprime " +
    "tal cual, cinta incluida. Quien monte este formulario desde otro sitio tiene que rotular " +
    "antes; el censo de FleetAdmin (que sí importa la función) es donde se ve.",
  "features/scene/SceneStrip.tsx":
    "(a) REPARTO. La franja resuelve el sitio de la alerta en el snapshot del mapa y pasa " +
    "`siteName` y `siteCode` a `AlertLine`, que pinta con `SiteLabel`. No imprime el nombre.",
};

describe("censo de la cinta DEMO · quién pinta un sitio pasa por la función (T-6.04)", () => {
  const pintores = censarPintores(PRODUCCION, SRC);

  it("el barrido encuentra a los pintores conocidos (no-vacuidad)", () => {
    const ficheros = pintores.map((p) => p.fichero);
    for (const f of [
      "features/console/IncidentTable.tsx",
      "features/triage/TriageTable.tsx",
      "features/console/DetailPanel.tsx",
      "features/fleet/SiteCard.tsx",
    ]) {
      expect(ficheros, `${f} dejó de pintar un sitio: revisa TOKENS`).toContain(f);
    }
    expect(pintores.length).toBeGreaterThan(10);
  });

  it("toda exención lleva su razón escrita", () => {
    for (const [k, v] of Object.entries(EXENTOS)) {
      expect(v.length, `la razón de ${k} es demasiado corta para ser una razón`).toBeGreaterThan(
        120,
      );
    }
  });

  it("nadie pinta un sitio sin pasar por la función, salvo los exentos declarados", () => {
    const sinFuncion = pintores.filter((p) => !p.pasaPorLaFuncion);
    const detalle = sinFuncion
      .map((p) => `  ${p.fichero}\n${p.sitios.map((s) => `    L${s}`).join("\n")}`)
      .join("\n");
    expect(
      sinFuncion.map((p) => p.fichero),
      "FICHEROS QUE PINTAN UN NOMBRE O CÓDIGO DE SITIO SIN PASAR POR `SiteLabel` / " +
        "`siteLabelText` / `esDeDemostracion`. Un sitio simulado saldría ahí sin cinta y " +
        "enseñaría «sin cinta ⇒ real». Pinta el nombre con <SiteLabel name code /> (o " +
        `siteLabelText en texto plano); no añadas la exención sin su razón:\n${detalle}`,
    ).toEqual(Object.keys(EXENTOS).sort());
  });

  it("una exención cuyo fichero ya pasa por la función (o ya no pinta sitios) sobra", () => {
    // Igualdad en la otra dirección: la lista no puede acumular exenciones
    // muertas. Si `SiteForm` un día pinta con `SiteLabel`, hay que borrar su línea.
    for (const f of Object.keys(EXENTOS)) {
      const p = pintores.find((x) => x.fichero === f);
      expect(p, `${f} ya no toca ningún sitio en el marcado: borra su exención`).toBeDefined();
      expect(p?.pasaPorLaFuncion, `${f} ya pasa por la función: borra su exención`).toBe(false);
    }
  });
});

/* =====================================================================
   EL PROPIO ANALIZADOR — sin esto el censo podría estar leyendo aire
   ===================================================================== */

describe("el analizador de la cinta · probado contra fuentes sintéticas", () => {
  const analizar = (archivos: Record<string, string>) =>
    censarPintores(
      Object.entries(archivos).map(([path, text]) => ({ path, text })),
      "/censo",
    );

  it("caza `{row.siteName}` a pelo y CALLA cuando el fichero importa SiteLabel", () => {
    const sinPuerta = analizar({
      "/censo/A.tsx": `export default function A({ row }) { return <td>{row.siteName}</td>; }`,
    });
    expect(sinPuerta.map((p) => [p.fichero, p.pasaPorLaFuncion])).toEqual([["A.tsx", false]]);
    const conPuerta = analizar({
      "/censo/B.tsx": `
        import SiteLabel from "../components/SiteLabel";
        export default function B({ row }) { return <td><SiteLabel name={row.siteName} code={row.siteCode} /></td>; }`,
    });
    expect(conPuerta.map((p) => [p.fichero, p.pasaPorLaFuncion])).toEqual([["B.tsx", true]]);
  });

  it("un `siteName` en una interfaz o en un comentario NO es pintar", () => {
    const medido = analizar({
      "/censo/T.tsx": `
        // aquí se habla de site.name en prosa
        interface P { siteName: string }
        export default function T(p: P) { return <p>{p.other}</p>; }`,
    });
    expect(medido).toEqual([]);
  });

  it("`tenant.name` o `p.name` no son sitios: el token exige la forma del sitio", () => {
    const medido = analizar({
      "/censo/U.tsx": `export default function U({ tenant, p }) { return <p>{tenant.name} {p.name}</p>; }`,
    });
    expect(medido).toEqual([]);
  });

  it("un import SÓLO de tipo de la puerta no cuenta como pasar por ella", () => {
    const medido = analizar({
      "/censo/V.tsx": `
        import type { SiteLabelProps as SiteLabel } from "../components/SiteLabel";
        export default function V({ site }) { return <h2>{site.name}</h2>; }`,
    });
    expect(medido.map((p) => p.pasaPorLaFuncion)).toEqual([false]);
  });
});
