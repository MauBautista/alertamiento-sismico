// [T-8.11 · A-062] EL CENSO DE LA RESPUESTA AL TOQUE.
//
// Medido al auditar para la presentación (2026-09): 57 `<Pressable>` fuera de
// los tests y **cero** usos de `pressed`, `android_ripple`, `TouchableOpacity`
// o `TouchableHighlight`. `Pressable` no responde visualmente de serie, así que
// ningún botón de la app daba señal de haber sido tocado: la persona volvía a
// pulsar mientras la primera petición seguía en vuelo.
//
// El arreglo es UN componente, `@/ui/Pulsable`, y este censo es lo que impide
// que el botón 58 nazca mudo: todo control que se pulse tiene que responder.
//
// Cumple un control si:
//   · es un `<Pulsable` (la respuesta la pone el componente, y su prueba
//     —`src/ui/Pulsable.test.tsx`— lo acredita), o
//   · es un control crudo que declara las DOS cosas: `android_ripple` y un
//     `style` que depende de `pressed`.
//
// Y además ningún fichero puede importar un pulsable crudo de `react-native`
// fuera de los declarados: un `const Boton = Pressable` escaparía al barrido
// por etiquetas y volvería a dejar un botón mudo.
//
// LAS EXCEPCIONES SE COMPARAN POR IGUALDAD (misma lección que el censo táctil):
// si alguien arregla una, este test se pone rojo y obliga a borrar su línea.

/// <reference types="node" />
import { relative, resolve } from "node:path";

import { fuentesDeProduccion, type FuenteEntrada } from "@/test-utils/screenStateCensus";

const SRC = resolve(__dirname, "..", "src");

/** Etiquetas crudas que se pulsan y no responden solas. */
const CRUDOS = ["Pressable", "TouchableWithoutFeedback"] as const;

/**
 * Controles crudos que NO llevan la respuesta estándar y por qué. Se comparan
 * por igualdad con `ruta · testID`.
 *
 * El botón de pánico se MANTIENE pulsado 1.5 s y su barra que se llena ES la
 * respuesta al dedo; una opacidad encima la ensuciaría. (El deslizador del panel
 * de control es el otro portador propio, pero no es un `Pressable`: responde por
 * gestos y no entra en este barrido.)
 */
const EXENTOS = ["features/panic/PanicButton.tsx · panic-hold"];

/** Ficheros que pueden importar un pulsable crudo: el envoltorio y los exentos. */
const IMPORTAN_CRUDO = ["ui/Pulsable.tsx", "features/panic/PanicButton.tsx"];

/* =====================================================================
   ANALIZADOR (puro: se le puede dar una fuente inventada)
   ===================================================================== */

/** Tapa los comentarios sin mover un carácter: los comentarios CITAN controles. */
function sinComentarios(texto: string): string {
  return texto
    .replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, " "))
    .replace(/(^|[^:])\/\/[^\n]*/g, (m, antes: string) => antes + " ".repeat(m.length - antes.length));
}

/** Desde tras el nombre de la etiqueta hasta el `>` que la cierra. */
function etiquetaDeApertura(texto: string, desde: number): string {
  let profundidad = 0;
  let comilla: string | null = null;
  for (let i = desde; i < texto.length; i += 1) {
    const c = texto[i];
    if (comilla !== null) {
      if (c === comilla && texto[i - 1] !== "\\") {
        comilla = null;
      }
      continue;
    }
    if (c === '"' || c === "'" || c === "`") {
      comilla = c;
    } else if (c === "{" || c === "(" || c === "[") {
      profundidad += 1;
    } else if (c === "}" || c === ")" || c === "]") {
      profundidad -= 1;
    } else if (c === ">" && profundidad === 0 && texto[i - 1] !== "=") {
      return texto.slice(desde, i);
    }
  }
  return texto.slice(desde);
}

interface Control {
  /** `features/home/HomeView.tsx · home-retry` */
  clave: string;
  donde: string;
  tag: string;
  cumple: boolean;
}

function etiquetas(texto: string, tag: string): { indice: number; props: string }[] {
  const out: { indice: number; props: string }[] = [];
  const marca = `<${tag}`;
  let desde = 0;
  for (;;) {
    const i = texto.indexOf(marca, desde);
    if (i < 0) {
      return out;
    }
    desde = i + 1;
    if (!/[\s/>]/.test(texto[i + marca.length] ?? "")) {
      continue; // `<Pressable` casaría dentro de `<PressableRow`
    }
    out.push({ indice: i, props: etiquetaDeApertura(texto, i + marca.length) });
  }
}

function censar(fuente: FuenteEntrada, src: string): Control[] {
  const ruta = relative(src, fuente.path);
  const texto = sinComentarios(fuente.text);
  const out: Control[] = [];
  for (const tag of [...CRUDOS, "Pulsable"]) {
    for (const { indice, props } of etiquetas(texto, tag)) {
      const testID = /testID=(?:"([^"]+)"|\{`([^`]+)`\})/.exec(props);
      const clave = `${ruta} · ${testID?.[1] ?? testID?.[2] ?? "(sin testID)"}`;
      const cumple =
        tag === "Pulsable" ||
        (/android_ripple=/.test(props) && /style=\{\s*\(\s*\{[^}]*\bpressed\b/.test(props));
      out.push({ clave, donde: `${ruta}:${texto.slice(0, indice).split("\n").length}`, tag, cumple });
    }
  }
  return out;
}

/** ¿Importa un pulsable crudo de `react-native`? (con alias o sin él; los tipos no cuentan) */
function importaCrudo(fuente: FuenteEntrada): boolean {
  const texto = sinComentarios(fuente.text);
  for (const m of texto.matchAll(/import\s+(type\s+)?\{([^}]*)\}\s*from\s*["']react-native["']/g)) {
    if (m[1] !== undefined) {
      continue; // `import type { … }`
    }
    const nombres = m[2]
      .split(",")
      .map((n) => n.trim())
      .filter((n) => n !== "" && !n.startsWith("type "))
      .map((n) => n.split(/\s+as\s+/)[0].trim());
    if (nombres.some((n) => (CRUDOS as readonly string[]).includes(n))) {
      return true;
    }
  }
  return false;
}

const PRODUCCION = fuentesDeProduccion(SRC);
const CONTROLES = PRODUCCION.flatMap((f) => censar(f, SRC));

/* =====================================================================
   C-0 · NO-VACUIDAD
   ===================================================================== */

describe("censo de respuesta al toque · el barrido encuentra la app", () => {
  it("hay fuentes de producción y controles que censar", () => {
    expect(PRODUCCION.length).toBeGreaterThan(40);
    // 57 controles pulsables al abrir la ficha: 56 pasaron a `<Pulsable`, el de
    // pánico se queda con su portador y el envoltorio es el 58.º `<Pressable`.
    // Si la población BAJA, el barrido dejó de ver algo.
    expect(CONTROLES.filter((c) => c.tag === "Pulsable").length).toBeGreaterThanOrEqual(56);
    expect(CONTROLES.length).toBeGreaterThanOrEqual(58);
  });

  it("las pantallas que la auditoría nombró están en la población", () => {
    const donde = CONTROLES.map((c) => c.donde);
    for (const fichero of [
      "features/checkin/CheckinView.tsx",
      "app/(brigadista)/sync.tsx",
      "features/headcount/HeadcountView.tsx",
      "ui/StateFrame.tsx",
    ]) {
      expect(donde.some((d) => d.startsWith(`${fichero}:`))).toBe(true);
    }
  });
});

/* =====================================================================
   C-1 · TODO CONTROL RESPONDE AL TOQUE
   ===================================================================== */

describe("censo de respuesta al toque · ningún control nace mudo", () => {
  it("todo pulsable responde, salvo los portadores propios declarados", () => {
    const mudos = CONTROLES.filter((c) => !c.cumple)
      .map((c) => c.clave)
      .sort();
    const declarados = [...EXENTOS].sort();
    if (mudos.length !== declarados.length || mudos.some((x, i) => x !== declarados[i])) {
      throw new Error(
        "Hay controles que no responden visualmente al toque.\n\n" +
          "Usa `<Pulsable>` de `@/ui/Pulsable` en vez de `<Pressable>`: opacidad y onda al\n" +
          "pulsar, y la escala solo si el sistema no pide reducir el movimiento.\n\n" +
          `SIN RESPUESTA:\n  ${
            CONTROLES.filter((c) => !c.cumple && !EXENTOS.includes(c.clave))
              .map((c) => `${c.donde} (${c.clave})`)
              .join("\n  ") || "(ninguno)"
          }\n\n` +
          `DECLARADOS QUE YA RESPONDEN O NO EXISTEN (borra su línea):\n  ${
            declarados.filter((d) => !mudos.includes(d)).join("\n  ") || "(ninguno)"
          }`,
      );
    }
    expect(mudos).toEqual(declarados);
  });

  it("nadie importa un pulsable crudo de react-native fuera del envoltorio y los exentos", () => {
    const importan = PRODUCCION.filter(importaCrudo)
      .map((f) => relative(SRC, f.path))
      .sort();
    expect(importan).toEqual([...IMPORTAN_CRUDO].sort());
  });

  it("el envoltorio mismo lleva la onda y el estilo que depende de `pressed`", () => {
    const envoltorio = CONTROLES.filter((c) => c.donde.startsWith("ui/Pulsable.tsx:") && c.tag === "Pressable");
    expect(envoltorio).toHaveLength(1);
    expect(envoltorio[0].cumple).toBe(true);
  });
});

/* =====================================================================
   C-2 · LA GUARDA DE LA GUARDA
   ===================================================================== */

describe("censo de respuesta al toque · el analizador caza lo que tiene que cazar", () => {
  const fuente = (text: string): FuenteEntrada => ({
    path: resolve(SRC, "features/inventado/Inventado.tsx"),
    text,
  });

  it("un Pressable sin nada se marca", () => {
    const [c] = censar(fuente('<Pressable onPress={f} style={styles.btn} testID="x">'), SRC);
    expect(c.cumple).toBe(false);
    expect(c.clave).toBe("features/inventado/Inventado.tsx · x");
  });

  it("con onda pero sin estilo pulsado, NO cuela (y al revés tampoco)", () => {
    expect(censar(fuente("<Pressable android_ripple={R} style={styles.btn}>"), SRC)[0].cumple).toBe(false);
    expect(
      censar(fuente("<Pressable style={({ pressed }) => [styles.btn, pressed && s.p]}>"), SRC)[0].cumple,
    ).toBe(false);
  });

  it("con las dos cosas cumple", () => {
    const [c] = censar(
      fuente("<Pressable android_ripple={R} style={({ pressed }) => [styles.btn, pressed && s.p]}>"),
      SRC,
    );
    expect(c.cumple).toBe(true);
  });

  it("un `<Pulsable` cumple por construcción y `<PressableRow` no se confunde", () => {
    expect(censar(fuente("<Pulsable onPress={f} style={styles.btn}>"), SRC)[0].cumple).toBe(true);
    expect(censar(fuente("<PressableRow onPress={f} />"), SRC)).toHaveLength(0);
  });

  it("TouchableWithoutFeedback también es un pulsable mudo", () => {
    expect(censar(fuente("<TouchableWithoutFeedback onPress={f}>"), SRC)[0].cumple).toBe(false);
  });

  it("un comentario que CITA un `<Pressable` no cuenta", () => {
    expect(censar(fuente("// el <Pressable de antes\n/* <Pressable x> */"), SRC)).toHaveLength(0);
  });

  it("importar Pressable de react-native se detecta, con alias o sin él; un tipo no", () => {
    expect(importaCrudo(fuente('import { Pressable, Text } from "react-native";'))).toBe(true);
    expect(importaCrudo(fuente('import {\n  Text,\n  Pressable as P,\n} from "react-native";'))).toBe(true);
    expect(importaCrudo(fuente('import { type PressableProps } from "react-native";'))).toBe(false);
    expect(importaCrudo(fuente('import { Text } from "react-native";'))).toBe(false);
  });
});
