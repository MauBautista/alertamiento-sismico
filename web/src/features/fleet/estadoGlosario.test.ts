// [T-2.85.b] EL PANEL Y LA CONSOLA HABLAN EL MISMO IDIOMA — lado de la consola.
//
// El panel del gabinete decía `NO CONTESTA`, `DATO RETENIDO`, `S/D`. La consola
// decía `OPERATIVO`, `DEGRADADO`, `SIN ENLACE`. Quien opera mira LAS DOS
// pantallas, y cada traducción que hace de cabeza bajo presión es un sitio donde
// se equivoca.
//
// La fuente de verdad es `shared/glossary/estados.json` — JSON y no un módulo
// porque el otro consumidor es un HTML servido por un Pi sin build. Aquí se
// comprueban las tres cosas que hacen que el glosario gobierne de verdad:
//
//   1. `estadoGlosario.ts` (la copia que la consola IMPORTA en ejecución) dice
//      exactamente lo que dice el JSON. Igualdad en los dos sentidos.
//   2. Ninguna fuente de `features/fleet` estrena un literal de estado fuera del
//      glosario — el mismo analizador de raíces que corre sobre el panel en
//      `edge/tests/test_glosario_de_estados.py`, y probado aquí contra fuentes
//      sintéticas antes de creerle nada.
//   3. Los términos que PRODUCE la nube se leen del productor
//      (`api/.../schemas/fleet.py`), no se copian a mano. Misma lección que
//      `shared/sdk-ts/src/bms.ts` con `ACK_KIND`: la lista que se deriva no
//      puede divergir; la escrita a mano siempre acaba divergiendo.
//
// LAS LISTAS SE COMPARAN POR IGUALDAD, NUNCA POR CONTENCIÓN.

import { readdirSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";

import { describe, expect, it } from "vitest";

import * as GLOSARIO from "./estadoGlosario";

const RAIZ = resolve(process.cwd(), "..");
const JSON_GLOSARIO = join(RAIZ, "shared", "glossary", "estados.json");
const FLEET = resolve(process.cwd(), "src", "features", "fleet");
const PRODUCTOR = join(RAIZ, "api", "src", "takab_api", "schemas", "fleet.py");

interface Eje {
  significa: string;
  panel: string | null;
  consola: string | null;
  detecta: string[];
  solo_en_el_panel_porque?: string[];
  solo_en_la_consola_porque?: string[];
}
interface Divergencia {
  eje: string;
  panel: string;
  consola: string;
  arreglo: string;
  dueno: string;
}

const G = JSON.parse(readFileSync(JSON_GLOSARIO, "utf-8")) as {
  ejes: Record<string, Eje>;
  divergencias: Divergencia[];
};

/** Frase en MAYÚSCULAS: la forma en que estas dos superficies rotulan estado. */
const MAYUS = /[A-ZÁÉÍÓÚÑ][-A-ZÁÉÍÓÚÑ0-9/·()+.]*(?:[ ][-A-ZÁÉÍÓÚÑ0-9/·()+.]+)*/g;

/**
 * `frase → eje` de las que hablan de un eje SIN usar su término canónico.
 *
 * Es el analizador de `edge/tests/test_glosario_de_estados.py`, palabra por
 * palabra: si los dos censos midieran distinto, el glosario tendría dos lecturas
 * y volveríamos al problema del principio.
 */
export function intrusas(frases: Set<string>, ejes: Record<string, Eje>): Record<string, string> {
  const fuera: Record<string, string> = {};
  for (const [nombre, d] of Object.entries(ejes)) {
    const canonicos = [d.panel, d.consola].filter((x): x is string => !!x);
    for (const f of frases) {
      if (d.detecta.some((r) => f.includes(r)) && !canonicos.some((c) => f.includes(c))) {
        fuera[f] = nombre;
      }
    }
  }
  return fuera;
}

/** Toda frase en mayúsculas de las fuentes de PRODUCCIÓN de `features/fleet`. */
function frasesDeLaConsola(): Set<string> {
  const out = new Set<string>();
  for (const nombre of readdirSync(FLEET)) {
    if (!/\.tsx?$/.test(nombre) || nombre.includes(".test.")) continue;
    let texto = readFileSync(join(FLEET, nombre), "utf-8");
    // Los comentarios explican el defecto histórico con sus palabras: citarlos
    // no es estrenar un literal, y contarlos convertiría cada explicación en
    // una infracción.
    texto = texto.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
    const literales = texto.match(/'[^'\n]*'|"[^"\n]*"|`[^`]*`/g) ?? [];
    const jsx = (texto.match(/>[^<>{}\n]+</g) ?? []).map((s) => s.slice(1, -1));
    for (const trozo of [...literales, ...jsx]) {
      for (const p of trozo.match(MAYUS) ?? []) {
        const limpio = p.replace(/^[ ·\-.]+|[ ·\-.]+$/g, "");
        if (limpio && /[A-ZÁÉÍÓÚÑ]/.test(limpio)) out.add(limpio);
      }
    }
  }
  return out;
}

/**
 * FRASES DE LA CONSOLA QUE TOCAN UNA RAÍZ Y NO SON ESTADO — con su razón.
 *
 * VACÍA, y así se queda mientras se pueda. Igualdad, no contención: quien añada
 * una tiene que escribir por qué su frase no habla del eje cuya raíz contiene.
 */
const NO_SON_ESTADO: Record<string, string> = {};

/* =====================================================================
   C-0 · NO-VACUIDAD — si el barrido no encuentra nada, el resto miente
   ===================================================================== */

describe("glosario de estados · el barrido encuentra la consola", () => {
  it("lee el glosario compartido y los ejes de las dos superficies", () => {
    expect(Object.keys(G.ejes).length).toBeGreaterThanOrEqual(8);
    for (const [nombre, d] of Object.entries(G.ejes)) {
      expect(d.panel ?? d.consola, `${nombre}: eje sin ningún término`).toBeTruthy();
      expect(d.detecta.length, `${nombre}: eje sin raíces`).toBeGreaterThan(0);
      // Donde el estado NO PUEDE ser idéntico, la diferencia está DECLARADA.
      // Aplanarla sería inventar una equivalencia falsa, que es peor que tener
      // dos vocabularios: la nube ve al gabinete por el latido y nada más.
      if (d.panel === null) expect(d.solo_en_la_consola_porque?.length).toBeGreaterThan(0);
      if (d.consola === null) expect(d.solo_en_el_panel_porque?.length).toBeGreaterThan(0);
    }
  });

  it("barre las fuentes de producción de la flota", () => {
    const frases = frasesDeLaConsola();
    expect(frases.size).toBeGreaterThan(100);
    expect(frases.has("SIN ENLACE")).toBe(true);
    expect(frases.has("S/D")).toBe(true);
  });
});

/* =====================================================================
   C-1 · LA COPIA QUE LA CONSOLA IMPORTA NO PUEDE SEPARARSE DEL JSON
   ===================================================================== */

describe("glosario · la consola sale del glosario, no de su memoria", () => {
  it("`estadoGlosario.ts` dice exactamente lo que dice el JSON", () => {
    const delModulo = new Set(Object.values(GLOSARIO).filter((v) => typeof v === "string"));
    const delJson = new Set(
      Object.values(G.ejes)
        .map((d) => d.consola)
        .filter((x): x is string => !!x),
    );
    expect(
      [...delModulo].sort(),
      "el módulo que la consola IMPORTA se separó de `shared/glossary/estados.json`. " +
        "Corrige el JSON y copia, nunca al revés: el panel del gabinete lee el mismo " +
        "fichero y no puede importar nada.",
    ).toEqual([...delJson].sort());
  });
});

/* =====================================================================
   C-2 · EL CENSO — nadie estrena un literal fuera del glosario
   ===================================================================== */

describe("censo · el analizador sabe lo que busca", () => {
  it.each([
    ["DATOS CONGELADOS DESDE 04:12", "vejez"],
    ["EL GABINETE NO RESPONDE", "pieza_muda"],
    ["GABINETE FUERA DE LÍNEA", "enlace_nube"],
    ["ESTACIÓN DADA DE BAJA", "baja_administrativa"],
    ["BATERÍA SIN DATO", "ausencia"],
  ])("caza %s como sinónimo recién estrenado de «%s»", (frase, eje) => {
    expect(intrusas(new Set([frase]), G.ejes)).toEqual({ [frase]: eje });
  });

  it.each(["SIN ENLACE", "UPS · S/D", "0 DEGRADADOS", "RETIRADO · PERO SIGUE REPORTANDO"])(
    "no acusa a «%s», que usa el término del glosario",
    (frase) => {
      expect(intrusas(new Set([frase]), G.ejes)).toEqual({});
    },
  );
});

describe("censo · ninguna fuente de la flota estrena un literal de estado", () => {
  it("cuadra con la deuda declarada", () => {
    const medidas = intrusas(frasesDeLaConsola(), G.ejes);
    const detalle = Object.entries(medidas)
      .filter(([f]) => !(f in NO_SON_ESTADO))
      .map(([f, eje]) => `  · ${JSON.stringify(f)} habla del eje «${eje}»`)
      .join("\n");
    expect(
      Object.keys(medidas).sort(),
      "LA CONSOLA ESTRENÓ UN LITERAL DE ESTADO FUERA DEL GLOSARIO " +
        "(`shared/glossary/estados.json`). O usa el término que ya existe —el panel " +
        "del gabinete lo usa y quien opera mira las dos pantallas—, o añádelo al " +
        `glosario con su razón.\n${detalle}`,
    ).toEqual(Object.keys(NO_SON_ESTADO).sort());
  });
});

/* =====================================================================
   C-3 · EL PRODUCTOR — lo que la nube emite se LEE, no se copia
   ===================================================================== */

describe("glosario · los términos que produce la nube se leen del productor", () => {
  const productor = readFileSync(PRODUCTOR, "utf-8");
  const constante = (nombre: string) => {
    const m = new RegExp(`^${nombre}\\s*=\\s*"([^"]*)"`, "m").exec(productor);
    expect(m, `${nombre} desapareció de ${PRODUCTOR}`).not.toBeNull();
    return m![1];
  };

  it("`derive_fleet_state` emite exactamente los términos del glosario", () => {
    // `derived_state` llega por la API con estas palabras dentro. Si el
    // productor las renombra, la consola contaría ceros en silencio (el defecto
    // de T-2.59) y además hablaría otro idioma que el panel.
    expect({
      OPERATIVO: constante("OPERATIVO"),
      DEGRADADO: constante("DEGRADADO"),
      SIN_ENLACE: constante("SIN_ENLACE"),
    }).toEqual({
      OPERATIVO: G.ejes.veredicto_sano.consola,
      DEGRADADO: G.ejes.veredicto_degradado.consola,
      SIN_ENLACE: G.ejes.enlace_nube.consola,
    });
  });

  it("el relé mudo se llama `NO CONTESTA` en el productor, como en el panel", () => {
    // [T-2.85.b · deuda 2 · PAGADA 2026-08-13] Era una divergencia declarada:
    // la nube emitía `RELÉS ILEGIBLES` donde el panel dice `NO CONTESTA`, para
    // el MISMO hecho —el módulo que gobierna los relés no responde—. La consola
    // PINTA esta cadena tal cual llega en `degrade_reasons`, así que no aparece
    // en sus fuentes y el censo de arriba no puede verla: se vigila aquí,
    // contra el productor.
    //
    // El prefijo `RELÉS ·` se queda porque `degrade_reasons` es una lista de
    // pills sin contexto —`NO CONTESTA` a secas junto a `EN BATERÍA` no dice
    // QUÉ no contesta—, y el glosario pide que la frase CONTENGA el término
    // canónico, no que sea exactamente él.
    const emitido = constante("RELAYS_ILEGIBLES");
    expect(emitido).toContain(G.ejes.pieza_muda.consola);
    expect(emitido).toBe("RELÉS · NO CONTESTA");
    expect(intrusas(new Set([emitido]), G.ejes)).toEqual({});
  });

  it("cada divergencia abierta lleva su arreglo exacto y su dueño", () => {
    // Esta lista SOLO PUEDE BAJAR. Se compara por igualdad justamente para que
    // pagar una deuda obligue a borrar su entrada en el mismo cambio: una
    // divergencia que sobrevive a su arreglo es peor que no haberla declarado,
    // porque documenta un defecto que ya no existe y esconde que quedó uno.
    //
    // Queda `vejez`, y su `por_que_sigue_abierta` dice lo que se midió al
    // intentar pagarla (T-2.137, 2026-08-13).
    expect(G.divergencias.map((d) => d.eje).sort()).toEqual(["vejez"]);
    for (const d of G.divergencias) {
      expect(Object.keys(G.ejes)).toContain(d.eje);
      expect(d.panel).not.toEqual(d.consola);
      expect(d.arreglo.length).toBeGreaterThan(20);
      expect(d.dueno.length).toBeGreaterThan(5);
    }
  });
});
