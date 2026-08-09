// [T-2.84.c · hueco RO-7.a] Censo DERIVADO de quién pinta dato de servidor.
//
// Este módulo no afirma nada: **deriva**. Las afirmaciones —y la deuda
// declarada— viven en `src/serverDataCensus.test.ts`. Se separa para poder
// probar el propio analizador contra fuentes sintéticas: una guarda que nadie
// ha visto fallar no es una guarda (ver `cssContract.test.ts`, que hace lo
// mismo con su lexer).
//
// LA SEÑAL ESTRUCTURAL
// --------------------
// «Pintar dato de servidor» no es una propiedad sintáctica: no hay una palabra
// que buscar, y una lista de nombres de componentes envejece con el primer
// fichero nuevo. Lo que sí es estructural es de dónde ENTRA el dato:
//
//   1. Los transportes remotos son un conjunto CERRADO y pequeño (`TRANSPORTES`).
//   2. Sobre el grafo de imports se calcula el CIERRE de productores: una
//      función es productora si llama a un transporte o a otra productora.
//      Nadie se apunta a mano: `useFleet` es productora porque llama a
//      `useQuery`, y `FleetPage` lo es porque llama a `useFleet`.
//   3. Dentro de cada componente se propaga el TINTE: toda variable cuyo
//      inicializador toca un valor productor queda teñida, hasta punto fijo.
//   4. Se recorre el JSX sabiendo si el nodo actual cuelga de un `<StateFrame>`.
//      Un valor teñido que se pinta FUERA de un StateFrame es el defecto.
//
// Por qué se culpa al DUEÑO de la consulta y no al hijo presentacional: el
// dueño es el único que puede distinguir «vacío» de «cargando» de «viejo» —
// `KpiStrip` recibe `kpis` y no tiene forma de saber si son ceros reales o la
// API caída (T-2.59). Y no hay escapatoria por delegación: pasar un valor
// teñido a un hijo fuera del StateFrame CUENTA como pintarlo, así que no se
// puede lavar el dato metiéndolo en un componente hijo.

import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";

import ts from "typescript";

/* =====================================================================
   ENTRADA
   ===================================================================== */

export interface FuenteEntrada {
  /** Ruta absoluta (o pseudo-absoluta en los tests del propio analizador). */
  path: string;
  text: string;
}

/** Un transporte = módulo + export por el que entra dato del servidor. */
export interface Transporte {
  /** Ruta del módulo que DEFINE el export (no un re-export). */
  file: string;
  export: string;
}

export interface OpcionesCenso {
  /** Raíz para las claves relativas del informe. */
  root: string;
  /** Transportes propios del proyecto (además de los hooks de lectura de TanStack). */
  transportes: Transporte[];
}

/**
 * Hooks de LECTURA de TanStack Query. `useMutation` queda fuera a propósito:
 * una mutación no es un dato que la pantalla presente como hecho vigente, es
 * el resultado de una acción que el operador acaba de disparar. `useQueryClient`
 * tampoco entrega datos.
 */
export const HOOKS_DE_LECTURA: readonly string[] = [
  "useQuery",
  "useQueries",
  "useInfiniteQuery",
  "useSuspenseQuery",
  "useSuspenseInfiniteQuery",
  "useSuspenseQueries",
];

const PAQUETE_QUERY = "@tanstack/react-query";

/* =====================================================================
   SALIDA
   ===================================================================== */

export interface SitioPintado {
  /** `features/fleet/FleetPage.tsx::FleetPage` */
  clave: string;
  linea: number;
  /** `{hijo}` · `<Kpi value>` · `<div title>` */
  donde: string;
  /** Identificadores teñidos que se pintan ahí. */
  ids: string[];
}

export interface MarcoDeEstado {
  /** `features/fleet/FleetPage.tsx` */
  fichero: string;
  /**
   * `fichero#ETIQUETA` — la clave estable del marco. Se usa la `label` (que es
   * el nombre humano del panel) y NO el número de línea: una línea añadida
   * arriba movería tres entradas y pondría el censo rojo sin que nada haya
   * cambiado, que es como una guarda se gana el ser relajada.
   */
  clave: string;
  linea: number;
  /** Entradas de las cuatro que NO están cableadas. */
  faltan: string[];
}

export interface ComponenteConDato {
  clave: string;
  fichero: string;
  nombre: string;
  /** Variables teñidas por el cierre de productores. */
  tenidos: string[];
  /** true si el componente materializa al menos un `<StateFrame>`. */
  tieneMarco: boolean;
}

export interface Censo {
  /** `file::name` de toda función que devuelve dato de servidor. */
  productores: string[];
  /** Componentes que POSEEN dato de servidor (llaman a una productora). */
  componentes: ComponenteConDato[];
  /** Clave → identificadores teñidos que pinta FUERA de un StateFrame. */
  fueraDelMarco: Record<string, string[]>;
  /** Detalle por sitio, para el mensaje de error. */
  sitios: SitioPintado[];
  /** Todo `<StateFrame>` del marcado de producción y qué entradas le faltan. */
  marcos: MarcoDeEstado[];
  /** `fichero:línea` donde se materializa `data-state` fuera de StateFrame.tsx. */
  dataStateForaneo: string[];
}

/* =====================================================================
   RECORRIDO DEL ÁRBOL
   ===================================================================== */

export function recorrer(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) recorrer(path, out);
    else out.push(path);
  }
  return out;
}

/** Marcado y lógica de PRODUCCIÓN: sin tests, sin `.d.ts`, sin utilería de test. */
export function fuentesDeProduccion(root: string): FuenteEntrada[] {
  return recorrer(root)
    .filter(
      (f) =>
        (f.endsWith(".ts") || f.endsWith(".tsx")) &&
        !f.includes(".test.") &&
        !f.endsWith(".d.ts") &&
        !f.includes(`${join("", "test-utils")}`),
    )
    .map((path) => ({ path, text: readFileSync(path, "utf8") }));
}

export function ficherosDeTest(root: string): FuenteEntrada[] {
  return recorrer(root)
    .filter((f) => f.includes(".test.") && (f.endsWith(".ts") || f.endsWith(".tsx")))
    .map((path) => ({ path, text: readFileSync(path, "utf8") }));
}

/* =====================================================================
   MÓDULOS
   ===================================================================== */

interface Modulo {
  file: string;
  sf: ts.SourceFile;
  /** local → {target, name} de cada import de VALOR (los `type` no cuentan). */
  imports: Map<string, { target: string; name: string }>;
  /** `export { x } from "./y"` — hay que atravesarlos o el transporte no se ve. */
  reexports: Map<string, { target: string; name: string }>;
  /** nombre → nodo función (declaración o const arrow/function-expression). */
  fns: Map<string, ts.Node>;
}

function resolverModulo(desde: string, spec: string, conocidos: Set<string>): string {
  if (!spec.startsWith(".")) return spec;
  const base = resolve(desde, "..", spec);
  for (const cand of [
    `${base}.ts`,
    `${base}.tsx`,
    join(base, "index.ts"),
    join(base, "index.tsx"),
  ]) {
    if (conocidos.has(cand) || existsSync(cand)) return cand;
  }
  return base;
}

function parsear(fuentes: FuenteEntrada[]): Map<string, Modulo> {
  const conocidos = new Set(fuentes.map((f) => f.path));
  const mods = new Map<string, Modulo>();
  for (const { path, text } of fuentes) {
    mods.set(path, {
      file: path,
      sf: ts.createSourceFile(path, text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX),
      imports: new Map(),
      reexports: new Map(),
      fns: new Map(),
    });
  }
  for (const m of mods.values()) {
    for (const st of m.sf.statements) {
      if (
        ts.isImportDeclaration(st) &&
        st.importClause &&
        !st.importClause.isTypeOnly &&
        ts.isStringLiteral(st.moduleSpecifier)
      ) {
        const target = resolverModulo(m.file, st.moduleSpecifier.text, conocidos);
        const clause = st.importClause;
        if (clause.name) m.imports.set(clause.name.text, { target, name: "default" });
        if (clause.namedBindings && ts.isNamedImports(clause.namedBindings)) {
          for (const el of clause.namedBindings.elements) {
            if (el.isTypeOnly) continue;
            m.imports.set(el.name.text, { target, name: (el.propertyName ?? el.name).text });
          }
        }
      }
      if (
        ts.isExportDeclaration(st) &&
        st.moduleSpecifier &&
        ts.isStringLiteral(st.moduleSpecifier) &&
        st.exportClause &&
        ts.isNamedExports(st.exportClause) &&
        !st.isTypeOnly
      ) {
        const target = resolverModulo(m.file, st.moduleSpecifier.text, conocidos);
        for (const el of st.exportClause.elements) {
          if (el.isTypeOnly) continue;
          m.reexports.set(el.name.text, { target, name: (el.propertyName ?? el.name).text });
        }
      }
    }
    recolectarFunciones(m);
  }
  return mods;
}

/** Sigue la cadena de re-exports hasta el módulo que DEFINE el símbolo. */
function origen(
  mods: Map<string, Modulo>,
  target: string,
  name: string,
  depth = 0,
): { target: string; name: string } {
  if (depth > 8) return { target, name };
  const re = mods.get(target)?.reexports.get(name);
  return re ? origen(mods, re.target, re.name, depth + 1) : { target, name };
}

function recolectarFunciones(m: Modulo): void {
  const visit = (n: ts.Node): void => {
    if (ts.isFunctionDeclaration(n) && n.name) m.fns.set(n.name.text, n);
    else if (
      ts.isVariableDeclaration(n) &&
      ts.isIdentifier(n.name) &&
      n.initializer &&
      (ts.isArrowFunction(n.initializer) || ts.isFunctionExpression(n.initializer))
    )
      m.fns.set(n.name.text, n.initializer);
    ts.forEachChild(n, visit);
  };
  ts.forEachChild(m.sf, visit);
}

/** Identificadores en posición de llamada dentro de un nodo. */
function llamadas(n: ts.Node): Set<string> {
  const out = new Set<string>();
  const visit = (x: ts.Node): void => {
    if (ts.isCallExpression(x) && ts.isIdentifier(x.expression)) out.add(x.expression.text);
    ts.forEachChild(x, visit);
  };
  ts.forEachChild(n, visit);
  return out;
}

/**
 * Identificadores RAÍZ de una expresión: de `fleet.cabinets.length` sale
 * `fleet`, no `cabinets` ni `length`. Sin esto, una propiedad llamada `data`
 * teñiría por accidente cualquier expresión que la mencionara.
 *
 * NO baja al JSX anidado, y eso es lo que hace útil al censo: en
 * `{open && <StateFrame loading={catalog.loading}>…</StateFrame>}` lo que se
 * pinta al desnudo es `open`, no `catalog` — el `catalog` está dentro del
 * marco. Contándolo, TODO envoltorio condicional saldría rojo y el censo
 * denunciaría precisamente al código que sí guarda.
 */
function raices(n: ts.Node): Set<string> {
  const out = new Set<string>();
  const visit = (x: ts.Node): void => {
    if (ts.isJsxElement(x) || ts.isJsxSelfClosingElement(x) || ts.isJsxFragment(x)) return;
    if (ts.isPropertyAccessExpression(x)) {
      visit(x.expression);
      return;
    }
    if (ts.isIdentifier(x)) {
      out.add(x.text);
      return;
    }
    ts.forEachChild(x, visit);
  };
  visit(n);
  return out;
}

function nombresLigados(n: ts.BindingName, out: string[] = []): string[] {
  if (ts.isIdentifier(n)) out.push(n.text);
  else for (const el of n.elements) if (ts.isBindingElement(el)) nombresLigados(el.name, out);
  return out;
}

/* =====================================================================
   EL CENSO
   ===================================================================== */

/** Atributos que NO presentan un dato: gobiernan estilo, identidad o acción. */
const ATRIBUTOS_NO_PRESENTACIONALES = new Set([
  "className",
  "style",
  "key",
  "ref",
  "id",
  "htmlFor",
  "type",
  "role",
  "disabled",
  "hidden",
  "checked",
  "readOnly",
  "tabIndex",
  "aria-pressed",
  "aria-hidden",
  "aria-busy",
  "aria-expanded",
  "aria-selected",
  "aria-current",
]);

const CUATRO_ENTRADAS = ["loading", "error", "empty", "staleSince"] as const;

export function censar(fuentes: FuenteEntrada[], opts: OpcionesCenso): Censo {
  const mods = parsear(fuentes);
  const clave = (file: string, name: string) => `${relative(opts.root, file)}::${name}`;

  /** ¿El local `name` de `m` es un transporte remoto? */
  const esTransporte = (m: Modulo, local: string): boolean => {
    const imp = m.imports.get(local);
    if (!imp) return false;
    if (imp.target === PAQUETE_QUERY) return HOOKS_DE_LECTURA.includes(imp.name);
    const o = origen(mods, imp.target, imp.name);
    return opts.transportes.some((t) => t.file === o.target && t.export === o.name);
  };

  // --- cierre de productores (punto fijo sobre el grafo de imports) ---
  const productores = new Set<string>();
  for (let ronda = 0, cambio = true; cambio && ronda < 50; ronda += 1) {
    cambio = false;
    for (const m of mods.values()) {
      for (const [name, fn] of m.fns) {
        const key = `${m.file}::${name}`;
        if (productores.has(key)) continue;
        for (const c of llamadas(fn)) {
          let hit = esTransporte(m, c) || (m.fns.has(c) && productores.has(`${m.file}::${c}`));
          if (!hit) {
            const imp = m.imports.get(c);
            if (imp && mods.has(imp.target)) {
              const o = origen(mods, imp.target, imp.name);
              hit = productores.has(`${o.target}::${o.name}`);
            }
          }
          if (hit) {
            productores.add(key);
            cambio = true;
            break;
          }
        }
      }
    }
  }

  /** Locales de `m` que, llamados, devuelven dato de servidor. */
  const productorasVisibles = (m: Modulo): Set<string> => {
    const s = new Set<string>();
    for (const [local, imp] of m.imports) {
      if (esTransporte(m, local)) {
        s.add(local);
        continue;
      }
      if (mods.has(imp.target)) {
        const o = origen(mods, imp.target, imp.name);
        if (productores.has(`${o.target}::${o.name}`)) s.add(local);
      }
    }
    for (const name of m.fns.keys()) if (productores.has(`${m.file}::${name}`)) s.add(name);
    return s;
  };

  const componentes: ComponenteConDato[] = [];
  const sitios: SitioPintado[] = [];
  const marcos: MarcoDeEstado[] = [];
  const dataStateForaneo: string[] = [];

  for (const m of mods.values()) {
    const linea = (n: ts.Node) => m.sf.getLineAndCharacterOfPosition(n.getStart(m.sf)).line + 1;
    const rel = relative(opts.root, m.file);

    // --- todo `<StateFrame>` del fichero, y `data-state` a mano ---
    const inspeccionarMarcado = (n: ts.Node): void => {
      if (ts.isJsxElement(n) || ts.isJsxSelfClosingElement(n)) {
        const abre = ts.isJsxElement(n) ? n.openingElement : n;
        const tag = abre.tagName.getText(m.sf);
        const props = abre.attributes.properties.filter(ts.isJsxAttribute);
        const nombres = props.map((a) => a.name.getText(m.sf));
        if (tag === "StateFrame") {
          const etiqueta = props.find((a) => a.name.getText(m.sf) === "label")?.initializer;
          const nombre =
            etiqueta !== undefined && ts.isStringLiteral(etiqueta)
              ? etiqueta.text
              : `#${marcos.filter((f) => f.fichero === rel).length}`;
          marcos.push({
            fichero: rel,
            clave: `${rel}#${nombre}`,
            linea: linea(abre),
            faltan: CUATRO_ENTRADAS.filter((x) => !nombres.includes(x)),
          });
        }
        for (const a of props) {
          if (a.name.getText(m.sf) === "data-state") {
            dataStateForaneo.push(`${rel}:${linea(a)}`);
          }
        }
      }
      ts.forEachChild(n, inspeccionarMarcado);
    };
    ts.forEachChild(m.sf, inspeccionarMarcado);

    if (!m.file.endsWith(".tsx")) continue;
    const productoras = productorasVisibles(m);

    for (const [name, fn] of m.fns) {
      if (!/^[A-Z]/.test(name) || !contieneJsx(fn)) continue;

      // --- tinte, hasta punto fijo ---
      const decls: ts.VariableDeclaration[] = [];
      const recogerDecls = (n: ts.Node): void => {
        if (ts.isVariableDeclaration(n) && n.initializer) decls.push(n);
        ts.forEachChild(n, recogerDecls);
      };
      ts.forEachChild(fn, recogerDecls);

      const tenidos = new Set<string>();
      for (const d of decls) {
        const dentro = new Set<string>();
        const cv = (n: ts.Node): void => {
          if (ts.isCallExpression(n) && ts.isIdentifier(n.expression))
            dentro.add(n.expression.text);
          ts.forEachChild(n, cv);
        };
        cv(d.initializer as ts.Node);
        if ([...dentro].some((c) => productoras.has(c)))
          for (const b of nombresLigados(d.name)) tenidos.add(b);
      }
      for (let cambio = true; cambio; ) {
        cambio = false;
        for (const d of decls) {
          const bn = nombresLigados(d.name);
          if (bn.every((x) => tenidos.has(x))) continue;
          if ([...raices(d.initializer as ts.Node)].some((u) => tenidos.has(u))) {
            for (const b of bn)
              if (!tenidos.has(b)) {
                tenidos.add(b);
                cambio = true;
              }
          }
        }
      }
      if (tenidos.size === 0) continue;

      // --- recorrido JSX con contexto de guarda ---
      let tieneMarco = false;
      const anota = (n: ts.Node, donde: string, ids: string[]): void => {
        if (ids.length > 0)
          sitios.push({ clave: clave(m.file, name), linea: linea(n), donde, ids });
      };
      const tenidosDe = (n: ts.Node) => [...raices(n)].filter((u) => tenidos.has(u)).sort();

      const andar = (n: ts.Node, guardado: boolean): void => {
        if (ts.isJsxElement(n) || ts.isJsxSelfClosingElement(n)) {
          const abre = ts.isJsxElement(n) ? n.openingElement : n;
          const tag = abre.tagName.getText(m.sf);
          const esMarco = tag === "StateFrame";
          if (esMarco) tieneMarco = true;
          for (const a of abre.attributes.properties) {
            if (esMarco) continue; // props del propio marco = cableado de la guarda
            if (ts.isJsxAttribute(a)) {
              const an = a.name.getText(m.sf);
              if (ATRIBUTOS_NO_PRESENTACIONALES.has(an) || /^(on[A-Z]|data-)/.test(an)) continue;
              if (a.initializer && ts.isJsxExpression(a.initializer) && a.initializer.expression) {
                if (!guardado) anota(a, `<${tag} ${an}>`, tenidosDe(a.initializer.expression));
                andarDentro(a.initializer.expression, guardado);
              }
            } else if (ts.isJsxSpreadAttribute(a)) {
              if (!guardado) anota(a, `<${tag} {...}>`, tenidosDe(a.expression));
              andarDentro(a.expression, guardado);
            }
          }
          if (ts.isJsxElement(n)) for (const c of n.children) andar(c, guardado || esMarco);
          return;
        }
        if (ts.isJsxFragment(n)) {
          for (const c of n.children) andar(c, guardado);
          return;
        }
        if (ts.isJsxExpression(n)) {
          if (n.expression) {
            if (!guardado) anota(n, "{hijo}", tenidosDe(n.expression));
            andarDentro(n.expression, guardado);
          }
          return;
        }
        ts.forEachChild(n, (c) => andar(c, guardado));
      };
      /** Baja por una expresión buscando JSX anidado (callbacks de `.map`, ternarios…). */
      const andarDentro = (n: ts.Node, guardado: boolean): void => {
        const visit = (x: ts.Node): void => {
          if (ts.isJsxElement(x) || ts.isJsxSelfClosingElement(x) || ts.isJsxFragment(x))
            andar(x, guardado);
          else ts.forEachChild(x, visit);
        };
        ts.forEachChild(n, visit);
      };
      ts.forEachChild(fn, (c) => andar(c, false));

      componentes.push({
        clave: clave(m.file, name),
        fichero: rel,
        nombre: name,
        tenidos: [...tenidos].sort(),
        tieneMarco,
      });
    }
  }

  const fueraDelMarco: Record<string, string[]> = {};
  for (const s of sitios) {
    const previo = fueraDelMarco[s.clave] ?? [];
    fueraDelMarco[s.clave] = [...new Set([...previo, ...s.ids])].sort();
  }

  return {
    productores: [...productores].map((p) => {
      const i = p.lastIndexOf("::");
      return clave(p.slice(0, i), p.slice(i + 2));
    }),
    componentes: componentes.sort((a, b) => a.clave.localeCompare(b.clave)),
    fueraDelMarco,
    sitios,
    marcos: marcos.filter((f) => f.faltan.length > 0),
    dataStateForaneo,
  };
}

function contieneJsx(fn: ts.Node): boolean {
  let hay = false;
  const visit = (n: ts.Node): void => {
    if (ts.isJsxElement(n) || ts.isJsxSelfClosingElement(n) || ts.isJsxFragment(n)) hay = true;
    if (!hay) ts.forEachChild(n, visit);
  };
  ts.forEachChild(fn, visit);
  return hay;
}

/* =====================================================================
   COBERTURA CONDUCTUAL — ¿existe la PRUEBA de los cuatro estados?
   ===================================================================== */

/**
 * Ficheros de producción cubiertos por un test que llama a `expectFourStates`.
 * Derivado de los imports relativos del test, no de una convención de nombres:
 * un test puede probar un componente que vive en otro fichero.
 */
export function ficherosConPruebaDeCuatroEstados(
  tests: FuenteEntrada[],
  produccion: FuenteEntrada[],
  root: string,
): Set<string> {
  const conocidos = new Set(produccion.map((f) => f.path));
  const out = new Set<string>();
  for (const { path, text } of tests) {
    if (!/\bexpectFourStates\b/.test(text)) continue;
    const sf = ts.createSourceFile(path, text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
    for (const st of sf.statements) {
      if (!ts.isImportDeclaration(st) || !ts.isStringLiteral(st.moduleSpecifier)) continue;
      if (st.importClause?.isTypeOnly) continue;
      const spec = st.moduleSpecifier.text;
      if (!spec.startsWith(".")) continue;
      const target = resolverModulo(path, spec, conocidos);
      if (conocidos.has(target)) out.add(relative(root, target));
    }
  }
  return out;
}
