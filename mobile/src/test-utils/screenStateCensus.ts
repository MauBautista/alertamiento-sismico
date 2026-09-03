// [T-2.111] CENSO DERIVADO DE LAS PANTALLAS MÓVILES (regla de oro 7).
//
// Espejo de `web/src/test-utils/serverDataCensus.ts`, con la señal estructural
// que móvil sí tiene y la consola no: **la tabla de rutas de `expo-router` ES
// el sistema de ficheros**. `src/app/**/*.tsx` no es una lista que alguien
// mantiene, es el censo entero de pantallas de la app, y crece solo con el
// fichero nuevo. Por eso aquí no hay ni una lista de pantallas escrita a mano:
// lo único que se declara es la DEUDA, y se compara por igualdad.
//
// Este módulo no afirma nada: **deriva**. Las afirmaciones y la deuda viven en
// `src/screenStateCensus.test.ts`, separadas para poder probar el propio
// analizador contra fuentes sintéticas — una guarda que nadie ha visto fallar
// no es una guarda.
//
// LAS TRES SEÑALES
// ----------------
//  1. POSEER DATO DE SERVIDOR. Axioma cerrado: los hooks de LECTURA de
//     `@tanstack/react-query`. Todo lo demás se deriva por cierre sobre el
//     grafo de imports — `useAlertState` es productora porque llama a
//     `useQuery`, y `crisis.tsx` lo es porque llama a `useAlertState`. Nadie se
//     apunta a mano. `useMutation` queda FUERA a propósito (igual que en la
//     consola): el resultado de una acción que la persona acaba de disparar no
//     es un dato que la pantalla presente como hecho vigente — ése es el
//     desenlace, y lo vigila la señal 3.
//  2. DECLARAR LOS CUATRO ESTADOS. Todo `<StateFrame>` de una ruta tiene que
//     cablear sus cuatro entradas. Callarse `staleSinceMs` AFIRMA «este dato no
//     puede envejecer»; callarse `empty`, «nunca está vacío».
//  3. TENER DESENLACE. El cliente del SDK **lanza** cuando muere `fetch`. Una
//     llamada al SDK dentro de una ruta que no esté en un `try…catch` ni
//     encadene `.catch(` es un `busy` que se queda encendido y un dato que se
//     pierde sin decir nada — el defecto exacto de T-2.111. Se exime lo que
//     esté dentro de un hook de react-query, que es quien posee ese rechazo.

// El `tsconfig.json` del paquete acota `types` a `["jest"]` (es una app de RN:
// los tipos de node no deben colarse en el código de la app). Este módulo corre
// SÓLO bajo jest, así que pide los tipos de node explícitamente, aquí, en vez de
// abrirlos para todo el árbol.
/// <reference types="node" />
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";

import ts from "typescript";

export interface FuenteEntrada {
  path: string;
  text: string;
}

/**
 * Hooks de LECTURA de TanStack Query — el único axioma del censo.
 * `useMutation` y `useQueryClient` quedan fuera (ver cabecera).
 */
export const HOOKS_DE_LECTURA: readonly string[] = [
  "useQuery",
  "useQueries",
  "useInfiniteQuery",
  "useSuspenseQuery",
  "useSuspenseInfiniteQuery",
];

const PAQUETE_QUERY = "@tanstack/react-query";
const PAQUETE_SDK = "@takab/sdk";

/** Las cuatro entradas del `StateFrame` móvil (`@/ui/StateFrame`). */
export const CUATRO_ENTRADAS = ["loading", "error", "empty", "staleSinceMs"] as const;

/**
 * [T-5.21] Señales de FALLO. Un `staleSinceMs` que dependa de una de ellas está
 * contestando la pregunta equivocada: la edad de un dato no depende de si el
 * refetch falló. Con red sana y datos de hace diez minutos, todas valen `false`
 * y la pantalla afirma frescura.
 *
 * `error` entra con su forma exacta y no por subcadena: `hydrationError` es otra
 * cosa —el fallo de abrir la cola local— y `retenidoDesde` no menciona ningún
 * fallo. Un censo que buscara «error» dentro de cualquier identificador
 * marcaría a los dos.
 */
export const SENALES_DE_FALLO = ["isError", "failureCount", "error", "isRefetchError"] as const;

/** Campos que significan «de cuándo es este dato». Los tres nombres que usa el repo. */
export const CAMPOS_DE_FRESCURA = ["stale", "staleSince", "staleSinceMs"] as const;

export interface FrescuraPorError {
  clave: string;
  fichero: string;
  linea: number;
  /** Las señales de fallo que aparecen en la expresión. */
  senales: string[];
  /** La expresión tal cual, para que el fallo diga qué hay que cambiar. */
  expresion: string;
}

export interface MarcoDeEstado {
  /** `app/crisis.tsx#0` — fichero + ordinal del marco dentro del fichero. */
  clave: string;
  fichero: string;
  linea: number;
  faltan: string[];
}

export interface PromesaSinDesenlace {
  /** `app/panic.tsx::panicVoteSitesSiteIdManualActivationVotesPost` */
  clave: string;
  fichero: string;
  linea: number;
  operacion: string;
}

export interface Censo {
  /** `file::name` de toda función que devuelve dato de servidor. */
  productores: string[];
  /** Rutas de `src/app` (clave relativa a `src`), todas. */
  rutas: string[];
  /** Rutas cuyo componente llama a una productora. */
  rutasConDato: string[];
  /** …y que NO materializan ningún `<StateFrame>`: no declaran nada. */
  rutasConDatoSinMarco: string[];
  /** Todo `<StateFrame>` de una ruta al que le falta alguna entrada. */
  marcos: MarcoDeEstado[];
  /**
   * [T-5.21] Marcos cuyo `staleSinceMs` depende de que la CONSULTA FALLE, no de
   * que el dato sea viejo. Es la mentira que el cableado no ve: `staleSinceMs`
   * está puesto —así que C-1 pasa— y sin embargo un dato de hace diez minutos
   * con red sana se pinta como fresco, porque nada ha fallado.
   */
  frescuraPorError: FrescuraPorError[];
  /**
   * [T-5.21] …y lo mismo UN SALTO MÁS ARRIBA: un hook que DEVUELVE la frescura
   * calculada con una señal de fallo. Es donde estaba el defecto de verdad —
   * `useAlertState.stale = isError && data !== undefined`— y siete pantallas lo
   * heredaban sin mencionar ningún error en su propio marcado. Sin esta regla,
   * el censo del marco pasaba en verde sobre las siete.
   */
  frescuraProducidaPorError: FrescuraPorError[];
  /** Llamadas al SDK en una ruta que pueden rechazar sin que nadie lo recoja. */
  sinDesenlace: PromesaSinDesenlace[];
}

/* =====================================================================
   RECORRIDO DEL ÁRBOL
   ===================================================================== */

export function recorrer(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) {
      recorrer(path, out);
    } else {
      out.push(path);
    }
  }
  return out;
}

/** Código de PRODUCCIÓN: sin tests, sin `.d.ts`, sin utilería de test. */
export function fuentesDeProduccion(src: string): FuenteEntrada[] {
  return recorrer(src)
    .filter(
      (f) =>
        (f.endsWith(".ts") || f.endsWith(".tsx")) &&
        !f.includes(".test.") &&
        !f.endsWith(".d.ts") &&
        !f.includes(`${join(src, "test-utils")}`),
    )
    .map((path) => ({ path, text: readFileSync(path, "utf8") }));
}

/** Todos los ficheros de test del paquete (viven en `src/` y en `tests/`). */
export function ficherosDeTest(raices: string[]): FuenteEntrada[] {
  return raices
    .filter((r) => existsSync(r))
    .flatMap((r) => recorrer(r))
    .filter((f) => f.includes(".test.") && (f.endsWith(".ts") || f.endsWith(".tsx")))
    .map((path) => ({ path, text: readFileSync(path, "utf8") }));
}

/* =====================================================================
   MÓDULOS
   ===================================================================== */

interface Modulo {
  file: string;
  sf: ts.SourceFile;
  imports: Map<string, { target: string; name: string }>;
  reexports: Map<string, { target: string; name: string }>;
  fns: Map<string, ts.Node>;
}

/** Resuelve relativos Y el alias `@/*` → `src/*` de `tsconfig.json`. */
export function resolverModulo(
  desde: string,
  spec: string,
  src: string,
  conocidos: Set<string>,
): string {
  let base: string;
  if (spec.startsWith("@/")) {
    base = join(src, spec.slice(2));
  } else if (spec.startsWith(".")) {
    base = resolve(desde, "..", spec);
  } else {
    return spec;
  }
  for (const cand of [`${base}.ts`, `${base}.tsx`, join(base, "index.ts"), join(base, "index.tsx")]) {
    if (conocidos.has(cand) || existsSync(cand)) {
      return cand;
    }
  }
  return base;
}

function parsear(fuentes: FuenteEntrada[], src: string): Map<string, Modulo> {
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
        const target = resolverModulo(m.file, st.moduleSpecifier.text, src, conocidos);
        const clause = st.importClause;
        if (clause.name) {
          m.imports.set(clause.name.text, { target, name: "default" });
        }
        if (clause.namedBindings && ts.isNamedImports(clause.namedBindings)) {
          for (const el of clause.namedBindings.elements) {
            if (el.isTypeOnly) {
              continue;
            }
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
        const target = resolverModulo(m.file, st.moduleSpecifier.text, src, conocidos);
        for (const el of st.exportClause.elements) {
          if (el.isTypeOnly) {
            continue;
          }
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
  if (depth > 8) {
    return { target, name };
  }
  const re = mods.get(target)?.reexports.get(name);
  return re ? origen(mods, re.target, re.name, depth + 1) : { target, name };
}

function recolectarFunciones(m: Modulo): void {
  const visit = (n: ts.Node): void => {
    if (ts.isFunctionDeclaration(n) && n.name) {
      m.fns.set(n.name.text, n);
    } else if (
      ts.isVariableDeclaration(n) &&
      ts.isIdentifier(n.name) &&
      n.initializer &&
      (ts.isArrowFunction(n.initializer) || ts.isFunctionExpression(n.initializer))
    ) {
      m.fns.set(n.name.text, n.initializer);
    }
    ts.forEachChild(n, visit);
  };
  ts.forEachChild(m.sf, visit);
}

function llamadas(n: ts.Node): Set<string> {
  const out = new Set<string>();
  const visit = (x: ts.Node): void => {
    if (ts.isCallExpression(x) && ts.isIdentifier(x.expression)) {
      out.add(x.expression.text);
    }
    ts.forEachChild(x, visit);
  };
  ts.forEachChild(n, visit);
  return out;
}

function contieneJsx(fn: ts.Node): boolean {
  let hay = false;
  const visit = (n: ts.Node): void => {
    if (ts.isJsxElement(n) || ts.isJsxSelfClosingElement(n) || ts.isJsxFragment(n)) {
      hay = true;
    }
    if (!hay) {
      ts.forEachChild(n, visit);
    }
  };
  ts.forEachChild(fn, visit);
  return hay;
}

/* =====================================================================
   EL CENSO
   ===================================================================== */

export function censar(fuentes: FuenteEntrada[], src: string): Censo {
  const mods = parsear(fuentes, src);
  const enApp = (f: string) => f.startsWith(join(src, "app") + "/") && f.endsWith(".tsx");

  const esTransporte = (m: Modulo, local: string): boolean => {
    const imp = m.imports.get(local);
    if (!imp) {
      return false;
    }
    return imp.target === PAQUETE_QUERY && HOOKS_DE_LECTURA.includes(imp.name);
  };

  // --- cierre de productores (punto fijo sobre el grafo de imports) ---
  const productores = new Set<string>();
  for (let ronda = 0, cambio = true; cambio && ronda < 50; ronda += 1) {
    cambio = false;
    for (const m of mods.values()) {
      for (const [name, fn] of m.fns) {
        const key = `${m.file}::${name}`;
        if (productores.has(key)) {
          continue;
        }
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

  const productorasVisibles = (m: Modulo): Set<string> => {
    const s = new Set<string>();
    for (const [local, imp] of m.imports) {
      if (esTransporte(m, local)) {
        s.add(local);
        continue;
      }
      if (mods.has(imp.target)) {
        const o = origen(mods, imp.target, imp.name);
        if (productores.has(`${o.target}::${o.name}`)) {
          s.add(local);
        }
      }
    }
    for (const name of m.fns.keys()) {
      if (productores.has(`${m.file}::${name}`)) {
        s.add(name);
      }
    }
    return s;
  };

  const rutas: string[] = [];
  const rutasConDato: string[] = [];
  const rutasConDatoSinMarco: string[] = [];
  const marcos: MarcoDeEstado[] = [];
  const frescuraPorError: FrescuraPorError[] = [];
  const frescuraProducidaPorError: FrescuraPorError[] = [];
  const sinDesenlace: PromesaSinDesenlace[] = [];

  // [T-5.21] Quién PRODUCE una frescura decidida por un fallo. Bucle PROPIO y
  // sobre TODOS los módulos: el de abajo salta lo que no está en `src/app`, y
  // el defecto de verdad vivía en `features/alert/useAlertState.ts`. La primera
  // versión de esta regla iba dentro de aquel bucle y no encontraba nada — ni en
  // el código real ni en la fuente sintética de su propia guarda.
  for (const m of mods.values()) {
    const rel = relative(src, m.file);
    const linea = (n: ts.Node) => m.sf.getLineAndCharacterOfPosition(n.getStart(m.sf)).line + 1;
    const inspeccionarProduccion = (n: ts.Node): void => {
      // TRES formas, y las tres aparecieron en el código real: la propiedad de
      // un objeto devuelto por un hook (`return { stale: … }`), la propiedad de
      // un objeto cualquiera, y una CONSTANTE LOCAL con nombre de frescura
      // (`const snapshotStaleSinceMs = stale && data ? …`). La tercera se
      // escapaba de las dos reglas anteriores: `camera.tsx` pasaba el nombre de
      // la constante al marco, y la señal de fallo quedaba un salto más atrás.
      const declarado =
        ts.isPropertyAssignment(n) && (CAMPOS_DE_FRESCURA as readonly string[]).includes(n.name.getText(m.sf));
      const localDeFrescura =
        ts.isVariableDeclaration(n) &&
        ts.isIdentifier(n.name) &&
        /stale/i.test(n.name.text) &&
        n.initializer !== undefined;
      if (ts.isPropertyAssignment(n) || localDeFrescura) {
        const nombre = ts.isPropertyAssignment(n) ? n.name.getText(m.sf) : (n as ts.VariableDeclaration).name.getText(m.sf);
        if (declarado || localDeFrescura) {
          const ids: string[] = [];
          const recoger = (x: ts.Node): void => {
            if (ts.isIdentifier(x)) {
              ids.push(x.text);
            }
            ts.forEachChild(x, recoger);
          };
          recoger((n as ts.PropertyAssignment | ts.VariableDeclaration).initializer!);
          const senales = [...new Set(ids)]
            .filter((id) => (SENALES_DE_FALLO as readonly string[]).includes(id))
            .sort();
          if (senales.length > 0) {
            frescuraProducidaPorError.push({
              clave: `${rel}::${nombre}`,
              fichero: rel,
              linea: linea(n),
              senales,
              expresion: (n as ts.PropertyAssignment | ts.VariableDeclaration).initializer!.getText(m.sf),
            });
          }
        }
      }
      ts.forEachChild(n, inspeccionarProduccion);
    };
    inspeccionarProduccion(m.sf);

    // …y la EXPRESIÓN de `staleSinceMs` en cualquier `<StateFrame>`, también
    // fuera de `src/app`: `features/account/AccountScreen.tsx` renderiza uno y
    // no es una ruta, así que la primera versión de esta regla —dentro del
    // bucle de rutas— no lo miraba nunca. El cableado (C-1) sigue siendo cosa
    // de rutas; la expresión no tiene por qué serlo.
    let ordinalMarco = 0;
    const inspeccionarExpresion = (n: ts.Node): void => {
      if (ts.isJsxElement(n) || ts.isJsxSelfClosingElement(n)) {
        const abre = ts.isJsxElement(n) ? n.openingElement : n;
        if (abre.tagName.getText(m.sf) === "StateFrame") {
          const attrStale = abre.attributes.properties
            .filter(ts.isJsxAttribute)
            .find((a) => a.name.getText(m.sf) === "staleSinceMs");
          if (attrStale?.initializer !== undefined) {
            const ids: string[] = [];
            const recoger = (x: ts.Node): void => {
              if (ts.isIdentifier(x)) {
                ids.push(x.text);
              }
              ts.forEachChild(x, recoger);
            };
            recoger(attrStale.initializer);
            const senales = [...new Set(ids)]
              .filter((id) => (SENALES_DE_FALLO as readonly string[]).includes(id))
              .sort();
            if (senales.length > 0) {
              frescuraPorError.push({
                clave: `${rel}#${ordinalMarco}`,
                fichero: rel,
                linea: linea(abre),
                senales,
                expresion: attrStale.initializer.getText(m.sf),
              });
            }
          }
          ordinalMarco += 1;
        }
      }
      ts.forEachChild(n, inspeccionarExpresion);
    };
    inspeccionarExpresion(m.sf);
  }

  for (const m of mods.values()) {
    if (!enApp(m.file)) {
      continue;
    }
    const rel = relative(src, m.file);
    const linea = (n: ts.Node) => m.sf.getLineAndCharacterOfPosition(n.getStart(m.sf)).line + 1;
    rutas.push(rel);

    // --- ¿posee dato de servidor? ---
    const productoras = productorasVisibles(m);
    let poseeDato = false;
    for (const [name, fn] of m.fns) {
      if (!/^[A-Z]/.test(name) || !contieneJsx(fn)) {
        continue;
      }
      if ([...llamadas(fn)].some((c) => productoras.has(c))) {
        poseeDato = true;
      }
    }
    // El `export default function Ruta()` es una declaración con nombre, así
    // que ya está en `fns`; pero un `export default () => …` no lo estaría.
    for (const st of m.sf.statements) {
      if (
        ts.isExportAssignment(st) &&
        (ts.isArrowFunction(st.expression) || ts.isFunctionExpression(st.expression)) &&
        [...llamadas(st.expression)].some((c) => productoras.has(c))
      ) {
        poseeDato = true;
      }
    }
    if (poseeDato) {
      rutasConDato.push(rel);
    }

    // --- todo `<StateFrame>` y qué entradas se calla ---
    let ordinal = 0;
    const inspeccionarMarcado = (n: ts.Node): void => {
      if (ts.isJsxElement(n) || ts.isJsxSelfClosingElement(n)) {
        const abre = ts.isJsxElement(n) ? n.openingElement : n;
        if (abre.tagName.getText(m.sf) === "StateFrame") {
          const nombres = abre.attributes.properties
            .filter(ts.isJsxAttribute)
            .map((a) => a.name.getText(m.sf));
          const faltan = CUATRO_ENTRADAS.filter((x) => !nombres.includes(x));
          if (faltan.length > 0) {
            marcos.push({
              clave: `${rel}#${ordinal}`,
              fichero: rel,
              linea: linea(abre),
              faltan: [...faltan],
            });
          }
          ordinal += 1;
        }
      }
      ts.forEachChild(n, inspeccionarMarcado);
    };
    ts.forEachChild(m.sf, inspeccionarMarcado);
    if (poseeDato && ordinal === 0) {
      rutasConDatoSinMarco.push(rel);
    }

    // --- promesas del SDK sin desenlace ---
    const sdkLocales = new Set(
      [...m.imports.entries()]
        .filter(([, imp]) => imp.target === PAQUETE_SDK)
        .map(([local]) => local),
    );
    if (sdkLocales.size > 0) {
      const visitar = (n: ts.Node): void => {
        if (
          ts.isCallExpression(n) &&
          ts.isIdentifier(n.expression) &&
          sdkLocales.has(n.expression.text) &&
          esPromesa(n)
        ) {
          if (!protegida(n, productoras)) {
            sinDesenlace.push({
              clave: `${rel}::${n.expression.text}`,
              fichero: rel,
              linea: linea(n),
              operacion: n.expression.text,
            });
          }
        }
        ts.forEachChild(n, visitar);
      };
      ts.forEachChild(m.sf, visitar);
    }
  }

  return {
    productores: [...productores].map((p) => {
      const i = p.lastIndexOf("::");
      return `${relative(src, p.slice(0, i))}::${p.slice(i + 2)}`;
    }),
    rutas: rutas.sort(),
    rutasConDato: rutasConDato.sort(),
    rutasConDatoSinMarco: rutasConDatoSinMarco.sort(),
    marcos: marcos.sort((a, b) => a.clave.localeCompare(b.clave)),
    frescuraPorError: frescuraPorError.sort((a, b) => a.clave.localeCompare(b.clave)),
    frescuraProducidaPorError: frescuraProducidaPorError.sort((a, b) =>
      a.clave.localeCompare(b.clave),
    ),
    sinDesenlace: sinDesenlace.sort((a, b) => a.clave.localeCompare(b.clave)),
  };
}

/**
 * ¿El resultado de esta llamada se USA como promesa? El SDK generado exporta
 * también ayudantes puros (`featuresTopic`, `groupActions`): sin esta puerta, el
 * censo los denunciaría por no capturar un rechazo que no existe. La señal es
 * sintáctica y no necesita tipos: se espera (`await`), se descarta (`void`) o se
 * encadena (`.then`/`.catch`/`.finally`).
 */
export function esPromesa(n: ts.CallExpression): boolean {
  const p = n.parent;
  if (!p) {
    return false;
  }
  if (ts.isAwaitExpression(p) || ts.isReturnStatement(p)) {
    return true;
  }
  if (ts.isVoidExpression(p)) {
    return true;
  }
  if (ts.isPropertyAccessExpression(p) && ["then", "catch", "finally"].includes(p.name.text)) {
    return true;
  }
  return false;
}

/**
 * ¿Alguien recoge el rechazo de esta llamada? Tres formas legítimas:
 *   · estar dentro del `try` de un `try…catch`;
 *   · encadenar `.catch(` (un `.finally(` NO cuenta: libera el botón pero no
 *     recoge el error — literalmente el caso de `notifyUnreported`);
 *   · estar dentro de una PRODUCTORA (`useQuery`, y por cierre `useCachedQuery`):
 *     react-query POSEE ese rechazo y lo convierte en `isError`, así que ahí el
 *     `queryFn` DEBE lanzar y capturar sería el error contrario. El conjunto de
 *     productoras se deriva, no se lista: un envoltorio nuevo queda exento solo
 *     por llamar a un hook de lectura.
 */
export function protegida(n: ts.Node, productoras: Set<string> = new Set()): boolean {
  let hijo: ts.Node = n;
  let p: ts.Node | undefined = n.parent;
  while (p) {
    if (ts.isTryStatement(p) && p.catchClause && p.tryBlock === hijo) {
      return true;
    }
    if (ts.isCallExpression(p)) {
      if (
        ts.isPropertyAccessExpression(p.expression) &&
        p.expression.name.text === "catch" &&
        p.expression === hijo
      ) {
        return true;
      }
      if (
        ts.isIdentifier(p.expression) &&
        (HOOKS_DE_LECTURA.includes(p.expression.text) || productoras.has(p.expression.text))
      ) {
        return true;
      }
    }
    hijo = p;
    p = p.parent;
  }
  return false;
}

/**
 * Ficheros de producción cubiertos por un test que llama a `expectFourStates`.
 * Derivado de los imports del test (relativos o por alias `@/`), no de una
 * convención de nombres: los tests de rutas viven en `tests/app/` y las rutas
 * en `src/app/`, así que jamás coincidirían por nombre.
 */
export function ficherosConPruebaDeCuatroEstados(
  tests: FuenteEntrada[],
  produccion: FuenteEntrada[],
  src: string,
): Set<string> {
  const conocidos = new Set(produccion.map((f) => f.path));
  const out = new Set<string>();
  for (const { path, text } of tests) {
    if (!/\bexpectFourStates\b/.test(text)) {
      continue;
    }
    const sf = ts.createSourceFile(path, text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
    for (const st of sf.statements) {
      if (!ts.isImportDeclaration(st) || !ts.isStringLiteral(st.moduleSpecifier)) {
        continue;
      }
      if (st.importClause?.isTypeOnly) {
        continue;
      }
      const spec = st.moduleSpecifier.text;
      if (!spec.startsWith(".") && !spec.startsWith("@/")) {
        continue;
      }
      const target = resolverModulo(path, spec, src, conocidos);
      if (conocidos.has(target)) {
        out.add(relative(src, target));
      }
    }
  }
  return out;
}
