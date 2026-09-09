// [T-6.20] EL CENSO TÁCTIL: nada obligaba a que un control se pudiera pulsar.
//
// Medido en el Pixel 8 Pro durante la auditoría UI/UX (2026-09-06): el botón
// `REINTENTAR` de las pantallas de vida medía ≈29 dp de alto y el enlace «Ver
// directorio completo →», 19. Son el botón que aparece cuando el ocupante NO
// PUDO consultar si tiene que evacuar y el camino a los teléfonos de la
// brigada. `hitSlop` no existía en toda la app y un solo control declaraba
// `minHeight`.
//
// El censo cubre las TRES clases de control que la app pone bajo el dedo
// —`Pressable`, `TextInput` y `Switch`—; las dos últimas entraron al medir en
// el aparato, no al leer el código (ver `CLASES`).
//
// El mínimo es `--tk-touch-min` (48 dp, Android). Dos formas de cumplirlo, y
// las dos tienen que ser DECLARADAS:
//
//   · `minHeight: touch.min` en el estilo del control — lo normal: el área que
//     responde al dedo es la que se ve.
//   · `hitSlop={slopHasta(<alto visible>)}` — para el control que vive dentro
//     de una fila densa (los chips LLAMAR/VERIFICAR de un pase de lista de 200
//     personas), donde crecer el botón empujaría la lista fuera de pantalla.
//     El alto visible se lo pasa su propio estilo, no una estimación a ojo.
//     Solo vale sobre una vista de React: Android IGNORA el `hitSlop` de un
//     control nativo, y por eso un `<Switch>` no puede ser el objetivo (ver
//     `CLASES`).
//
// LA LISTA DE EXCEPCIONES SE COMPARA POR IGUALDAD, nunca por contención: si
// alguien arregla una entrada, este test se pone rojo y le obliga a borrar su
// línea. Una excepción que puede crecer sola no es una excepción, es un
// agujero (misma lección que `screenStateCensus` y `serverDataCensus`).

/// <reference types="node" />
import { resolve, relative } from "node:path";

import { tokens, toNumber } from "@takab/design-tokens";

import { slopHasta, touch } from "@/ui/theme";

import { fuentesDeProduccion, type FuenteEntrada } from "./test-utils/screenStateCensus";

const RAIZ = resolve(process.cwd());
const SRC = resolve(RAIZ, "src");
const MINIMO = toNumber(tokens.touch.min);

/* =====================================================================
   ANALIZADOR (puro: se le puede dar una fuente inventada y preguntarle)
   ===================================================================== */

interface Control {
  /** `features/home/HomeView.tsx:165` — clicable y estable al reordenar. */
  donde: string;
  /** Texto de la etiqueta de apertura, sin el `<Pressable` ni el `>`. */
  props: string;
  cumple: boolean;
  razon: string;
}

/**
 * Recorta desde `desde` hasta el `>` que cierra la etiqueta de apertura,
 * ignorando los que viajan dentro de llaves, comillas o de una flecha `=>`.
 */
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

/** El valor de `prop={…}` con emparejamiento de llaves (o null si no está). */
function valorDeProp(props: string, prop: string): string | null {
  const marca = `${prop}={`;
  const i = props.indexOf(marca);
  if (i < 0) {
    return null;
  }
  let profundidad = 0;
  for (let j = i + marca.length - 1; j < props.length; j += 1) {
    if (props[j] === "{") {
      profundidad += 1;
    } else if (props[j] === "}") {
      profundidad -= 1;
      if (profundidad === 0) {
        return props.slice(i + marca.length, j);
      }
    }
  }
  return props.slice(i + marca.length);
}

/** El cuerpo de `NOMBRE: { … }` dentro del `StyleSheet.create` del fichero. */
function bloqueDeEstilo(texto: string, nombre: string): string | null {
  // El delimitador de la izquierda evita que `sevChip` case dentro de
  // `miSevChip`; se admite `{`/`,` además del salto de línea porque un
  // `StyleSheet.create({ btn: {…} })` de una sola línea es igual de válido.
  const re = new RegExp(`[{,\\s]${nombre}:\\s*\\{`);
  const m = re.exec(texto);
  if (m === null) {
    return null;
  }
  const abre = texto.indexOf("{", m.index + 1);
  let profundidad = 0;
  for (let j = abre; j < texto.length; j += 1) {
    if (texto[j] === "{") {
      profundidad += 1;
    } else if (texto[j] === "}") {
      profundidad -= 1;
      if (profundidad === 0) {
        return texto.slice(abre + 1, j);
      }
    }
  }
  return null;
}

/** ¿Este cuerpo de estilo declara un alto ≥ el mínimo? */
function declaraAltoSuficiente(cuerpo: string): boolean {
  if (/minHeight:\s*touch\.min\b/.test(cuerpo)) {
    return true;
  }
  const m = /minHeight:\s*(\d+)/.exec(cuerpo);
  return m !== null && Number(m[1]) >= MINIMO;
}

/**
 * Las tres clases de control que la app pone bajo el dedo. `Pressable` era la
 * única en el enunciado de la ficha; las otras dos las trajo la medición en el
 * Pixel: el interruptor de GPS del aviso de privacidad medía **27 dp** y el
 * campo del código de sitio, **46.7**.
 *
 * **`Switch` no puede ser el objetivo táctil.** En Android el `hitSlop` solo lo
 * honra una vista de React (`ReactHitSlopView`, que implementa `ReactViewGroup`)
 * y sobre un interruptor NATIVO se ignora **en silencio**: medido en el Pixel,
 * un toque a 8 dp de su borde no lo movió, con la holgura declarada en el
 * código. Así que el interruptor queda de INDICADOR (`pointerEvents="none"`) y
 * el objetivo es su fila, que entra en el censo como el `Pressable` que es.
 */
const CLASES = [
  { tag: "Pressable", soloIndicador: false },
  { tag: "TextInput", soloIndicador: false },
  { tag: "Switch", soloIndicador: true },
] as const;

/**
 * Tapa los comentarios SIN mover un solo carácter (espacios por dentro, saltos
 * de línea intactos), para que los `ruta:línea` sigan siendo ciertos.
 *
 * Hace falta porque los comentarios de este árbol CITAN los controles de los
 * que hablan —`privacidad.tsx` explica en prosa por qué un `<Switch>` no puede
 * recibir el dedo—, y el censo los contaba como controles sin arreglar.
 */
function sinComentarios(texto: string): string {
  return texto
    .replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, " "))
    .replace(/(^|[^:])\/\/[^\n]*/g, (m, antes: string) => antes + " ".repeat(m.length - antes.length));
}

function censarFuente(fuente: FuenteEntrada, src: string): Control[] {
  const out: Control[] = [];
  const ruta = relative(src, fuente.path);
  const texto = sinComentarios(fuente.text);
  for (const { tag, soloIndicador } of CLASES) {
    const marca = `<${tag}`;
    let desde = 0;
    for (;;) {
      const i = texto.indexOf(marca, desde);
      if (i < 0) {
        break;
      }
      desde = i + 1;
      // `<Switch` casaría dentro de `<SwitchRow`: tras el nombre tiene que
      // venir un espacio, un salto de línea o el cierre de la etiqueta.
      if (!/[\s/>]/.test(texto[i + marca.length] ?? "")) {
        continue;
      }
      const linea = texto.slice(0, i).split("\n").length;
      const props = etiquetaDeApertura(texto, i + marca.length);
      const donde = `${ruta}:${linea}`;

      if (soloIndicador) {
        const indicador = /pointerEvents=("none"|{"none"})/.test(props);
        out.push({
          donde,
          props,
          cumple: indicador,
          razon: indicador
            ? "indicador: el objetivo es su fila"
            : `${tag} recibe el dedo (en Android ignora hitSlop): pásalo a pointerEvents="none" y haz Pressable su fila`,
        });
        continue;
      }

      const slop = valorDeProp(props, "hitSlop");
      if (slop !== null) {
        const derivado = /slopHasta\(/.test(slop);
        out.push({
          donde,
          props,
          cumple: derivado,
          razon: derivado ? "hitSlop derivado del token" : "hitSlop escrito a mano (usa slopHasta)",
        });
        continue;
      }

      const estilo = valorDeProp(props, "style");
      if (estilo === null) {
        out.push({ donde, props, cumple: false, razon: "sin estilo y sin hitSlop" });
        continue;
      }
      const nombres = [...estilo.matchAll(/styles\.([A-Za-z0-9_]+)/g)].map((m) => m[1]);
      const cuerpos = nombres
        .map((n) => bloqueDeEstilo(texto, n))
        .filter((c): c is string => c !== null);
      const cumple = [estilo, ...cuerpos].some(declaraAltoSuficiente);
      out.push({
        donde,
        props,
        cumple,
        razon: cumple
          ? "minHeight del token"
          : `sin alto declarado (${nombres.join(", ") || "inline"})`,
      });
    }
  }
  return out;
}

const PRODUCCION = fuentesDeProduccion(SRC);
const CONTROLES = PRODUCCION.flatMap((f) => censarFuente(f, SRC));

/**
 * Controles que NO cumplen y por qué se les perdona. **Vacía**: el día que haga
 * falta una excepción se escribe aquí con su razón, y el test de más abajo
 * vigila que la lista no crezca sola.
 */
const EXENTOS: string[] = [];

/* =====================================================================
   C-0 · NO-VACUIDAD — si el barrido no encuentra nada, el resto miente
   ===================================================================== */

describe("censo táctil · el barrido encuentra la app", () => {
  it("hay fuentes de producción y controles que censar", () => {
    expect(PRODUCCION.length).toBeGreaterThan(40);
    expect(CONTROLES.length).toBeGreaterThanOrEqual(45);
  });

  it("el mínimo sale del paquete de tokens, no de un número escrito aquí", () => {
    expect(tokens.touch.min).toBe("48px");
    expect(MINIMO).toBe(48);
  });
});

/* =====================================================================
   C-1 · TODO CONTROL DECLARA SU ÁREA
   ===================================================================== */

describe("censo táctil · todo control declara un objetivo del tamaño mínimo", () => {
  it("ninguno se queda por debajo sin decirlo", () => {
    const incumplen = CONTROLES.filter((c) => !c.cumple)
      .map((c) => `${c.donde} — ${c.razon}`)
      .sort();
    const declarados = [...EXENTOS].sort();
    if (incumplen.length !== declarados.length || incumplen.some((x, i) => x !== declarados[i])) {
      throw new Error(
        "Hay controles sin objetivo táctil del tamaño mínimo.\n\n" +
          "Arréglalo con UNA de las dos formas declaradas:\n" +
          '  · `minHeight: touch.min` + `justifyContent: "center"` en su estilo, o\n' +
          "  · `hitSlop={slopHasta(<alto visible>)}` si vive en una fila densa.\n\n" +
          `SIN DECLARAR:\n  ${incumplen.join("\n  ") || "(ninguno)"}\n\n` +
          `DECLARADOS QUE YA NO INCUMPLEN (borra su línea):\n  ${
            declarados.filter((d) => !incumplen.includes(d)).join("\n  ") || "(ninguno)"
          }`,
      );
    }
    expect(incumplen).toEqual(declarados);
  });

  it("los controles de las pantallas de vida están en la población", () => {
    // Sin esto, un `SRC` mal resuelto o un cambio de nombre dejaría el censo
    // mirando a otro lado y en verde. Se nombran los que la auditoría midió.
    const donde = CONTROLES.map((c) => c.donde);
    for (const fichero of [
      "ui/StateFrame.tsx",
      "features/home/HomeView.tsx",
      "features/checkin/CheckinView.tsx",
      "features/panic/PanicButton.tsx",
      "features/alarm/TacticalAckButton.tsx",
    ]) {
      expect(donde.some((d) => d.startsWith(`${fichero}:`))).toBe(true);
    }
  });
});

/* =====================================================================
   C-2 · LA GUARDA DE LA GUARDA — falla cuando debe
   ===================================================================== */

describe("censo táctil · el analizador caza lo que tiene que cazar", () => {
  const fuente = (cuerpo: string): FuenteEntrada => ({
    path: resolve(SRC, "features/inventado/Inventado.tsx"),
    text: cuerpo,
  });

  it("un Pressable sin alto ni hitSlop se marca", () => {
    const [c] = censarFuente(
      fuente(
        "<Pressable style={styles.link}><Text>x</Text></Pressable>\n" +
          "const styles = StyleSheet.create({ link: { color: 'x' } });",
      ),
      SRC,
    );
    expect(c.cumple).toBe(false);
  });

  it("un Pressable SIN estilo se marca", () => {
    const [c] = censarFuente(fuente("<Pressable onPress={f}><Text>x</Text></Pressable>"), SRC);
    expect(c.cumple).toBe(false);
    expect(c.razon).toBe("sin estilo y sin hitSlop");
  });

  it("`minHeight: touch.min` en el estilo referenciado cumple", () => {
    const [c] = censarFuente(
      fuente(
        "<Pressable style={[styles.btn, dim && styles.dim]}><Text>x</Text></Pressable>\n" +
          "const styles = StyleSheet.create({ btn: { minHeight: touch.min } });",
      ),
      SRC,
    );
    expect(c.cumple).toBe(true);
  });

  it("`hitSlop={slopHasta(n)}` cumple y un hitSlop a mano NO", () => {
    const [ok] = censarFuente(
      fuente("<Pressable hitSlop={slopHasta(CHIP)} style={styles.chip}><Text>x</Text></Pressable>"),
      SRC,
    );
    expect(ok.cumple).toBe(true);
    const [malo] = censarFuente(
      fuente("<Pressable hitSlop={{ top: 8 }} style={styles.chip}><Text>x</Text></Pressable>"),
      SRC,
    );
    expect(malo.cumple).toBe(false);
  });

  it("un `<Switch>` que recibe el dedo se marca; de indicador, cumple", () => {
    const malo = censarFuente(fuente("<Switch onValueChange={f} value={v} />"), SRC)[0];
    expect(malo.cumple).toBe(false);
    // …y tampoco cuela con holgura: en Android un control nativo la ignora.
    const conHolgura = censarFuente(
      fuente("<Switch hitSlop={slopHasta(27)} onValueChange={f} value={v} />"),
      SRC,
    )[0];
    expect(conHolgura.cumple).toBe(false);
    const bueno = censarFuente(fuente('<Switch pointerEvents="none" value={v} />'), SRC)[0];
    expect(bueno.cumple).toBe(true);
  });

  it("un alto numérico por debajo del mínimo NO cuela", () => {
    const bajo = censarFuente(
      fuente(
        "<Pressable style={styles.btn}><Text>x</Text></Pressable>\n" +
          "const styles = StyleSheet.create({ btn: { minHeight: 44 } });",
      ),
      SRC,
    )[0];
    expect(bajo.cumple).toBe(false);
    const alto = censarFuente(
      fuente(
        "<Pressable style={styles.btn}><Text>x</Text></Pressable>\n" +
          "const styles = StyleSheet.create({ btn: { minHeight: 56 } });",
      ),
      SRC,
    )[0];
    expect(alto.cumple).toBe(true);
  });
});

/* =====================================================================
   C-3 · LA ARITMÉTICA DEL hitSlop
   ===================================================================== */

describe("censo táctil · slopHasta lleva el chip al mínimo", () => {
  it("el tema resuelve el mismo mínimo que el paquete", () => {
    expect(touch.min).toBe(MINIMO);
  });

  it("un chip de 24 dp recibe 12 por lado y llega justo al mínimo", () => {
    const s = slopHasta(24);
    expect(s).toEqual({ top: 12, bottom: 12, left: 12, right: 12 });
    expect(24 + s.top + s.bottom).toBeGreaterThanOrEqual(MINIMO);
  });

  it("un alto impar redondea HACIA ARRIBA (nunca se queda corto)", () => {
    const s = slopHasta(25);
    expect(25 + s.top + s.bottom).toBeGreaterThanOrEqual(MINIMO);
  });

  it("un control que ya cumple no recibe holgura", () => {
    expect(slopHasta(MINIMO)).toEqual({ top: 0, bottom: 0, left: 0, right: 0 });
    expect(slopHasta(96)).toEqual({ top: 0, bottom: 0, left: 0, right: 0 });
  });
});
