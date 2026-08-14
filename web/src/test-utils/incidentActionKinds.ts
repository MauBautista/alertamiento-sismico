/**
 * [T-2.133] EL CENSO DE PRODUCTORES DE `incident_actions.kind`, LEÍDO DE `api/src`.
 *
 * `T-2.119` cerró la mitad fácil del problema: todo `kind` que el ingest ESCRIBE
 * tiene que tener vista y rótulo, y el censo se lee de `ACK_KIND`
 * (`bmsChannels.test.ts::ackKindDelIngest`) en vez de escribirse a mano. Faltaba
 * la mitad simétrica, que es la que esa ficha midió: **todo `kind` que el
 * registro DA DE ALTA tiene que tener quien lo escriba**.
 *
 * Las dos direcciones fallan distinto y por eso hacen falta las dos:
 *
 *   · un productor sin rótulo pinta el `kind` crudo, en verde («GAS_CLOSED»);
 *   · una entrada MUERTA en el registro no se ve en pantalla jamás —nadie la
 *     escribe— pero ensucia el censo del que se derivan los rótulos, y el día
 *     que alguien la mire creerá que existe un camino que no existe.
 *
 * Es una LECTURA en tiempo de test, no un `import`: no añade dependencia de
 * build de la consola sobre `api/` (cf. `consoleImageCensus.test.ts`, que vigila
 * exactamente los imports que salen de `web/`).
 *
 * ---------------------------------------------------------------------------
 * [T-2.144] EL LÍMITE QUE `T-2.133` DECLARÓ, Y POR QUÉ YA NO ES EL MISMO
 * ---------------------------------------------------------------------------
 *
 * `T-2.133` dejó escrito aquí que el censo INVERSO —del productor al registro—
 * «no se puede hacer con un barrido honesto», porque `headcount_*` los fija un
 * router sobre una sentencia declarada en otro módulo y `lifecycle.py` los saca
 * de un `dict`. Un barrido que buscara los nombres LITERALMENTE daba falsos
 * negativos y nadie lo sabría — y así fue: `T-2.144` encontró OCHO productores
 * sin rótulo, no siete, y el octavo (`notify_delivered`) **ni siquiera está en
 * `api/src`**: lo escribe la función PL/pgSQL `app_notify_delivery`
 * (`db/schema.sql`, migración `0040`) desde el webhook del proveedor.
 *
 * La conclusión de `T-2.133` era correcta sobre el barrido que intentaba —buscar
 * el nombre— y equivocada sobre el problema. El nombre no se busca: **se
 * resuelve**. Lo que sí es decidible, y es donde se ancla todo lo de abajo:
 *
 *   1. QUÉ FICHEROS insertan en la tabla — la cadena `INSERT INTO
 *      incident_actions` está o no está, y se barre TODO el repo, no `api/src`
 *      (`ficherosProductoresDelRepo`). Ahí aparece el octavo.
 *   2. QUÉ EXPRESIÓN ocupa la posición de `kind` en cada sentencia — se saca
 *      POSICIONALMENTE de la lista de columnas y de la tupla de valores
 *      (`sentenciasProductoras`), no por parecido de nombres.
 *   3. A QUÉ literales puede resolverse esa expresión — cuatro reglas, todas
 *      derivadas de código declarado (§`resuelveKind`).
 *
 * Y lo que NO es decidible se declara y **se pone en rojo**, nunca se salta: una
 * expresión que ninguna regla sabe resolver deja la sentencia con `kinds: []` y
 * `regla: "SIN RESOLVER"`, y el test la nombra con su fichero. Un censo que
 * calla lo que no entiende es el que produjo esta ficha.
 *
 * LÍMITE RESIDUAL, medido y escrito (lo cierra el diff a `api/` de `T-2.144`):
 * `lifecycle.py` hace `_ACTION_KIND.get(new_state, new_state)`. Un estado nuevo
 * SIN entrada en ese `dict` escribiría su propio nombre como `kind`, y esta
 * resolución —que lee los VALORES del `dict`— no lo vería. Hoy no ocurre: los
 * tres destinos posibles de `transitions.VALID_TRANSITIONS` están los tres en el
 * `dict`, y el test lo comprueba.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, resolve, sep } from "node:path";

const REPO = resolve(process.cwd(), "..");
const API_SRC = join(REPO, "api", "src", "takab_api");

/** Marca que identifica a un fichero que ESCRIBE en la tabla. */
const INSERT = "INSERT INTO incident_actions";

/**
 * Raíces donde vive un productor de PRODUCCIÓN. `db/` entra porque el octavo
 * productor es una función PL/pgSQL y no había forma de verlo desde `api/src`.
 */
const RAICES = ["api/src", "api/migrations", "db"];

/** Extensiones que pueden llevar SQL. `.sh` entra por `db/verify_rls_smoke.sh`. */
const EXTENSIONES = [".py", ".sql", ".sh"];

/** Directorios sin productores que además harían lento el barrido del repo. */
const PODA = new Set([
  ".git",
  ".expo",
  ".local-soc",
  ".pytest_cache",
  ".ruff_cache",
  ".venv",
  "android",
  "build",
  "coverage",
  "dist",
  "graphify-out",
  "ios",
  "node_modules",
  "playwright-report",
  "test-results",
  "venv",
  "__pycache__",
]);

/**
 * Productores REALES que quedan FUERA del corpus, uno a uno y con su razón.
 *
 * Esto no es una lista de conveniencia: el barrido del repo los encuentra igual
 * (`ficherosProductoresDelRepo`) y el test exige que cualquier productor que no
 * esté en el corpus esté declarado AQUÍ. Un noveno productor en un sitio que
 * nadie barrió no puede volver a pasar en silencio.
 */
export const PRODUCTORES_EXENTOS: Record<string, string> = {
  "api/scripts/fake_ingest.py":
    "generador de fixtures LOCAL (siembra un sismo de mentira en la base de " +
    "desarrollo); no se despliega ni corre contra producción, y sus dos kinds " +
    "son los que el propio ingest escribe.",
};

// ---------------------------------------------------------------------------
// Lectura del corpus
// ---------------------------------------------------------------------------

/**
 * Los comentarios `--` de SQL NO cuentan como productor, y no es un detalle:
 * `db/schema.sql` documenta la columna con `-- 'siren_on','siren_test',…`, así
 * que sin esto `siren_test` —el nombre que `T-2.133` midió MUERTO y retiró del
 * registro— volvería a parecer vivo en cuanto `db/` entrara al corpus.
 */
function normaliza(ruta: string, texto: string): string {
  return ruta.endsWith(".py") ? texto : texto.replace(/--[^\n]*/g, "");
}

function ficheros(dir: string, acc: string[] = []): string[] {
  for (const entrada of readdirSync(dir)) {
    if (PODA.has(entrada)) {
      continue;
    }
    const ruta = join(dir, entrada);
    if (statSync(ruta).isDirectory()) {
      ficheros(ruta, acc);
    } else if (EXTENSIONES.some((e) => entrada.endsWith(e))) {
      acc.push(ruta);
    }
  }
  return acc;
}

/** ¿Es un fichero de PRUEBAS? Los tests escriben kinds inventados a propósito. */
function esTest(rel: string): boolean {
  const partes = rel.split("/");
  return partes.includes("tests") || partes.some((p) => p.startsWith("test_"));
}

function rel(ruta: string): string {
  return relative(REPO, ruta).split(sep).join("/");
}

function leer(ruta: string): string {
  return normaliza(ruta, readFileSync(ruta, "utf8"));
}

/** Ficheros del CORPUS (`api/src`, `api/migrations`, `db`) que insertan. */
export function ficherosProductores(): string[] {
  return RAICES.flatMap((r) => ficheros(join(REPO, r)))
    .filter((f) => !esTest(rel(f)) && leer(f).includes(INSERT))
    .map(rel)
    .sort();
}

/**
 * Ficheros de TODO el repo (menos pruebas y poda) que insertan en la tabla.
 *
 * Es el barrido que encuentra al productor que vive donde nadie miró. Se compara
 * con el corpus + `PRODUCTORES_EXENTOS`: la diferencia pone el test en rojo.
 */
export function ficherosProductoresDelRepo(): string[] {
  return ficheros(REPO)
    .map(rel)
    .filter((r) => !esTest(r) && leer(join(REPO, r)).includes(INSERT))
    .sort();
}

/*
 * [T-2.144] `productoresDelKind()` SE RETIRÓ. Buscaba el nombre del kind como
 * literal entrecomillado dentro de los ficheros que insertan, y ésa es
 * exactamente la forma de censo que `T-2.133` declaró incapaz: daba dos falsos
 * negativos —`headcount_closed` y `headcount_notify`, cuyo literal vive en un
 * router que NO inserta— y ningún aviso de que los daba.
 *
 * Lo sustituye `kindsDeProductores()`, que no busca el nombre: resuelve la
 * expresión de la columna. Dejar las dos habría sido peor que tener una mala:
 * dos censos con aire de autoridad y veredictos distintos es el defecto que esta
 * familia de fichas lleva cuatro veces pagando.
 */

/**
 * Los verbos de notificación que el orquestador declara, leídos de sus propias
 * constantes (`_KIND_SENT = "notify_sent"`, …).
 *
 * Ésta sí es derivable en la dirección inversa —productor ⇒ rótulo— porque el
 * orquestador los declara todos juntos y con nombre. Es la que cazó el defecto
 * gemelo de `T-2.133`: `T-2.109` añadió un CUARTO verbo (`notify_no_recipients`)
 * y ninguna de las dos superficies lo rotulaba, así que la fila que dice «no
 * había a quién avisar en este inmueble» se pintaba cruda y EN VERDE.
 */
export function verbosDeNotificacion(): string[] {
  const fuente = readFileSync(join(API_SRC, "notify", "orchestrator.py"), "utf8");
  const verbos = [...fuente.matchAll(/^_KIND_\w+ = "(\w+)"/gm)].map((m) => m[1]);
  if (verbos.length === 0) {
    throw new Error(
      'no se encontró ningún `_KIND_* = "…"` en el orquestador: el contrato se movió',
    );
  }
  return verbos;
}

// ---------------------------------------------------------------------------
// [T-2.144] Del productor al kind: POSICIONAL, no por parecido de nombres
// ---------------------------------------------------------------------------

/** Una sentencia `INSERT INTO incident_actions` y a qué kinds puede escribir. */
export interface SentenciaProductora {
  /** Ruta relativa al repo. */
  fichero: string;
  /** Texto CRUDO que ocupa la posición de la columna `kind`. */
  expresion: string;
  /** Literales a los que esa expresión puede resolverse. Vacío = sin resolver. */
  kinds: string[];
  /** Qué regla lo resolvió (o `SIN RESOLVER`). Es lo que se lee en el fallo. */
  regla: string;
}

/** Recorta el grupo `( … )` que abre en `inicio`, respetando anidamiento y comillas. */
function grupoBalanceado(texto: string, inicio: number): { cuerpo: string; fin: number } | null {
  if (texto[inicio] !== "(") {
    return null;
  }
  let nivel = 0;
  let comilla: string | null = null;
  for (let i = inicio; i < texto.length; i += 1) {
    const ch = texto[i];
    if (comilla !== null) {
      if (ch === comilla) {
        comilla = null;
      }
      continue;
    }
    if (ch === "'" || ch === '"') {
      comilla = ch;
    } else if (ch === "(") {
      nivel += 1;
    } else if (ch === ")") {
      nivel -= 1;
      if (nivel === 0) {
        return { cuerpo: texto.slice(inicio + 1, i), fin: i + 1 };
      }
    }
  }
  return null;
}

/** Trocea por comas de PRIMER nivel (`jsonb_build_object(a, b)` es UN elemento). */
function troceaTopLevel(s: string): string[] {
  const partes: string[] = [];
  let nivel = 0;
  let comilla: string | null = null;
  let actual = "";
  for (const ch of s) {
    if (comilla !== null) {
      actual += ch;
      if (ch === comilla) {
        comilla = null;
      }
      continue;
    }
    if (ch === "'" || ch === '"') {
      comilla = ch;
    } else if (ch === "(" || ch === "[") {
      nivel += 1;
    } else if (ch === ")" || ch === "]") {
      nivel -= 1;
    } else if (ch === "," && nivel === 0) {
      partes.push(actual.trim());
      actual = "";
      continue;
    }
    actual += ch;
  }
  partes.push(actual.trim());
  return partes;
}

/**
 * Limpia el ruido de que el SQL viva DENTRO de un literal de Python: la sentencia
 * se parte en varias cadenas adyacentes (`"… kind, actor) " "VALUES (…)"`) y los
 * `"` sobran para el troceo. Se quitan sólo las comillas DOBLES: las simples son
 * las del SQL y son justamente las que llevan el kind.
 */
function limpiaCadenasPython(s: string): string {
  return s.replace(/"/g, " ");
}

/** Constantes/diccionarios con `KIND` en el nombre → los literales que declaran. */
function kindsDeclaradosEn(texto: string): string[] {
  const kinds = new Set<string>();
  for (const m of texto.matchAll(/^\s*\w*KIND\w*\s*(?::[^=\n]*)?=\s*"([a-z0-9_]+)"/gm)) {
    kinds.add(m[1]);
  }
  for (const m of texto.matchAll(/^\w*KIND\w*\s*(?::[^=\n]*)?=\s*\{([\s\S]*?)^\}/gm)) {
    for (const v of m[1].matchAll(/:\s*"([a-z0-9_]+)"/g)) {
      kinds.add(v[1]);
    }
  }
  return [...kinds];
}

/** Asignaciones PL/pgSQL `v_kind := 'literal'` del propio cuerpo de la función. */
function kindsAsignadosA(texto: string, variable: string): string[] {
  const re = new RegExp(`\\b${variable}\\s*:=\\s*'([a-z0-9_]+)'`, "g");
  return [...texto.matchAll(re)].map((m) => m[1]);
}

/**
 * Enlaces `"kind": "literal"` en las LLAMADAS a una sentencia con nombre.
 *
 * Se busca en el fichero que la define y, si allí no se usa, en TODO `api/src`:
 * `INSERT_HEADCOUNT_ACTION` vive en `queries/mobile.py` —que no la invoca— y
 * quien le fija el `kind` es `routers/mobile_incident.py`, que ni siquiera es un
 * fichero productor. La ventana va DESPUÉS del uso, que es donde está el
 * diccionario de parámetros: buscar `"kind": "…"` suelto en `api/src` traería
 * `command`, `config_update` y `catalog_update`, que son de OTRAS tablas, y
 * exigirles rótulo sería inventar entradas muertas — el mal de `siren_test`.
 */
function kindsEnLlamadasA(constante: string, propio: string, corpus: string[]): string[] {
  const re = new RegExp(`\\b${constante}\\b[\\s\\S]{0,600}?["']kind["']\\s*:\\s*([\\w"']+)`, "g");
  const cosecha = (texto: string): string[] =>
    [...texto.matchAll(re)].flatMap((m) => {
      const valor = m[1];
      const literal = /^["'](\w+)["']$/.exec(valor);
      if (literal !== null) {
        return [literal[1]];
      }
      // `"kind": _KIND_SENT` / `"kind": kind` ⇒ lo declara el propio fichero.
      const declarado = new RegExp(`^\\s*${valor}\\s*=\\s*"([a-z0-9_]+)"`, "m").exec(texto);
      return declarado !== null ? [declarado[1]] : kindsDeclaradosEn(texto);
    });
  const propios = cosecha(propio);
  if (propios.length > 0) {
    return propios;
  }
  return corpus.flatMap((f) => (f.includes(constante) ? cosecha(f) : []));
}

/** A qué literales puede resolverse la expresión que ocupa la posición `kind`. */
function resuelveKind(
  expresion: string,
  texto: string,
  constante: string | null,
  corpus: string[],
): { kinds: string[]; regla: string } {
  const literal = /^'([a-z0-9_]+)'$/.exec(expresion);
  if (literal !== null) {
    return { kinds: [literal[1]], regla: "literal en la propia sentencia" };
  }
  const variable = /^([a-z_][a-z0-9_]*)$/.exec(expresion);
  if (variable !== null) {
    const asignados = kindsAsignadosA(texto, variable[1]);
    if (asignados.length > 0) {
      return { kinds: asignados, regla: `asignaciones \`${variable[1]} := '…'\`` };
    }
  }
  const esEnlace = /^(%\(\w+\)s|%s|:\w+)/.test(expresion);
  if (esEnlace) {
    const porLlamada = constante === null ? [] : kindsEnLlamadasA(constante, texto, corpus);
    if (porLlamada.length > 0) {
      return { kinds: [...new Set(porLlamada)], regla: `enlaces \`"kind"\` de \`${constante}\`` };
    }
    const declarados = kindsDeclaradosEn(texto);
    if (declarados.length > 0) {
      return { kinds: declarados, regla: "constantes/diccionarios `*KIND*` del fichero" };
    }
  }
  return { kinds: [], regla: "SIN RESOLVER" };
}

/** Nombre al que se asigna la sentencia, si lo tiene (`_ACTION_SQL = """…`). */
function constanteDe(previo: string): string | null {
  const m = /(\w+)\s*(?::[^=\n]*)?=\s*(?:text\(\s*)?("""|'''|"|')\s*$/.exec(previo);
  return m === null ? null : m[1];
}

function sentenciasDe(ruta: string, texto: string, corpus: string[]): SentenciaProductora[] {
  const out: SentenciaProductora[] = [];
  for (let i = texto.indexOf(INSERT); i !== -1; i = texto.indexOf(INSERT, i + 1)) {
    const abre = texto.indexOf("(", i + INSERT.length);
    const cols = abre === -1 ? null : grupoBalanceado(texto, abre);
    if (cols === null) {
      out.push({ fichero: rel(ruta), expresion: "", kinds: [], regla: "SIN RESOLVER" });
      continue;
    }
    const columnas = troceaTopLevel(limpiaCadenasPython(cols.cuerpo)).map((c) => c.trim());
    const idx = columnas.indexOf("kind");
    const resto = limpiaCadenasPython(texto.slice(cols.fin, cols.fin + 4000));
    const tuplas: string[][] = [];
    const mv = /\bVALUES\b/i.exec(resto.slice(0, 200));
    if (mv !== undefined && mv !== null) {
      let desde = resto.indexOf("(", mv.index);
      while (desde !== -1) {
        const g = grupoBalanceado(resto, desde);
        if (g === null) {
          break;
        }
        tuplas.push(troceaTopLevel(g.cuerpo));
        const siguiente = resto.slice(g.fin).match(/^\s*,\s*/);
        desde = siguiente === null ? -1 : g.fin + siguiente[0].length;
      }
    } else {
      const ms = /\bSELECT\b/i.exec(resto.slice(0, 200));
      if (ms !== null) {
        const cuerpo = resto.slice(ms.index + 6).split(/\n\s*(?:WHERE|FROM)\b/i)[0];
        tuplas.push(troceaTopLevel(cuerpo));
      }
    }
    for (const valores of tuplas) {
      const expresion = idx >= 0 && idx < valores.length ? valores[idx].trim() : "";
      const previo = texto.slice(Math.max(0, i - 200), i);
      const { kinds, regla } = resuelveKind(expresion, texto, constanteDe(previo), corpus);
      out.push({ fichero: rel(ruta), expresion, kinds, regla });
    }
    if (tuplas.length === 0) {
      out.push({ fichero: rel(ruta), expresion: "", kinds: [], regla: "SIN RESOLVER" });
    }
  }
  return out;
}

/** Todas las sentencias productoras del corpus, con su resolución. */
export function sentenciasProductoras(): SentenciaProductora[] {
  const rutas = ficherosProductores().map((r) => join(REPO, r));
  const propios = rutas.map(leer);
  // Ámbito de las LLAMADAS: todo `api/src`, no sólo los productores. Quien fija
  // el `kind` de `INSERT_HEADCOUNT_ACTION` es un router que no inserta nada.
  const ambito = [...new Set([...rutas, ...ficheros(join(REPO, "api", "src"))])].map(leer);
  return rutas.flatMap((ruta, n) => sentenciasDe(ruta, propios[n], ambito));
}

/** Unión de los kinds que el corpus puede escribir. Derivada, no enumerada. */
export function kindsDeProductores(): string[] {
  return [...new Set(sentenciasProductoras().flatMap((s) => s.kinds))].sort();
}

/**
 * Los destinos posibles de la máquina de estados del incidente, leídos de
 * `transitions.py`. Sostiene el límite residual declarado arriba: si un destino
 * no tiene entrada en `_ACTION_KIND`, `lifecycle.py` escribiría su nombre crudo.
 */
export function destinosDeCicloDeVida(): string[] {
  const fuente = readFileSync(join(API_SRC, "incident", "transitions.py"), "utf8");
  const bloque = fuente
    .split("VALID_TRANSITIONS: dict[str, frozenset[str]] = {")[1]
    ?.split("\n}")[0];
  if (bloque === undefined) {
    throw new Error("VALID_TRANSITIONS no encontrado en transitions.py: el contrato se movió");
  }
  const destinos = new Set<string>();
  for (const m of bloque.matchAll(/frozenset\(\{([^}]*)\}\)/g)) {
    for (const v of m[1].matchAll(/"(\w+)"/g)) {
      destinos.add(v[1]);
    }
  }
  return [...destinos].sort();
}

/** El `dict` `_ACTION_KIND` de `lifecycle.py`: estado destino → kind escrito. */
export function kindsDeCicloDeVida(): Record<string, string> {
  const fuente = readFileSync(join(API_SRC, "incident", "lifecycle.py"), "utf8");
  const bloque = fuente.split("_ACTION_KIND: dict[str, str] = {")[1]?.split("\n}")[0];
  if (bloque === undefined) {
    throw new Error("_ACTION_KIND no encontrado en lifecycle.py: el contrato se movió");
  }
  return Object.fromEntries(
    [...bloque.matchAll(/"(\w+)"\s*:\s*"(\w+)"/g)].map((m) => [m[1], m[2]]),
  );
}
