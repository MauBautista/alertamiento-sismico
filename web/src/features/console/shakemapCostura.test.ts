// [T-7.24] LA COSTURA: el vocabulario del mapa de la sacudida está escrito a
// mano a los DOS lados, y aquí se cruzan los dos ficheros.
//
// EL DEFECTO QUE CIERRA, medido: los nombres de umbral (`pga_watch_g`,
// `pga_trip_g`) se teclean en
// `api/src/takab_api/shakemap/calculo.py` y otra vez en
// `web/src/features/console/shakemap.ts`. Hoy coinciden. Si mañana la nube
// renombra uno, `colorDeBanda` no lo encuentra en `PGA_COLOR`, lo manda a
// `PGA_SIN_BANDA` y TODOS los anillos y TODOS los puntos se vuelven grises en
// silencio — con la leyenda rotulando tan tranquila el nombre nuevo, porque la
// leyenda cita el umbral que llega en el rasgo. Las dos suites fabrican esas
// cadenas por su cuenta, así que ninguna de las dos se pondría roja: el mapa
// entero perdería su codificación sin un solo test en rojo.
//
// Lo mismo vale para los cuatro ESTADOS: uno que la nube renombre cae en la rama
// «no interpretable» de `vistaSacudida` y el mapa deja de pintarse entero.
//
// POR QUÉ AQUÍ Y NO EN `api/`: la víctima es la consola. Quien renombra en la
// nube no corre la suite de `web`, pero `make test` sí las corre las dos, y este
// fichero es el único punto del repositorio donde las dos listas se miran.
//
// ⚠️ Guarda de TEXTO sobre un fichero de Python, a propósito: importarlo desde
// TS es imposible y un tercer fichero de "vocabulario compartido" sería una
// TERCERA verdad sobre lo mismo.

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import {
  ESTADOS,
  ESTADO_PENDIENTE,
  PGA_COLOR,
  PROC_MEDIDO,
  PROC_MODELADO,
  UMBRALES,
} from "./shakemap";

const API = resolve(process.cwd(), "../api/src/takab_api");

/** Un módulo de la nube SIN comentarios: explican cada nombre citándolo en
 *  prosa, y contar esa prosa daría por declarado un nombre que ya no es el del
 *  código. Es la misma trampa que enmascara `cssContract.test.ts` en las hojas. */
function nube(ruta: string): string {
  return readFileSync(resolve(API, ruta), "utf8").replace(/^\s*#.*$/gm, "");
}

const CALCULO = nube("shakemap/calculo.py");
const SERVICIO = nube("shakemap/servicio.py");

/** El valor de una constante `NOMBRE = "cadena"` del módulo de la nube. */
function constante(nombre: string): string | null {
  const m = new RegExp(String.raw`^${nombre}\s*=\s*"([^"]*)"`, "m").exec(CALCULO);
  return m === null ? null : m[1];
}

/**
 * Los niveles que la nube PUBLICA, derivados como los deriva ella: los campos en
 * `_g` de `felt.Thresholds`.
 *
 * Se re-deriva en vez de leer una lista, porque la nube tampoco lee una lista
 * (`UMBRALES = tuple(f.name for f in dataclasses.fields(Thresholds) …)`). Un
 * umbral de PGA nuevo en la banda del inmueble aparece solo en el mapa — y tiene
 * que aparecer solo también en esta guarda, o la consola se quedaría sin color
 * para él y nadie se enteraría.
 */
function umbralesDeLaNube(): string[] {
  const felt = nube("felt.py");
  const clase = /class Thresholds:([\s\S]*?)\n\n\n/.exec(felt);
  expect(clase, "no se encontró `class Thresholds` en felt.py").not.toBeNull();
  return [...clase![1].matchAll(/^ {4}(\w+):\s*float/gm)]
    .map((m) => m[1])
    .filter((n) => n.endsWith("_g"));
}

describe("[T-7.24] los dos lados de la costura dicen lo MISMO", () => {
  it("el escáner lee de verdad los dos módulos de la nube", () => {
    // Sin este ancla, un módulo que cambiara de sitio dejaría todas las
    // comprobaciones de abajo comparando `null` con `null` o listas vacías.
    expect(CALCULO).toContain("UMBRALES");
    expect(constante("UMBRAL_WATCH"), "no se encontró UMBRAL_WATCH en calculo.py").not.toBeNull();
    expect(umbralesDeLaNube().length, "ningún umbral derivado de felt.Thresholds").toBeGreaterThan(
      1,
    );
    // Y la nube los DERIVA de la banda, no los teclea: si dejara de hacerlo, el
    // re-derivado de esta guarda ya no sería el mismo conjunto que el suyo.
    expect(CALCULO).toMatch(
      /UMBRALES = tuple\(\s*f\.name for f in dataclasses\.fields\(Thresholds\)/,
    );
  });

  it("los nombres de umbral que la nube publica, y en el mismo orden", () => {
    expect(
      umbralesDeLaNube(),
      "un umbral renombrado en la nube vuelve GRIS el mapa entero, sin un solo test en rojo",
    ).toEqual([...UMBRALES]);
    // Y cada uno tiene tinta en esta consola: sin ella cae en `PGA_SIN_BANDA`.
    for (const umbral of umbralesDeLaNube()) {
      expect(
        PGA_COLOR[umbral],
        `${umbral} llega de la nube y esta consola no lo sabe pintar`,
      ).toBeDefined();
    }
  });

  it("y la consola no INVENTA niveles: pinta EXACTAMENTE los que la nube publica", () => {
    // La otra mitad de la costura. Un nombre que la consola sabe pintar y la
    // nube no puede producir es una segunda verdad sobre el mismo cable.
    //
    // ⚠️ Aquí vivió una lista de excepción (`UMBRALES_RETIRADOS`) que eximía a
    // `correlacion_min_pga_g` «porque los snapshots ya persistidos siguen
    // trayendo ese anillo y pintarlos gris volvería gris el mapa de todos los
    // sismos anteriores». No existen esos snapshots, medido el 2026-09-21:
    // `git grep -n correlacion_min_pga_g HEAD` → vacío, `git grep -l -i shakemap
    // HEAD -- api/migrations db/` → 0 ficheros, y la tabla `incident_shakemap`
    // la crea por PRIMERA vez la migración `0069_mapa_de_sacudida.py`, de este
    // mismo cambio. Era un boquete con una razón inventada escrita al lado, que
    // es justo como se ensanchan. Si algún día hay una herencia de verdad se
    // declarará CON SU MEDICIÓN; hasta entonces, default-deny sin escape.
    expect(
      Object.keys(PGA_COLOR).sort(),
      "la consola pinta un nivel que la nube no publica, o le falta uno que sí",
    ).toEqual([...umbralesDeLaNube()].sort());
  });

  it("un `sin_datos` de esta nube VIAJA con un punto mudo por inmueble: no es una contradicción", () => {
    // Por qué está esta guarda aquí y no en `shakemap.test.ts`: la consola tiene
    // una rama que ACUSA al snapshot de contradecirse (`sin_datos` con medidas
    // dentro). Esa acusación sólo es legítima si la nube no puede producir ese
    // par por construcción, y eso se comprueba en la nube, no en una fixture.
    //
    // El defecto que cierra: la rama gateaba con `puntos.length > 0`, y resulta
    // que el snapshot `sin_datos` que esta nube publica de verdad trae un punto
    // MUDO por cada inmueble instrumentado. La consola le gritaba al operador
    // «EL SNAPSHOT SE DECLARA "SIN DATOS" Y TRAE 2 MEDIDA(S)» con cero medidas,
    // y tapaba la nota que sí importa. Falsa alarma en la pantalla del SOC.
    //
    // (1) el ESTADO se deriva de si hubo alguna medida…
    expect(
      CALCULO,
      "`sin_datos` ya no se deriva de las medidas: la rama de discrepancia queda sin premisa",
    ).toMatch(/hubo_medida = any\(m\.pga_g is not None for m in medidas\)/);
    // …(2) y los PUNTOS salen de las mismas `medidas`, SIN filtrar por valor.
    expect(CALCULO, "el punto ya no es uno por medida: revisar el predicado de la consola").toMatch(
      /puntos = tuple\(_punto\(m, [^)]*\) for m in medidas\)/,
    );
    // (3) y una `Medida` se construye por cada inmueble con coordenadas, mida o
    // no: el único filtro de `_medidas_de` es la geometría.
    const cuerpo = /def _medidas_de\([\s\S]*?(?=\ndef |$)/.exec(SERVICIO);
    expect(cuerpo, "no se encontró `_medidas_de` en servicio.py").not.toBeNull();
    expect(cuerpo![0]).toMatch(/for e in tabla\.items/);
    expect(cuerpo![0]).toMatch(/if e\.lat is not None and e\.lon is not None/);
    expect(
      /peak_pga_g is not None|pga_g is not None/.test(cuerpo![0]),
      "la nube empezó a filtrar los mudos: el `sin_datos` con puntos ya no es el caso normal",
    ).toBe(false);
  });

  it("los CUATRO estados del mapa", () => {
    const deLaNube = [
      constante("ESTADO_COMPLETO"),
      constante("ESTADO_SOLO_OBSERVADO"),
      constante("ESTADO_SIN_DATOS"),
      constante("ESTADO_PENDIENTE"),
    ];
    expect(
      deLaNube,
      "un estado renombrado cae en «no interpretable» y el mapa deja de pintarse",
    ).toEqual([...ESTADOS]);
    expect(deLaNube).toContain(ESTADO_PENDIENTE);
  });

  it("las DOS procedencias", () => {
    // Si éstas divergen no se pinta NADA: los builders son default-deny, un
    // rasgo sin la procedencia de su capa se descarta.
    expect([constante("PROC_MEDIDO"), constante("PROC_MODELADO")]).toEqual([
      PROC_MEDIDO,
      PROC_MODELADO,
    ]);
  });
});
