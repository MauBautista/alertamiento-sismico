// [T-7.05 · C-3] La función que decide el intervalo, probada SIN red.
//
// El defecto que cierra esta ficha se midió así (censo de T-7.04, §5, F1b): el
// detalle abierto a los 3 s de `opened_at`, el dictamen en la base a los 61 s
// y el rótulo todavía diciendo «SIN DICTAMEN» a los 81 s. Lo que decidía era
// una ausencia —ningún `refetchInterval`—, y una ausencia no se puede probar.
// Por eso la decisión pasa a ser una FUNCIÓN: se le puede preguntar.
//
// QUÉ MIDE ESTE FICHERO Y QUÉ NO. Esto es aritmética pura: entra un estado,
// sale un número o `false`. No toca red, ni react-query, ni DOM. Lo que la
// FUNCIÓN produce cuando se monta en la pantalla lo ejerce
// `TriageDetailRefresh.test.tsx` (jsdom, clientes del SDK mockeados) y lo que
// hace contra el worker de verdad —el cronómetro del «≤10 s» con la pila viva y
// con el canal live caído a propósito— lo ejerce el integrador; la demarcación
// exacta está escrita en la cabecera de aquel fichero.

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import {
  DICTAMEN_REFETCH_MS,
  DICTAMEN_WATCH_MS,
  dictamenRefetchMs,
  type DictamenRefreshInput,
} from "./dictamenRefresh";

const ABIERTO = "2026-09-12T12:46:29.600Z";
const T0 = Date.parse(ABIERTO);

/** Caso base: el del censo — incidente abierto, joven y sin dictamen. */
function entrada(over: Partial<DictamenRefreshInput> = {}): DictamenRefreshInput {
  return {
    incidentId: "484d31d8-0000-4000-8000-000000000000",
    incident: { openedAt: ABIERTO },
    dictamens: [],
    now: T0 + 3_000,
    ...over,
  };
}

/** Preliminar automático: la cabeza que el worker TODAVÍA puede corregir. */
const PRELIMINAR = [{ signed_by: null }];
/** Cadena con firma del inspector: intocable para la pasada automática. */
const FIRMADO = [{ signed_by: "u-1" }, { signed_by: null }];

describe("dictamenRefetchMs · cuándo se sondea", () => {
  it("incidente abierto y sin dictamen: sondea", () => {
    expect(dictamenRefetchMs(entrada())).toBe(DICTAMEN_REFETCH_MS);
  });

  it("la consulta aún en vuelo (`undefined`) cuenta como «sin dictamen»", () => {
    // `undefined` no es «no hay»: es «todavía no se sabe». Tratarlo como
    // silencio dejaría el sondeo apagado justo en el primer render, que es
    // cuando el inspector abre la fila.
    expect(dictamenRefetchMs(entrada({ dictamens: undefined }))).toBe(DICTAMEN_REFETCH_MS);
  });

  it("con el PRELIMINAR ya en la cadena SIGUE sondeando: falta la corrección", () => {
    // Éste es el defecto que encontró la revisión adversaria (f0r2 · nº2).
    // `run_dictamen_pass` sólo se aparta si la cabeza está FIRMADA
    // (`if row["head_signed_by"] is not None: continue`); con una cabeza
    // preliminar y un status recalculado distinto INSERTA una corrección con
    // `supersedes_dictamen_id` — el caso «el quórum corroboró después del
    // preliminar» del propio docstring del worker. Parar con la primera fila
    // dejaba al inspector firmando un veredicto ya superado, y en solo-REST esa
    // corrección no llegaba nunca.
    expect(dictamenRefetchMs(entrada({ dictamens: PRELIMINAR }))).toBe(DICTAMEN_REFETCH_MS);
  });

  it("con la cadena FIRMADA: para", () => {
    // Firmar es la condición de parada del worker, y la de aquí. La cadena sólo
    // vuelve a crecer al firmar otra vez, y eso invalida por su cuenta
    // (`signMutation.onSuccess`).
    expect(dictamenRefetchMs(entrada({ dictamens: FIRMADO }))).toBe(false);
  });

  it("sin incidente seleccionado: para", () => {
    // La consulta está `enabled:false`; un intervalo aquí es un temporizador
    // sobre nada.
    expect(dictamenRefetchMs(entrada({ incidentId: null }))).toBe(false);
  });

  it("fuera de la ventana en la que la pasada automática puede emitir: para", () => {
    const tarde = entrada({ now: T0 + DICTAMEN_WATCH_MS + 1 });
    expect(dictamenRefetchMs(tarde)).toBe(false);
  });

  it("justo en el borde de la ventana todavía sondea", () => {
    expect(dictamenRefetchMs(entrada({ now: T0 + DICTAMEN_WATCH_MS }))).toBe(DICTAMEN_REFETCH_MS);
  });

  it("un reloj adelantado (incidente «del futuro») no apaga el sondeo", () => {
    expect(dictamenRefetchMs(entrada({ now: T0 - 60_000 }))).toBe(DICTAMEN_REFETCH_MS);
  });

  it("sin la fila del incidente NO se sondea: sin ancla no hay hora de parada", () => {
    // Antes esta rama devolvía el intervalo «porque lo desconocido no se presume
    // silencio». El argumento era bueno para lo que se PINTA y malo para lo que
    // se SONDEA: sin `opened_at` no hay ventana que calcular, y lo que quedaba
    // era un temporizador perpetuo sobre dos endpoints esperando a un llamador
    // que lo tomara por omisión.
    expect(dictamenRefetchMs(entrada({ incident: null }))).toBe(false);
  });

  it("con una fecha de apertura ilegible tampoco: es el mismo agujero", () => {
    expect(dictamenRefetchMs(entrada({ incident: { openedAt: "ayer" } }))).toBe(false);
  });
});

describe("dictamenRefetchMs · TODO sondeo caduca", () => {
  // La invariante que sustituye a la promesa escrita en un comentario. Barre las
  // formas de entrada que el hook puede construir y comprueba que, con el reloj
  // suficientemente adelantado, ninguna sigue pidiendo. Una rama nueva que
  // devuelva intervalo sin mirar el reloj —como las dos que había— pone esto
  // rojo sin que nadie tenga que acordarse de escribirle un test.
  const FORMAS: Array<[string, Partial<DictamenRefreshInput>]> = [
    ["caso base", {}],
    ["fila desconocida", { incident: null }],
    ["fecha ilegible", { incident: { openedAt: "ayer" } }],
    ["fecha vacía", { incident: { openedAt: "" } }],
    ["consulta en vuelo", { dictamens: undefined }],
    ["preliminar sin firmar", { dictamens: PRELIMINAR }],
    ["cadena firmada", { dictamens: FIRMADO }],
    ["sin incidente", { incidentId: null }],
  ];

  const UN_ANO_MS = 365 * 24 * 60 * 60 * 1000;

  it.each(FORMAS)("«%s» deja de sondear con el reloj adelantado", (_nombre, over) => {
    expect(dictamenRefetchMs(entrada({ ...over, now: T0 + UN_ANO_MS }))).toBe(false);
  });

  it("el barrido cubre cada rama: alguna de esas formas SÍ sondea en su momento", () => {
    // Contraejemplo obligatorio: si todas las formas devolvieran `false` siempre,
    // el `it.each` de arriba pasaría por vacuidad y no estaría defendiendo nada.
    const vivas = FORMAS.filter(([, over]) => dictamenRefetchMs(entrada(over)) !== false);
    expect(vivas.map(([n]) => n)).toEqual([
      "caso base",
      "consulta en vuelo",
      "preliminar sin firmar",
    ]);
  });
});

describe("dictamenRefetchMs · el intervalo NO es un número suelto", () => {
  it("cabe dentro de los 10 s que exige el criterio C-3", () => {
    // El criterio medible de la ficha: el rótulo cambia «dentro de los 10 s
    // siguientes a la emisión». Un intervalo de 10 s o más no lo cumple ni en
    // el mejor caso, porque al periodo hay que sumarle la petición.
    expect(DICTAMEN_REFETCH_MS).toBeLessThan(10_000);
    expect(DICTAMEN_REFETCH_MS).toBeGreaterThanOrEqual(1_000);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// LA VENTANA, DERIVADA DEL WORKER QUE DE VERDAD CORRE.
//
// La primera versión de esta guarda leía `lookback_s: float = 300.0` de
// `dictamen/service.py` — y ése es un DEFAULT MUERTO: `engine.py` siempre pasa
// el suyo. Con eso, arrancar el motor con `--lookback 900` ensanchaba la ventana
// real y este fichero seguía verde (revisión adversaria f0r2 · nº1). Ahora se
// leen las TRES declaraciones de la cadena Y los arrancadores desplegados, se
// exige que cada lectura acierte —una que deje de casar es la guarda quedándose
// ciega, no una guarda que aprueba— y se compara contra la MAYOR.
//
// Es una LECTURA de fichero, no un import: no añade dependencia de build de la
// consola sobre `api/`. Misma receta que `serverFrameCensus.test.ts` con
// `ws/protocol.py`.
const RAIZ = resolve(process.cwd(), "..");
const lee = (rel: string) => readFileSync(resolve(RAIZ, rel), "utf8");

/** Dónde está declarado el lookback, y por qué cada uno puede gobernar. */
const DECLARACIONES: Array<[string, RegExp, string]> = [
  [
    "api/src/takab_api/incident/__main__.py",
    /add_argument\(\s*"--lookback"[^)]*default=([\d.]+)/,
    "el que GOBIERNA hoy: nadie pasa el flag, así que corre este default",
  ],
  [
    "api/src/takab_api/incident/engine.py",
    /lookback_s:\s*float\s*=\s*([\d.]+)/,
    "el de `IncidentEngine`: gobierna si alguien construye el motor sin el CLI",
  ],
  [
    "api/src/takab_api/dictamen/service.py",
    /lookback_s:\s*float\s*=\s*([\d.]+)/,
    "el de `run_dictamen_pass`: sombreado hoy, gobierna si se quita el paso-a-través",
  ],
];

/** Quién arranca el worker: un `--lookback` aquí pisa a los tres de arriba. */
const ARRANCADORES = ["deploy/cloud/docker-compose.yml", "demo/soc_local.sh"];

describe("DICTAMEN_WATCH_MS · cubre la ventana del worker", () => {
  it("lee el lookback de las tres declaraciones y de quien arranca el worker", () => {
    const valores: Array<[string, number]> = [];

    for (const [rel, re, porque] of DECLARACIONES) {
      const m = re.exec(lee(rel));
      expect(
        m,
        `${rel} dejó de declarar el lookback de la forma que este test sabe leer ` +
          `(${porque}). La guarda se quedaría CIEGA: arréglala antes de seguir.`,
      ).not.toBeNull();
      valores.push([rel, Number(m?.[1])]);
    }

    for (const rel of ARRANCADORES) {
      const src = lee(rel);
      if (!src.includes("--lookback")) {
        continue; // no lo pisa: gobierna el default del CLI
      }
      const m = /--lookback[\s"',=]+([\d.]+)/.exec(src);
      expect(
        m,
        `${rel} pasa --lookback y este test no supo leer el valor: la ventana real ` +
          `del worker dejó de ser visible desde aquí.`,
      ).not.toBeNull();
      valores.push([rel, Number(m?.[1])]);
    }

    for (const [rel, v] of valores) {
      expect(Number.isFinite(v) && v > 0, `${rel}: lookback ilegible (${v})`).toBe(true);
    }

    const [peorRel, peor] = valores.reduce((a, b) => (b[1] > a[1] ? b : a));
    expect(
      DICTAMEN_WATCH_MS,
      `la ventana de sondeo (${DICTAMEN_WATCH_MS} ms) se quedó por debajo del ` +
        `lookback del worker (${peor} s, en ${peorRel}): habría incidentes a los ` +
        `que la pasada automática todavía puede emitirles —o corregirles— y la ` +
        `pantalla ya no estaría mirando.`,
    ).toBeGreaterThanOrEqual(peor * 1000);
  });
});
