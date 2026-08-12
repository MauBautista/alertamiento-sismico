// [T-2.79.d + T-2.82.a] Censo DERIVADO de quién sortea la precedencia de estados.
//
// Este módulo no afirma nada: **deriva**. Las afirmaciones —y la deuda
// declarada— viven en `src/statePrecedenceCensus.test.ts`. Se separa para poder
// probar el propio analizador contra fuentes sintéticas: una guarda que nadie
// ha visto fallar no es una guarda (mismo patrón que `serverDataCensus.ts` y
// `cssContract.test.ts`).
//
// LAS DOS SEÑALES
// ---------------
// 1. PRECEDENCIA LOCAL (T-2.79.d). `STATE_PRECEDENCE` decide qué gana cuando
//    dos estados son ciertos a la vez. Un componente puede sortear esa tabla
//    sin tocarla: le basta con APAGAR su propio `empty` cuando el dato está
//    viejo. Eso hacía `PrivacyConsentBanner` con `empty={sereno && …}` —y
//    `sereno` exige `staleSince === null`—, y el resultado era la franja muda:
//    `DATOS RETENIDOS · hh:mm UTC` y debajo NADA, porque sin dato los hijos
//    tampoco pintan. La tabla ni se enteraba.
//
//    La señal es estructural: el `empty` del marco DEPENDE del valor que ese
//    mismo marco pasa como `staleSince`. Con una precisión que evita el falso
//    positivo obvio: un identificador que ADEMÁS alimenta a `loading` o a
//    `error` es la CONSULTA (`query.dataUpdatedAt`, `query.isPending`), no el
//    veredicto de frescura, y compartir la consulta es normal y sano.
//
// 2. FRESCURA CLAVADA A MANO (T-2.82.a). En la pantalla donde el inspector
//    FIRMA un dictamen, ningún panel podía declarar su dato viejo:
//    `staleSince={null}` a mano en todos. La población NO se enumera: se
//    calcula el cierre de la página siguiendo las etiquetas JSX a través de los
//    imports, así que el panel número cuatro entra solo el día que alguien lo
//    monte. Y se sigue un salto de propiedad: un panel que reciba `staleSince`
//    por prop y al que NADIE se la pase está igual de clavado a `null`, sólo
//    que el `null` está en el valor por defecto.

import { existsSync, readFileSync } from "node:fs";
import { join, relative, resolve } from "node:path";

import ts from "typescript";

import type { FuenteEntrada } from "./serverDataCensus";

export type { FuenteEntrada };

/* =====================================================================
   MÓDULOS — parseo e imports (mínimo necesario, sin tipos)
   ===================================================================== */

interface Modulo {
  file: string;
  sf: ts.SourceFile;
  /** local → módulo+export de cada import de VALOR. */
  imports: Map<string, { target: string; name: string }>;
  reexports: Map<string, { target: string; name: string }>;
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

export function parsear(fuentes: FuenteEntrada[]): Map<string, Modulo> {
  const conocidos = new Set(fuentes.map((f) => f.path));
  const mods = new Map<string, Modulo>();
  for (const { path, text } of fuentes) {
    mods.set(path, {
      file: path,
      sf: ts.createSourceFile(path, text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX),
      imports: new Map(),
      reexports: new Map(),
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
  }
  return mods;
}

/**
 * Identificadores RAÍZ de una expresión: de `fleet.cabinets.length` sale
 * `fleet`. No baja al JSX anidado — dentro de un JSX hijo ya no se está
 * hablando de esta expresión.
 */
export function raices(n: ts.Node): Set<string> {
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
   MARCOS — todo `<StateFrame>` con su etiqueta y sus props
   ===================================================================== */

export interface Marco {
  /** Ruta relativa a la raíz del censo. */
  fichero: string;
  /** La `label` del marco, tal cual. */
  etiqueta: string;
  /** `fichero#ETIQUETA` — clave estable; la línea se mueve, la etiqueta no. */
  clave: string;
  linea: number;
  /** Componente que lo materializa (para resolver props y sitios de montaje). */
  componente: string;
  props: Map<string, ts.Expression | undefined>;
  /** Nombres declarados como variable DENTRO del componente que lo monta. */
  locales: Set<string>;
  /** name → raíces de su inicializador, dentro del componente que lo monta. */
  dependencias: Map<string, Set<string>>;
}

function esComponente(name: string, fn: ts.Node): boolean {
  if (!/^[A-Z]/.test(name)) return false;
  let hay = false;
  const visit = (n: ts.Node): void => {
    if (ts.isJsxElement(n) || ts.isJsxSelfClosingElement(n) || ts.isJsxFragment(n)) hay = true;
    if (!hay) ts.forEachChild(n, visit);
  };
  ts.forEachChild(fn, visit);
  return hay;
}

/** Funciones con nombre del módulo (declaración, const-arrow y `export default`). */
function funciones(m: Modulo): Map<string, ts.Node> {
  const out = new Map<string, ts.Node>();
  const visit = (n: ts.Node): void => {
    if (ts.isFunctionDeclaration(n) && n.name) out.set(n.name.text, n);
    else if (
      ts.isVariableDeclaration(n) &&
      ts.isIdentifier(n.name) &&
      n.initializer &&
      (ts.isArrowFunction(n.initializer) || ts.isFunctionExpression(n.initializer))
    )
      out.set(n.name.text, n.initializer);
    ts.forEachChild(n, visit);
  };
  ts.forEachChild(m.sf, visit);
  return out;
}

export function marcosDe(mods: Map<string, Modulo>, root: string): Marco[] {
  const out: Marco[] = [];
  for (const m of mods.values()) {
    if (!m.file.endsWith(".tsx")) continue;
    const rel = relative(root, m.file);
    const linea = (n: ts.Node) => m.sf.getLineAndCharacterOfPosition(n.getStart(m.sf)).line + 1;

    for (const [nombre, fn] of funciones(m)) {
      if (!esComponente(nombre, fn)) continue;

      const locales = new Set<string>();
      const dependencias = new Map<string, Set<string>>();
      const recoger = (n: ts.Node): void => {
        if (ts.isVariableDeclaration(n) && n.initializer) {
          const deps = raices(n.initializer);
          for (const b of nombresLigados(n.name)) {
            locales.add(b);
            dependencias.set(b, deps);
          }
        }
        ts.forEachChild(n, recoger);
      };
      ts.forEachChild(fn, recoger);

      const visitar = (n: ts.Node): void => {
        if (ts.isJsxElement(n) || ts.isJsxSelfClosingElement(n)) {
          const abre = ts.isJsxElement(n) ? n.openingElement : n;
          if (abre.tagName.getText(m.sf) === "StateFrame") {
            const props = new Map<string, ts.Expression | undefined>();
            for (const a of abre.attributes.properties) {
              if (!ts.isJsxAttribute(a)) continue;
              const init = a.initializer;
              // `label="EVIDENCIA"` es un StringLiteral pelado, NO un
              // JsxExpression: tratándolo igual, todas las claves salían
              // `fichero##0` y el censo se volvía ilegible (medido).
              const expr = init
                ? ts.isJsxExpression(init)
                  ? init.expression
                  : (init as ts.Expression)
                : undefined;
              props.set(a.name.getText(m.sf), expr);
            }
            const etiqueta = props.get("label");
            const label =
              etiqueta !== undefined && ts.isStringLiteral(etiqueta)
                ? etiqueta.text
                : `#${out.filter((f) => f.fichero === rel).length}`;
            // Dos marcos con la MISMA etiqueta en el mismo fichero (las dos
            // ramas del ternario de `QuorumNodes`) colapsarían en una sola
            // clave, y una tabla de razones no podría hablar de los dos. Se
            // numera el repetido, no todos: la clave del primero no se mueve.
            const repetidos = out.filter((f) => f.fichero === rel && f.etiqueta === label).length;
            out.push({
              fichero: rel,
              etiqueta: label,
              clave: repetidos === 0 ? `${rel}#${label}` : `${rel}#${label}~${repetidos + 1}`,
              linea: linea(abre),
              componente: nombre,
              props,
              locales,
              dependencias,
            });
          }
        }
        ts.forEachChild(n, visitar);
      };
      ts.forEachChild(fn, visitar);
    }
  }
  return out.sort((a, b) => a.clave.localeCompare(b.clave));
}

/* =====================================================================
   SEÑAL 1 · PRECEDENCIA LOCAL — `empty` apagado por la frescura
   ===================================================================== */

export interface PrecedenciaLocal {
  clave: string;
  fichero: string;
  linea: number;
  /** Identificadores por los que el `empty` acaba dependiendo del `staleSince`. */
  via: string[];
}

/**
 * ANTEPASADOS: de qué depende `semilla`, transitivamente. Sube por el grafo
 * `name → raíces de su inicializador`.
 */
function antepasados(semilla: Iterable<string>, deps: Map<string, Set<string>>): Set<string> {
  const out = new Set<string>(semilla);
  for (let cambio = true; cambio; ) {
    cambio = false;
    for (const id of [...out]) {
      for (const dep of deps.get(id) ?? []) {
        if (!out.has(dep)) {
          out.add(dep);
          cambio = true;
        }
      }
    }
  }
  return out;
}

/**
 * DESCENDIENTES: qué se calcula A PARTIR DE `semilla`. Baja por el mismo grafo,
 * y la dirección es la mitad del censo: subir desde `staleSince` da la consulta
 * entera —`triage`, `now`, los filtros— y denunciaría a los trece paneles que
 * simplemente comparten su consulta (medido: 13 falsos positivos). Lo que
 * delata la precedencia local es lo contrario: una variable calculada A PARTIR
 * del veredicto de frescura, como el `sereno` del banner de privacidad.
 */
function descendientes(semilla: Iterable<string>, deps: Map<string, Set<string>>): Set<string> {
  const out = new Set<string>(semilla);
  for (let cambio = true; cambio; ) {
    cambio = false;
    for (const [name, refs] of deps) {
      if (out.has(name)) continue;
      if ([...refs].some((r) => out.has(r))) {
        out.add(name);
        cambio = true;
      }
    }
  }
  return out;
}

export function precedenciasLocales(marcos: Marco[]): PrecedenciaLocal[] {
  const out: PrecedenciaLocal[] = [];
  for (const marco of marcos) {
    const stale = marco.props.get("staleSince");
    const empty = marco.props.get("empty");
    if (!stale || !empty) continue;

    // Un identificador que ADEMÁS alimenta `loading`/`error` es la CONSULTA, no
    // el veredicto de frescura: `staleSince={q.dataUpdatedAt}` junto a
    // `loading={q.isPending}` comparte `q` con todo el marco, y eso es sano.
    const delDato = new Set<string>([
      ...raices(marco.props.get("loading") ?? stale),
      ...raices(marco.props.get("error") ?? stale),
    ]);
    const veredicto = [...raices(stale)].filter((x) => !delDato.has(x));
    if (veredicto.length === 0) continue;

    const contagiados = descendientes(veredicto, marco.dependencias);
    const via = [...antepasados(raices(empty), marco.dependencias)]
      .filter((x) => contagiados.has(x))
      .sort();
    if (via.length > 0)
      out.push({ clave: marco.clave, fichero: marco.fichero, linea: marco.linea, via });
  }
  return out;
}

/* =====================================================================
   SEÑAL 2 · LA PÁGINA — cierre por etiquetas JSX y frescura clavada
   ===================================================================== */

/** Etiquetas JSX de un fichero, resueltas al módulo que las define. */
function tagsDe(m: Modulo, mods: Map<string, Modulo>): Set<string> {
  const out = new Set<string>();
  const visit = (n: ts.Node): void => {
    if (ts.isJsxElement(n) || ts.isJsxSelfClosingElement(n)) {
      const abre = ts.isJsxElement(n) ? n.openingElement : n;
      const tag = abre.tagName.getText(m.sf);
      if (/^[A-Z]/.test(tag)) {
        const imp = m.imports.get(tag);
        if (imp) {
          const re = mods.get(imp.target)?.reexports.get(imp.name);
          const target = re ? re.target : imp.target;
          if (mods.has(target)) out.add(target);
        }
      }
    }
    ts.forEachChild(n, visit);
  };
  ts.forEachChild(m.sf, visit);
  return out;
}

/** Cierre de ficheros alcanzables desde `entrada` siguiendo etiquetas JSX. */
export function arbolDeLaPagina(
  mods: Map<string, Modulo>,
  root: string,
  entrada: string,
): string[] {
  const inicio = resolve(root, entrada);
  if (!mods.has(inicio)) return [];
  const vistos = new Set<string>([inicio]);
  const cola = [inicio];
  while (cola.length > 0) {
    const file = cola.shift() as string;
    const m = mods.get(file);
    if (!m) continue;
    for (const dep of tagsDe(m, mods)) {
      if (!vistos.has(dep)) {
        vistos.add(dep);
        cola.push(dep);
      }
    }
  }
  return [...vistos].map((f) => relative(root, f)).sort();
}

export interface FrescuraClavada {
  clave: string;
  fichero: string;
  linea: number;
  /**
   * `ausente` — el marco no declara `staleSince` (afirma «este dato no puede
   * envejecer» callándoselo).
   * `nulo` — `staleSince={null}` literal.
   * `prop-sin-cablear` — lo recibe por propiedad y NADIE se la pasa (o se la
   * pasan `null`): el `null` está en el valor por defecto, y es el mismo clavo.
   */
  motivo: "ausente" | "nulo" | "prop-sin-cablear";
  detalle: string;
}

/**
 * ¿Dónde se monta `<Componente>` dentro del árbol, y con qué valor le llega la
 * propiedad `prop`?
 *
 * La propiedad se busca POR SU NOMBRE, no por el literal `staleSince`: un panel
 * que pinta dos datos distintos recibe dos edades y no puede llamarlas igual a
 * las dos (`QuorumNodes` es el caso — la del incidente en la rama `absent`, la
 * del evento en la otra). Buscando un atributo llamado `staleSince` el censo
 * denunciaba como no cableado a un panel bien cableado, y ese falso positivo
 * empuja a renombrar props para contentar al analizador.
 */
function sitiosDeMontaje(
  mods: Map<string, Modulo>,
  root: string,
  arbol: Set<string>,
  destino: string,
  prop: string,
): { donde: string; cableado: boolean }[] {
  const out: { donde: string; cableado: boolean }[] = [];
  for (const m of mods.values()) {
    if (!arbol.has(relative(root, m.file))) continue;
    const visit = (n: ts.Node): void => {
      if (ts.isJsxElement(n) || ts.isJsxSelfClosingElement(n)) {
        const abre = ts.isJsxElement(n) ? n.openingElement : n;
        const tag = abre.tagName.getText(m.sf);
        const imp = m.imports.get(tag);
        if (imp) {
          const re = mods.get(imp.target)?.reexports.get(imp.name);
          if ((re ? re.target : imp.target) === destino) {
            const attr = abre.attributes.properties
              .filter(ts.isJsxAttribute)
              .find((a) => a.name.getText(m.sf) === prop);
            const expr =
              attr?.initializer && ts.isJsxExpression(attr.initializer)
                ? attr.initializer.expression
                : undefined;
            const cableado = expr !== undefined && expr.kind !== ts.SyntaxKind.NullKeyword;
            out.push({
              donde: `${relative(root, m.file)}:${
                m.sf.getLineAndCharacterOfPosition(abre.getStart(m.sf)).line + 1
              }`,
              cableado,
            });
          }
        }
      }
      ts.forEachChild(n, visit);
    };
    ts.forEachChild(m.sf, visit);
  }
  return out;
}

export function frescuraClavada(
  mods: Map<string, Modulo>,
  root: string,
  marcos: Marco[],
  arbol: string[],
): FrescuraClavada[] {
  const enElArbol = new Set(arbol);
  const out: FrescuraClavada[] = [];

  for (const marco of marcos) {
    if (!enElArbol.has(marco.fichero)) continue;
    const base = { clave: marco.clave, fichero: marco.fichero, linea: marco.linea };

    if (!marco.props.has("staleSince")) {
      out.push({
        ...base,
        motivo: "ausente",
        detalle: "no declara `staleSince`: se calla que su dato puede envejecer",
      });
      continue;
    }
    const expr = marco.props.get("staleSince");
    if (expr === undefined || expr.kind === ts.SyntaxKind.NullKeyword) {
      out.push({ ...base, motivo: "nulo", detalle: "`staleSince={null}` clavado a mano" });
      continue;
    }
    // Un salto de propiedad: si el valor es una prop del componente (no una
    // variable suya), el `null` puede estar en el sitio de montaje o en el
    // valor por defecto — y clava igual.
    if (ts.isIdentifier(expr) && !marco.locales.has(expr.text)) {
      const destino = resolve(root, marco.fichero);
      const sitios = sitiosDeMontaje(mods, root, enElArbol, destino, expr.text);
      const sinCablear = sitios.filter((s) => !s.cableado);
      if (sitios.length > 0 && sinCablear.length > 0) {
        out.push({
          ...base,
          motivo: "prop-sin-cablear",
          detalle:
            `recibe \`${expr.text}\` por propiedad y nadie se la pasa en ` +
            sinCablear.map((s) => s.donde).join(", "),
        });
      }
    }
  }
  return out.sort((a, b) => a.clave.localeCompare(b.clave));
}

/* =====================================================================
   ENTRADA
   ===================================================================== */

export function leer(paths: string[]): FuenteEntrada[] {
  return paths.map((path) => ({ path, text: readFileSync(path, "utf8") }));
}
