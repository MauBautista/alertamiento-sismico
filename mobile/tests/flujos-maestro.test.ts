/**
 * Los flujos de Maestro TIENEN QUE CARGAR.
 *
 * POR QUÉ ESTE TEST EXISTE
 * ------------------------
 * `03-dictamen-liberacion.yaml` —el flujo del dictamen firmado → reingreso
 * liberado— llevaba desde que se escribió **sin acreditarse nunca**, y la razón
 * no era el teléfono ni el entorno: llevaba `assertVisible` con un `timeout:`
 * dentro, propiedad que ese comando NO tiene. Maestro rechaza el fichero
 * ENTERO —«Unknown Property: timeout»— antes de ejecutar un solo paso, así que
 * el flujo no fallaba una aserción: no cargaba. Medido el 2026-09-12 con
 * Maestro 2.6.1, con el Pixel conectado y el estado sembrado a propósito.
 *
 * La espera se escribe con `extendedWaitUntil`, que es lo que hacen los otros
 * siete flujos. Este barrido existe para que el octavo no vuelva a nacer roto:
 * un flujo E2E que no carga se lee como «todavía no lo hemos corrido», y eso
 * puede durar meses.
 */
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

const RAIZ = join(__dirname, "..", ".maestro");

/** Comandos que NO admiten `timeout:` (la espera va en `extendedWaitUntil`). */
const SIN_TIMEOUT = ["assertVisible", "assertNotVisible", "assertTrue"];

function flujos(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
    e.isDirectory()
      ? flujos(join(dir, e.name))
      : e.name.endsWith(".yaml")
        ? [join(dir, e.name)]
        : [],
  );
}

/** Los `timeout:` puestos DENTRO de un comando que no los acepta. El bloque de
 *  un comando son las líneas con MÁS sangría que su guion: al volver a su
 *  sangría (o a menos) empieza el comando siguiente. */
function timeoutsMalPuestos(texto: string): string[] {
  const lineas = texto.split("\n");
  const malos: string[] = [];
  lineas.forEach((linea, i) => {
    const m = /^(\s*)-\s+(\w+):\s*$/.exec(linea);
    if (!m || !SIN_TIMEOUT.includes(m[2])) {
      return;
    }
    const sangria = m[1].length;
    for (let j = i + 1; j < lineas.length; j++) {
      const propia = /^(\s*)\S/.exec(lineas[j]);
      if (!propia) {
        break; // línea en blanco: fin del bloque (como antes)
      }
      if (propia[1].length <= sangria) {
        break;
      }
      if (/^\s+timeout:/.test(lineas[j])) {
        malos.push(`${m[2]} en la línea ${j + 1}`);
      }
    }
  });
  return malos;
}

describe("flujos de Maestro", () => {
  const ficheros = flujos(RAIZ);

  it("hay flujos que barrer (si no, este test no afirma nada)", () => {
    expect(ficheros.length).toBeGreaterThan(5);
  });

  it("el analizador caza el `timeout:` del comando y no el del comando SIGUIENTE", () => {
    // El caso real de `03` (T-7.63): la propiedad dentro del bloque.
    expect(timeoutsMalPuestos('- assertVisible:\n    text: "x"\n    timeout: 5000\n')).toEqual([
      "assertVisible en la línea 3",
    ]);
    // [T-8.11] Anidado en `commands:`: el bloque termina donde vuelve la
    // sangría del comando. Antes se leía «toda línea indentada que sigue» y el
    // `timeout:` del `extendedWaitUntil` hermano se le atribuía a él.
    const anidado = [
      "- runFlow:",
      "    commands:",
      "      - assertNotVisible:",
      '          id: "state-error"',
      "      - extendedWaitUntil:",
      "          visible: x",
      "          timeout: 5000",
      "",
    ].join("\n");
    expect(timeoutsMalPuestos(anidado)).toEqual([]);
  });

  it.each(ficheros.map((f) => [f.slice(RAIZ.length + 1), f]))(
    "%s no pone `timeout:` donde Maestro no lo acepta",
    (_nombre, ruta) => {
      const malos = timeoutsMalPuestos(readFileSync(ruta, "utf8"));
      expect(
        malos.join("; ") +
          (malos.length
            ? " — Maestro rechaza el fichero ENTERO y el flujo no llega a correr; usa extendedWaitUntil"
            : ""),
      ).toBe("");
    },
  );
});

/**
 * CENSO · lo que una cabecera AFIRMA tiene que ser cierto.
 *
 * POR QUÉ ESTE SEGUNDO BARRIDO EXISTE (T-7.63)
 * --------------------------------------------
 * `03-dictamen-liberacion.yaml` decía en su cabecera que un inspector tenía que
 * firmar un dictamen EN LA CONSOLA WEB durante el flujo. No era cierto desde que
 * existe el arnés: `reentry.sql` inserta el dictamen **ya firmado**. Se planificó
 * una tanda de diez contando con diez firmas a mano; ninguna hacía falta. Y `02`
 * decía «incidente ACTIVO» cuando lo que necesita es la sacudida CONCLUIDA — con
 * la fase en `crisis` el brigadista ve la instrucción a pantalla completa y el
 * flujo muere en un `tapOn` que no tiene nada que ver con lo que mide.
 *
 * Un comentario falso en un documento ejecutable no rompe el flujo: rompe la
 * planificación de quien lo lee, y no hay corrida en rojo que lo delate. De ahí
 * que lo cace un test y no una relectura: una relectura caduca el día que se
 * hace.
 *
 * Lo que se puede DERIVAR se deriva; lo que no, se exige declarado:
 *   · si el TOTP hace falta lo dice el YAML —`login-tactico.yaml` teclea en
 *     `totpCodeInput` y `login-occupant.yaml` no—, así que la cabecera no puede
 *     decir lo contrario ni callarse;
 *   · las fases que nombra una cabecera tienen que existir en el arnés, que es
 *     quien las implementa (`seed_staging_incident.sh`).
 */

/** Las líneas de comentario de la cabecera: todo lo anterior a `appId:`. */
function cabecera(ruta: string): string {
  const lineas = readFileSync(ruta, "utf8").split("\n");
  const fin = lineas.findIndex((l) => /^appId:/.test(l));
  return lineas.slice(0, fin === -1 ? 0 : fin).join("\n");
}

/** El cuerpo ejecutable, SIN comentarios — o el censo se cuenta a sí mismo. */
function cuerpoSinComentarios(ruta: string): string {
  return readFileSync(ruta, "utf8")
    .split("\n")
    .map((l) => l.replace(/#.*$/, ""))
    .join("\n");
}

/** Cierre transitivo de `runFlow: <fichero>` (la forma en bloque es inline). */
function cierre(ruta: string): string[] {
  const vistos = new Set<string>();
  const pila = [ruta];
  while (pila.length) {
    const actual = pila.pop()!;
    if (vistos.has(actual)) {
      continue;
    }
    vistos.add(actual);
    for (const m of cuerpoSinComentarios(actual).matchAll(
      /runFlow:\s+(\S+\.yaml)/g,
    )) {
      pila.push(join(actual, "..", m[1]));
    }
  }
  return [...vistos];
}

/** Flujos de primer nivel: los que se invocan, no los subflujos de `shared/`. */
const RAIZ_FLUJOS = readdirSync(RAIZ)
  .filter((n) => n.endsWith(".yaml"))
  .sort();

/** Subcomandos que el arnés acepta de verdad — su propio `case`. */
const ARNES = join(
  __dirname,
  "..",
  "..",
  "infra",
  "scripts",
  "seed_staging_incident.sh",
);
const FASES = new Set(
  [...readFileSync(ARNES, "utf8").matchAll(/^([a-z]+)\)/gm)].map((m) => m[1]),
);

describe("censo · las cabeceras de los flujos dicen la verdad", () => {
  it("hay flujos de primer nivel y fases del arnés que casar", () => {
    expect(RAIZ_FLUJOS.length).toBeGreaterThan(5);
    expect(FASES.size).toBeGreaterThan(3);
  });

  it.each(RAIZ_FLUJOS)("%s declara si pide TOTP, y acierta", (nombre) => {
    const ruta = join(RAIZ, nombre);
    const hijos = cierre(ruta);
    const haceLogin = hijos.some((f) => /login-\w+\.yaml$/.test(f));
    const pideTOTP = hijos.some((f) =>
      /totpCodeInput/.test(cuerpoSinComentarios(f)),
    );
    const texto = cabecera(ruta);

    if (!haceLogin) {
      // Una continuación (`05b`, `05c`) hereda la sesión de la parte anterior:
      // no declara TOTP porque no hace login, pero SÍ de dónde viene, o quien
      // planifica la corrida la lee como un flujo suelto que puede correr solo.
      expect(`${nombre}: sin login propio y sin decir de dónde viene`).toBe(
        /VIENE DE/.test(texto)
          ? `${nombre}: sin login propio y sin decir de dónde viene`
          : "",
      );
      return;
    }

    const dice = /NO PIDE TOTP/.test(texto)
      ? false
      : /PIDE TOTP/.test(texto)
        ? true
        : null;
    expect(
      dice === null
        ? `${nombre}: la cabecera no dice si pide TOTP (pídelo: "PIDE TOTP" / "NO PIDE TOTP"). Lo pide: ${pideTOTP}`
        : dice !== pideTOTP
          ? `${nombre}: la cabecera dice "pide TOTP = ${dice}" y el subflujo de login dice ${pideTOTP}`
          : "",
    ).toBe("");
  });

  // La tabla del README es lo que lee quien PLANIFICA la corrida — la cabecera
  // la lee quien ya la está corriendo, que es demasiado tarde para conseguir a
  // alguien que teclee un TOTP. Así que la columna tiene que casar con el YAML.
  it.each(RAIZ_FLUJOS)("%s casa con la columna TOTP del README", (nombre) => {
    const hijos = cierre(join(RAIZ, nombre));
    if (!hijos.some((f) => /login-\w+\.yaml$/.test(f))) {
      return; // una continuación no hace login: no le toca fila propia
    }
    const pideTOTP = hijos.some((f) =>
      /totpCodeInput/.test(cuerpoSinComentarios(f)),
    );
    const filas = readFileSync(join(RAIZ, "README.md"), "utf8")
      .split("\n")
      .filter((l) => l.trim().startsWith("|"));
    const celdas = (l: string) =>
      l
        .split("|")
        .slice(1, -1)
        .map((c) => c.trim());
    const col = celdas(
      filas.find((l) => celdas(l).includes("TOTP")) ?? "",
    ).indexOf("TOTP");
    if (col === -1) {
      expect("README: la tabla de cobertura no tiene columna TOTP").toBe("");
      return;
    }
    const fila = filas.find((l) => l.includes(nombre));
    if (!fila) {
      expect(`README: ninguna fila de la tabla nombra ${nombre}`).toBe("");
      return;
    }
    const dice = celdas(fila)[col].replace(/\*/g, "");
    expect(
      dice !== (pideTOTP ? "sí" : "no")
        ? `README dice TOTP="${dice}" para ${nombre} y su login dice ${pideTOTP ? "sí" : "no"}`
        : "",
    ).toBe("");
  });

  it.each(RAIZ_FLUJOS)(
    "%s solo nombra fases que el arnés implementa",
    (nombre) => {
      const citadas = [
        ...cabecera(join(RAIZ, nombre)).matchAll(/PHASE=([a-z]+)/g),
      ].map((m) => m[1]);
      const fantasma = citadas.filter((f) => !FASES.has(f));
      expect(
        fantasma.length
          ? `${nombre}: cita PHASE=${fantasma.join(", PHASE=")} y el arnés no las tiene (${[...FASES].sort().join(", ")})`
          : "",
      ).toBe("");
    },
  );
});

/**
 * CENSO · una captura de un RECORRIDO no puede ser la de una pantalla rota.
 *
 * [T-8.11 · verificador] Los recorridos (`recorrido-*.yaml`) pasan por todas las
 * pestañas dejando una captura, pero en PANEL, TRIAGE, LISTA y SYNC no afirmaban
 * nada del contenido: un `waitForAnimationToEnd` y la foto. Una pestaña en
 * «SIN CONEXIÓN CON EL SERVIDOR» salía en VERDE, y la corrida se leía como «todo
 * responde» justo cuando no.
 *
 * Toda `takeScreenshot` de un recorrido va seguida —como SIGUIENTE comando, al
 * mismo nivel— de `assertNotVisible` sobre `state-error`, el `testID` del
 * estado de error de `StateFrame`. La captura va PRIMERO: si la aserción falla,
 * la foto del error ya está en los artefactos.
 */
const RECORRIDOS = RAIZ_FLUJOS.filter((n) => n.startsWith("recorrido-"));

/** Las capturas de un flujo que NO van seguidas de la aserción de error. */
function capturasSinAsercion(texto: string): string[] {
  const lineas = texto.split("\n").map((l) => l.replace(/\s+#.*$/, "").replace(/^\s*#.*$/, ""));
  const malas: string[] = [];
  lineas.forEach((linea, i) => {
    const m = /^(\s*)-\s+takeScreenshot:\s*(\S+)/.exec(linea);
    if (!m) {
      return;
    }
    const sangria = m[1];
    const j = lineas.findIndex((l, k) => k > i && l.trim() !== "");
    const siguiente = j === -1 ? "" : lineas[j];
    const bloque = j === -1 ? "" : lineas.slice(j + 1, j + 3).join("\n");
    const ok =
      siguiente === `${sangria}- assertNotVisible:` &&
      new RegExp(`^${sangria}\\s+id:\\s*"state-error"`, "m").test(bloque);
    if (!ok) {
      malas.push(`${m[2]} (línea ${i + 1})`);
    }
  });
  return malas;
}

describe("censo · los recorridos no fotografían una pantalla en error como si respondiera", () => {
  it("hay recorridos que barrer", () => {
    expect(RECORRIDOS).toEqual(["recorrido-ocupante.yaml", "recorrido-tactico.yaml"]);
  });

  it("el analizador caza una captura sin aserción y acepta la que la lleva", () => {
    const bien = '- takeScreenshot: a\n- assertNotVisible:\n    id: "state-error"\n';
    const mal = "- takeScreenshot: b\n- back\n";
    const anidada = '  - runFlow:\n      commands:\n        - takeScreenshot: c\n        - back\n';
    expect(capturasSinAsercion(bien)).toEqual([]);
    expect(capturasSinAsercion(mal)).toEqual(["b (línea 1)"]);
    expect(capturasSinAsercion(anidada)).toEqual(["c (línea 3)"]);
  });

  it.each(RECORRIDOS)("%s: cada captura va seguida de assertNotVisible state-error", (nombre) => {
    const texto = readFileSync(join(RAIZ, nombre), "utf8");
    expect(texto).toMatch(/takeScreenshot:/);
    expect(capturasSinAsercion(texto)).toEqual([]);
  });
});
