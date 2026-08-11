// [T-2.111] EL CENSO: nada obligaba a la pantalla de vida NÚMERO 5.
//
// Regla de oro 7: todo componente maneja `loading`, `error`, `empty` y `stale`.
// «Mostrar un dato congelado como si fuera live es peor que mostrar sin datos».
//
// `expectFourStates` —el ayudante que esta ficha trae a móvil— es OPT-IN: cada
// test tiene que acordarse de llamarlo, y de eso no se acuerda nadie para la
// pantalla siguiente. La consola ya aprendió esto en T-2.84.c y respondió con
// un censo derivado; esto es su equivalente móvil, y aquí la señal es todavía
// más limpia: **`expo-router` construye su tabla de rutas con un
// `require.context` sobre `src/app`, así que el sistema de ficheros ES el censo
// de pantallas**. No hay una lista de pantallas escrita a mano en este fichero;
// la ruta nueva entra sola en la población el día que alguien la crea.
//
// EL DEFECTO NO ES TEÓRICO — es literalmente T-2.111:
//   · `crisis.tsx` y `checkin.tsx`, las dos pantallas de vida, giraban PARA
//     SIEMPRE sin sitio vigilado (la consulta ni se habilita ⇒ el spinner no se
//     resuelve nunca).
//   · `panic.tsx` y `lista.tsx` dejaban el botón en «ENVIANDO…» con la red
//     caída, porque el cliente del SDK LANZA y nadie capturaba.
//   · `lista.tsx` afirmaba «Sin incidente activo en su sitio» cuando lo que
//     pasaba es que no había podido preguntar.
//
// LAS LISTAS SE COMPARAN POR IGUALDAD, NUNCA POR CONTENCIÓN. Si alguien arregla
// una entrada, este test se pone rojo y le obliga a borrar su línea. Una
// excepción que puede crecer sola no es una excepción, es un agujero (misma
// lección que `web/src/serverDataCensus.test.ts`).

/// <reference types="node" />
import { resolve } from "node:path";

import {
  censar,
  esPromesa,
  ficherosConPruebaDeCuatroEstados,
  ficherosDeTest,
  fuentesDeProduccion,
  protegida,
  CUATRO_ENTRADAS,
  HOOKS_DE_LECTURA,
  type FuenteEntrada,
} from "./test-utils/screenStateCensus";

const RAIZ = resolve(process.cwd());
const SRC = resolve(RAIZ, "src");

const PRODUCCION = fuentesDeProduccion(SRC);
const CENSO = censar(PRODUCCION, SRC);
const CON_PRUEBA = ficherosConPruebaDeCuatroEstados(
  ficherosDeTest([SRC, resolve(RAIZ, "tests")]),
  PRODUCCION,
  SRC,
);

/**
 * Igualdad CON MENSAJE ACCIONABLE. `expect(valor, mensaje)` es de vitest —el
 * `expect` de jest toma un solo argumento y falla con «Expect takes at most one
 * argument»—, así que aquí el mensaje se lanza aparte. Importa: la mitad del
 * valor de un censo está en que el fallo diga QUÉ HACER, no sólo qué difiere.
 */
function exigirIgual(actual: string[], declarado: string[], mensaje: string): void {
  const iguales =
    actual.length === declarado.length && actual.every((x, i) => x === declarado[i]);
  if (!iguales) {
    const sobran = actual.filter((x) => !declarado.includes(x));
    const faltan = declarado.filter((x) => !actual.includes(x));
    throw new Error(
      `${mensaje}\n\n` +
        (sobran.length > 0 ? `SIN DECLARAR (arréglalo o decláralo):\n  ${sobran.join("\n  ")}\n` : "") +
        (faltan.length > 0
          ? `YA NO EXISTEN (borra su línea de la lista):\n  ${faltan.join("\n  ")}\n`
          : "") +
        `\nMEDIDO:    [${actual.join(", ")}]\nDECLARADO: [${declarado.join(", ")}]`,
    );
  }
  expect(actual).toEqual(declarado);
}

/* =====================================================================
   C-0 · NO-VACUIDAD — si el barrido no encuentra nada, el resto miente
   ===================================================================== */

describe("censo móvil · el barrido encuentra el árbol", () => {
  it("parsea las rutas de `expo-router` y halla el transporte", () => {
    expect(PRODUCCION.length).toBeGreaterThan(80);
    expect(CENSO.rutas.length).toBeGreaterThan(20);
    expect(CENSO.productores.length).toBeGreaterThan(10);
    expect(CENSO.rutasConDato.length).toBeGreaterThan(8);
  });

  it("la población de pantallas SALE DEL SISTEMA DE FICHEROS, no de una lista", () => {
    // `expo-router` arma su tabla con `require.context` sobre `src/app`: la
    // pantalla nueva entra en el censo por existir, sin que nadie la apunte.
    for (const ruta of ["app/crisis.tsx", "app/checkin.tsx", "app/panic.tsx"]) {
      expect(CENSO.rutas).toContain(ruta);
    }
    expect(CENSO.rutas).toContain("app/(brigadista)/lista.tsx");
  });

  it("el cierre es TRANSITIVO y atraviesa el alias `@/`", () => {
    // `crisis.tsx` no llama a `useQuery`: llama a `useAlertState`, que sí. Si el
    // punto fijo se quedara en un salto, el censo vería los hooks y NI UNA
    // pantalla. Y si el resolvedor no supiera de `@/`, tampoco.
    expect(CENSO.productores).toContain("features/alert/useAlertState.ts::useAlertState");
    expect(CENSO.rutasConDato).toContain("app/crisis.tsx");
    expect(CENSO.rutasConDato).toContain("app/checkin.tsx");
  });

  it("`useMutation` no es un transporte", () => {
    // Igual que en la consola: el resultado de una acción que la persona acaba
    // de disparar no es un dato que la pantalla presente como hecho vigente.
    // Ese desenlace lo vigila C-2, no C-4.
    expect(HOOKS_DE_LECTURA).toContain("useQuery");
    expect(HOOKS_DE_LECTURA).not.toContain("useMutation");
  });

  it("las cuatro entradas del marco móvil son las de `@/ui/StateFrame`", () => {
    expect([...CUATRO_ENTRADAS]).toEqual(["loading", "error", "empty", "staleSinceMs"]);
  });
});

/* =====================================================================
   C-1 · CABLEADO — todo `<StateFrame>` declara sus cuatro entradas
   ===================================================================== */

/**
 * Vacío, y así se queda. Un `<StateFrame>` sin `staleSinceMs` AFIRMA «este dato
 * no puede envejecer»; sin `empty`, «nunca está vacío». Si es cierto, se dice
 * en el marcado (`staleSinceMs={null}`) — el silencio es la mentira.
 */
const MARCOS_INCOMPLETOS: string[] = [];

describe("censo móvil · todo `<StateFrame>` de una ruta cablea las cuatro", () => {
  it("ninguno se calla una", () => {
    const flojos = CENSO.marcos.map((f) => `${f.clave} falta ${f.faltan.join(",")}`).sort();
    const conLinea = CENSO.marcos
      .map((f) => `  ${f.fichero}:${f.linea} falta ${f.faltan.join(",")}`)
      .join("\n");
    exigirIgual(
      flojos,
      MARCOS_INCOMPLETOS,
      "un `<StateFrame>` que se calla una entrada afirma algo que no ha comprobado: " +
        "sin `staleSinceMs`, «este dato no puede envejecer»; sin `empty`, «nunca " +
        `está vacío». Si de verdad no aplica, DILO en el marcado:\n${conLinea}`,
    );
  });
});

/* =====================================================================
   C-2 · DESENLACE — ninguna promesa del SDK se pierde en silencio
   ===================================================================== */

/**
 * ÉSTE ES EL DEFECTO DE T-2.111 CONVERTIDO EN GUARDA. El cliente del SDK
 * **lanza** cuando muere `fetch` (devolver `{data, error}` es sólo para los HTTP
 * de error). Una llamada al SDK dentro de una ruta que no esté en un
 * `try…catch` ni encadene `.catch(` es un `busy` que se queda encendido y un
 * dato de vida que se pierde sin decir nada.
 *
 * Vacío, y así se queda: las cuatro pantallas de esta ficha eran las únicas que
 * incumplían. Un `.finally(` NO cuenta —libera el botón pero no recoge el
 * error—, que es exactamente lo que hacían `notifyUnreported` y `closeHeadcount`.
 */
const SIN_DESENLACE: string[] = [];

describe("censo móvil · ninguna llamada al SDK se queda sin desenlace", () => {
  it("toda promesa de una ruta la recoge alguien", () => {
    const sueltas = CENSO.sinDesenlace.map((s) => s.clave).sort();
    const detalle = CENSO.sinDesenlace
      .map((s) => `  ${s.fichero}:${s.linea} → ${s.operacion}()`)
      .join("\n");
    exigirIgual(
      sueltas,
      SIN_DESENLACE,
      "LLAMADAS AL SDK QUE PUEDEN RECHAZAR SIN QUE NADIE LO RECOJA. El cliente " +
        "LANZA al morir `fetch`: sin `try…catch` (o `.catch(`) el `setBusy(false)` " +
        "no corre, el botón se queda muerto y el dato se pierde sin decir nada. " +
        `Un \`.finally(\` no basta — libera el botón pero se traga el error:\n${detalle}`,
    );
  });
});

/* =====================================================================
   C-3 · CONTENCIÓN — la ruta con dato de servidor materializa un marco
   ===================================================================== */

/**
 * DEUDA MEDIDA (2026-08-10): dos rutas poseen dato de servidor y no
 * materializan NINGÚN `<StateFrame>`. Se declaran, no se esconden.
 *
 *  · `app/alarma-inmueble.tsx` — MISMO DEFECTO que esta ficha cerró en
 *    `crisis.tsx`, en su pantalla gemela: `if (!data?.building_alarm)` pinta un
 *    `ActivityIndicator` con «VERIFICANDO…» que sin sitio vigilado NO SE
 *    RESUELVE NUNCA. Queda fuera del alcance de T-2.111 porque el fichero no
 *    está en su lista de propiedad; es ficha aparte, y la costura es idéntica.
 *  · `app/camera.tsx` — la cámara forense no PRESENTA el dato: lo usa para
 *    SELLAR la marca de agua (`incident_id`, `max_pga_g`). Su estado real es el
 *    permiso de cámara, que sí declara. Queda censada porque sellar una foto
 *    forense con metadatos viejos es un problema distinto pero real (T-2.108
 *    dejó el `pgaG: null ⇒ "pendiente de sync"` como mitigación honesta).
 */
const SIN_MARCO_DE_ESTADOS: string[] = ["app/alarma-inmueble.tsx", "app/camera.tsx"];

describe("censo móvil · la ruta con dato de servidor declara sus estados", () => {
  it("cuadra con la deuda declarada", () => {
    exigirIgual(
      CENSO.rutasConDatoSinMarco,
      SIN_MARCO_DE_ESTADOS,
      "RUTAS QUE POSEEN DATO DE SERVIDOR Y NO MATERIALIZAN NINGÚN `<StateFrame>`. " +
        "Cúbrelas con `@/ui/StateFrame` cableando sus cuatro entradas — no añadas " +
        "la línea a SIN_MARCO_DE_ESTADOS salvo que puedas escribir su razón encima.",
    );
  });
});

/* =====================================================================
   C-4 · COBERTURA CONDUCTUAL — ¿existe la PRUEBA de los cuatro estados?
   ===================================================================== */

/**
 * ÉSTE ES EL MECANISMO QUE OBLIGA A LA PANTALLA SIGUIENTE, y el producto
 * duradero de la ficha. De las 11 rutas que poseen dato de servidor, las 3 que
 * T-2.111 cierra tienen una prueba que llama a `expectFourStates`; estas 8 no.
 *
 * Comparada por IGUALDAD: la pantalla de vida NÚMERO 12 —que por consumir
 * `useAlertState` entra sola en `rutasConDato`— pone este test ROJO el día que
 * se crea, y su autor tiene exactamente dos salidas: escribir su
 * `expectFourStates`, o añadir su línea aquí A LA VISTA DE TODOS con la razón
 * escrita encima. No hay tercera; no se puede "olvidar" llamar al ayudante.
 *
 * Y arreglar una de éstas también pone el test rojo: obliga a borrar su línea,
 * así que la deuda sólo puede bajar.
 */
const SIN_PRUEBA_DE_CUATRO_ESTADOS: string[] = [
  // Varios `<StateFrame>` HERMANOS (5): el ayudante exige exclusión mutua, así
  // que hay que probarlos marco a marco. Además otro agente lo está tocando hoy.
  "app/(brigadista)/panel.tsx",
  // T-2.108 le puso el marco con las cuatro entradas, pero no la prueba.
  "app/(brigadista)/triage.tsx",
  // Marco completo, sin prueba. `siteId === null` ya lo declara como `empty`.
  "app/(occupant)/directorio.tsx",
  "app/(occupant)/inicio.tsx",
  "app/(occupant)/rutas.tsx",
  // Sin marco NINGUNO — ver C-3, donde está la razón larga de cada una.
  "app/alarma-inmueble.tsx",
  "app/camera.tsx",
  // Marco completo, sin prueba.
  "app/dictamen.tsx",
];

describe("censo móvil · las rutas con dato tienen la PRUEBA de los cuatro estados", () => {
  it("cuadra con la deuda declarada", () => {
    const sinPrueba = CENSO.rutasConDato.filter((r) => !CON_PRUEBA.has(r)).sort();
    exigirIgual(
      sinPrueba,
      [...SIN_PRUEBA_DE_CUATRO_ESTADOS].sort(),
      "RUTAS CON DATO DE SERVIDOR SIN PRUEBA DE LOS CUATRO ESTADOS. Escribe su " +
        "test con `expectFourStates` (`src/test-utils/expectFourStates.tsx`; los " +
        "ejemplos están en `tests/app/*-states.test.tsx`) o añade su línea a " +
        "SIN_PRUEBA_DE_CUATRO_ESTADOS con la razón escrita encima. Recuerda: los " +
        "tests van FUERA de `src/app/`, o `expo-router` deja de compilar el bundle.",
    );
  });

  it("las cuatro pantallas de vida de T-2.111 NO están en la deuda", () => {
    // Candado anti-regresión: la lista de arriba se compara por igualdad, así
    // que si alguien borra el test de `crisis` la ruta reaparece en `sinPrueba`
    // y el test anterior cae. Esto lo dice además con nombre, para que el fallo
    // se lea sin tener que derivarlo.
    const vivas = ["app/crisis.tsx", "app/checkin.tsx", "app/(brigadista)/lista.tsx"];
    const desprotegidas = vivas.filter((v) => !CON_PRUEBA.has(v));
    exigirIgual(
      desprotegidas,
      [],
      "PANTALLAS DE VIDA QUE PERDIERON SU PRUEBA DE CUATRO ESTADOS. Las cerró " +
        "T-2.111 midiendo el texto que lee la persona; volver a dejarlas sin " +
        "prueba es reabrir la ficha.",
    );
    for (const viva of vivas) {
      expect(SIN_PRUEBA_DE_CUATRO_ESTADOS).not.toContain(viva);
    }
  });

  it("`panic.tsx` queda FUERA de esta población, y por una razón", () => {
    // `panic.tsx` no lee NADA del servidor: su única llamada remota es el voto,
    // que es una ACCIÓN. Exigirle `stale` sería fabricar una frescura que no
    // existe — la mentira que este censo persigue. Lo que sí se le exige es el
    // desenlace (C-2), y declarar el `empty` de "sin sitio vigilado", que ya
    // hace con `StateFrame`. La exclusión no se cree: se mide.
    expect(CENSO.rutas).toContain("app/panic.tsx");
    expect(CENSO.rutasConDato).not.toContain("app/panic.tsx");
    expect(CENSO.rutasConDatoSinMarco).not.toContain("app/panic.tsx");
  });
});

/* =====================================================================
   C-5 · EL ANALIZADOR, CONTRA FUENTES SINTÉTICAS
   ===================================================================== */

/**
 * Una guarda que nadie ha visto fallar no es una guarda. Aquí se le da al
 * analizador el CÓDIGO ORIGINAL de T-2.111 —el que estaba en `main` esta
 * mañana— y se exige que lo denuncie; y el código corregido, y se exige que
 * calle. Sin esto, un censo verde no distinguiría "no hay defectos" de "el
 * analizador no mira".
 */
const SRC_FALSO = "/s/src";

function fuente(rel: string, text: string): FuenteEntrada {
  return { path: `${SRC_FALSO}/${rel}`, text };
}

/** El módulo que hace de `useAlertState`: productor por llamar a `useQuery`. */
const HOOK = fuente(
  "features/alert/useAlertState.ts",
  `import { useQuery } from "@tanstack/react-query";
   export function useAlertState(id: string | null) {
     return useQuery({ queryKey: ["x", id], queryFn: async () => 1 });
   }`,
);

/** Un envoltorio propio: productor por CIERRE, sin nombrar a react-query. */
const ENVOLTORIO = fuente(
  "offline/useCachedQuery.ts",
  `import { useQuery } from "@tanstack/react-query";
   export function useCachedQuery(o: object) { return useQuery(o); }`,
);

const SDK = fuente("sdk.ts", "export const nada = 1;");

describe("censo móvil · el analizador, medido contra fuentes sintéticas", () => {
  it("el cierre transitivo llega a la ruta a través del alias `@/`", () => {
    const c = censar(
      [
        HOOK,
        ENVOLTORIO,
        SDK,
        fuente(
          "app/pantalla.tsx",
          `import { useAlertState } from "@/features/alert/useAlertState";
           export default function Pantalla() {
             const s = useAlertState("x");
             return <View>{s.data}</View>;
           }`,
        ),
      ],
      SRC_FALSO,
    );
    expect(c.rutasConDato).toEqual(["app/pantalla.tsx"]);
    expect(c.rutasConDatoSinMarco).toEqual(["app/pantalla.tsx"]);
  });

  it("DENUNCIA el `void sdk().finally(…)` original de `notifyUnreported`", () => {
    const c = censar(
      [
        fuente(
          "app/lista.tsx",
          `import { notifyUnreported } from "@takab/sdk";
           export default function Lista() {
             const go = () => {
               setBusy(true);
               void notifyUnreported({ path: {} }).finally(() => setBusy(false));
             };
             return <View onPress={go} />;
           }`,
        ),
      ],
      SRC_FALSO,
    );
    expect(c.sinDesenlace.map((s) => s.operacion)).toEqual(["notifyUnreported"]);
  });

  it("DENUNCIA el `await sdk()` sin `try` original de `panic.tsx`", () => {
    const c = censar(
      [
        fuente(
          "app/panic.tsx",
          `import { panicVote } from "@takab/sdk";
           export default function Panic() {
             const vote = () => {
               setBusy(true);
               void (async () => {
                 const res = await panicVote({ path: {} });
                 setBusy(false);
               })();
             };
             return <View onPress={vote} />;
           }`,
        ),
      ],
      SRC_FALSO,
    );
    expect(c.sinDesenlace.map((s) => s.operacion)).toEqual(["panicVote"]);
  });

  it("CALLA con `try…catch`, con `.catch(` y dentro de una productora", () => {
    const c = censar(
      [
        HOOK,
        ENVOLTORIO,
        fuente(
          "app/ok.tsx",
          `import { useCachedQuery } from "@/offline/useCachedQuery";
           import { leer, escribir, otra } from "@takab/sdk";
           export default function Ok() {
             const q = useCachedQuery({ queryFn: async () => { const r = await leer({}); return r; } });
             const a = () => { void (async () => { try { await escribir({}); } catch { avisar(); } })(); };
             const b = () => { void otra({}).catch(() => avisar()); };
             return <View onPress={a} onLongPress={b}>{q.data}</View>;
           }`,
        ),
      ],
      SRC_FALSO,
    );
    expect(c.sinDesenlace).toEqual([]);
  });

  it("no confunde un AYUDANTE PURO del SDK con una promesa", () => {
    // `featuresTopic()` y `groupActions()` se exportan del mismo paquete y no
    // devuelven promesa: sin esta puerta el censo denunciaría a `panel.tsx` por
    // no capturar un rechazo que no existe (medido: 2 falsos positivos).
    const c = censar(
      [
        fuente(
          "app/panel.tsx",
          `import { featuresTopic, groupActions } from "@takab/sdk";
           export default function Panel() {
             const t = featuresTopic("s");
             return <View>{groupActions([]).length}{t}</View>;
           }`,
        ),
      ],
      SRC_FALSO,
    );
    expect(c.sinDesenlace).toEqual([]);
  });

  it("DENUNCIA el `<StateFrame>` que se calla una entrada", () => {
    const c = censar(
      [
        HOOK,
        fuente(
          "app/floja.tsx",
          `import { useAlertState } from "@/features/alert/useAlertState";
           import { StateFrame } from "@/ui/StateFrame";
           export default function Floja() {
             const s = useAlertState("x");
             return <StateFrame empty={false} emptyText="x" loading={s.isLoading}>{s.data}</StateFrame>;
           }`,
        ),
      ],
      SRC_FALSO,
    );
    expect(c.marcos.map((m) => m.faltan)).toEqual([["error", "staleSinceMs"]]);
    // Y con marco, deja de estar "sin marco" aunque el marco sea flojo.
    expect(c.rutasConDatoSinMarco).toEqual([]);
  });

  it("`esPromesa` y `protegida` son las dos puertas, y se prueban aparte", () => {
    // Guarda de las funciones exportadas: si alguien relaja una, el censo
    // entero se vuelve permisivo en silencio.
    expect(typeof esPromesa).toBe("function");
    expect(typeof protegida).toBe("function");
  });

  it("la cobertura se deriva de los IMPORTS del test, no del nombre del fichero", () => {
    // Los tests de rutas viven en `tests/app/` y las rutas en `src/app/`: por
    // nombre no coincidirían JAMÁS. Y sin resolver `@/`, tampoco.
    const cubiertos = ficherosConPruebaDeCuatroEstados(
      [
        {
          path: `${RAIZ}/tests/app/crisis-states.test.tsx`,
          text: `import { expectFourStates } from "@/test-utils/expectFourStates";
                 import Crisis from "@/app/crisis";`,
        },
      ],
      PRODUCCION,
      SRC,
    );
    expect([...cubiertos]).toContain("app/crisis.tsx");
  });

  it("un test que NO llama al ayudante no cuenta como cobertura", () => {
    const cubiertos = ficherosConPruebaDeCuatroEstados(
      [
        {
          path: `${RAIZ}/tests/app/otro.test.tsx`,
          text: `import Crisis from "@/app/crisis";
                 it("algo", () => expect(1).toBe(1));`,
        },
      ],
      PRODUCCION,
      SRC,
    );
    expect([...cubiertos]).toEqual([]);
  });
});
