/**
 * [T-2.133] EL CENSO DE PRODUCTORES DE `incident_actions.kind`, LEÍDO DE `api/src`.
 *
 * `T-2.119` cerró la mitad fácil del problema: todo `kind` que el ingest ESCRIBE
 * tiene que tener vista y rótulo, y el censo se lee de `ACK_KIND`
 * (`bmsChannels.test.ts::ackKindDelIngest`) en vez de escribirse a mano. Faltaba
 * la mitad simétrica, que es la que esta ficha mide: **todo `kind` que el
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
 * LÍMITE DECLARADO, para que nadie le pida a esto lo que no puede dar: el barrido
 * va del REGISTRO al productor, nunca al revés. Enumerar todos los kinds que
 * `api/` escribe es imposible con un barrido honesto —`headcount_closed` y
 * `headcount_notify` los fija `routers/mobile_incident.py` sobre una sentencia
 * declarada en `queries/mobile.py`, y `incident/lifecycle.py` los saca de un
 * `dict` de estados— así que un censo inverso automático daría una lista
 * incompleta con aspecto de completa. La dirección inversa se cubre donde SÍ es
 * derivable: `verbosDeNotificacion()`, abajo.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";

const API_SRC = resolve(process.cwd(), "..", "api", "src", "takab_api");

/** Marca que identifica a un fichero que ESCRIBE en la tabla. */
const INSERT = "INSERT INTO incident_actions";

function ficherosPy(dir: string, acc: string[] = []): string[] {
  for (const entrada of readdirSync(dir)) {
    const ruta = join(dir, entrada);
    if (statSync(ruta).isDirectory()) {
      ficherosPy(ruta, acc);
    } else if (entrada.endsWith(".py")) {
      acc.push(ruta);
    }
  }
  return acc;
}

/** Ficheros de `api/src` con al menos un `INSERT INTO incident_actions`. */
export function ficherosQueEscribenAcciones(): string[] {
  return ficherosPy(API_SRC).filter((f) => readFileSync(f, "utf8").includes(INSERT));
}

/**
 * ¿Quién escribe este `kind`? Devuelve los ficheros donde el nombre aparece como
 * literal de Python, entre los que insertan en la tabla.
 *
 * Se exige el literal ENTRECOMILLADO y completo: `siren_test` aparece decenas de
 * veces en `api/src` como acción de la matriz RBAC (`allowed_actions.siren_test`),
 * y contar esas apariciones habría dado por vivo justo el nombre que esta ficha
 * midió muerto.
 */
export function productoresDelKind(kind: string): string[] {
  const literal = new RegExp(`["']${kind}["']`);
  return ficherosQueEscribenAcciones().filter((f) => literal.test(readFileSync(f, "utf8")));
}

/**
 * Los verbos de notificación que el orquestador declara, leídos de sus propias
 * constantes (`_KIND_SENT = "notify_sent"`, …).
 *
 * Ésta sí es derivable en la dirección inversa —productor ⇒ rótulo— porque el
 * orquestador los declara todos juntos y con nombre. Es la que caza el defecto
 * gemelo de esta ficha: `T-2.109` añadió un CUARTO verbo (`notify_no_recipients`)
 * y ninguna de las dos superficies lo rotula, así que la fila que dice «no había
 * a quién avisar en este inmueble» se pinta cruda y EN VERDE.
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
