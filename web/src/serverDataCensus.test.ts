// [T-2.84.c · hueco RO-7.a] EL CENSO: nada obligaba al componente número 28.
//
// Regla de oro 7: todo componente maneja `loading`, `error`, `empty` y `stale`.
// «Mostrar un dato congelado como si fuera live es peor que mostrar sin datos».
//
// La matriz de trazabilidad lo midió el 2026-08-08: 27 componentes usan
// `StateFrame`, sólo 14 tienen la prueba de los cuatro estados, y ≥12 pintan
// dato de servidor FUERA del marco. La única guarda era `expectFourStates()`,
// un ayudante OPT-IN que cada test tiene que acordarse de llamar — y de eso no
// se acuerda nadie para el componente siguiente.
//
// No es teórico. Esta regla se ha roto CUATRO veces documentadas en este repo:
//   · T-2.59 — `/fleet` pintaba "0 SIN ENLACE" en verde con la API caída,
//     porque la tira de KPI vive FUERA del StateFrame.
//   · el panel del gabinete pintaba features CONGELADAS como vivas.
//   · la tira de KPI de `/fleet` pintaba ceros con la API caída.
//   · el banner de privacidad acusaba de no consentir a quien sí consintió.
//
// Un test de componente no caza esto: `getByText` pasa igual. Lo único que lo
// caza sin ojos humanos es DERIVAR del árbol quién posee dato de servidor y
// cruzarlo contra quién declara sus cuatro estados. El analizador vive en
// `test-utils/serverDataCensus.ts` —y allí está explicada la señal estructural—;
// aquí están las afirmaciones, la DEUDA declarada y las pruebas del propio
// analizador contra fuentes sintéticas.
//
// LAS LISTAS SE COMPARAN POR IGUALDAD, NUNCA POR CONTENCIÓN. Si alguien arregla
// una entrada, este test se pone rojo y le obliga a borrar su línea. Una
// excepción que puede crecer sola no es una excepción, es un agujero — este
// repo ya lo aprendió dos veces (`DEUDA_HEREDADA` y la exención de
// `--tk-surface-3`, ambas en `designTokens.test.ts`).

import { join, resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { STATE_PRECEDENCE, resolveState } from "./components/StateFrame";
import {
  censar,
  ficherosConPruebaDeCuatroEstados,
  ficherosDeTest,
  fuentesDeProduccion,
  HOOKS_DE_LECTURA,
  type FuenteEntrada,
  type Transporte,
} from "./test-utils/serverDataCensus";

const SRC = resolve(process.cwd(), "src");

/**
 * LOS TRANSPORTES — el único axioma del censo, y es un conjunto cerrado.
 *
 * Todo lo demás se DERIVA: no hay ni una lista de componentes en este fichero
 * que no sea deuda medida. Sólo hay dos formas de que un dato del servidor
 * entre en este árbol de React:
 *
 *  1. HTTP, por los hooks de LECTURA de `@tanstack/react-query` (los declara
 *     `HOOKS_DE_LECTURA`; `useMutation` queda fuera a propósito: el resultado
 *     de una acción que el operador acaba de disparar no es un dato que la
 *     pantalla presente como hecho vigente).
 *  2. El canal live, por `useLiveSocket` — la única superficie que reparte los
 *     frames del WebSocket. `features/console/socket.ts` es un re-export y el
 *     analizador atraviesa la cadena.
 *
 * EXCLUIDO CON RAZÓN — `auth/session.store.ts::useSessionStore`: `me` no es un
 * dato que un panel presente como medición vigente, es la IDENTIDAD de la
 * sesión. Se establece una vez en el arranque, `RequireSession` bloquea el
 * árbol hasta que existe y NADA la refresca, así que no puede envejecer bajo
 * los pies del operador. Contarla metería `App`, `RouteGuard`, `RequireSession`
 * y `LoginPage` en un censo de paneles de datos (medido: 34 componentes en vez
 * de 21, con la mitad del ruido en plomería de sesión). La exclusión NO se
 * cree: la vigila el test «la sesión no se refresca» — el día que alguien le
 * ponga un refetch, este censo tiene que volver a incluirla.
 */
const TRANSPORTES: Transporte[] = [
  { file: join(SRC, "live", "socket.ts"), export: "useLiveSocket" },
];

const PRODUCCION = fuentesDeProduccion(SRC);
const CENSO = censar(PRODUCCION, { root: SRC, transportes: TRANSPORTES });
const CON_PRUEBA = ficherosConPruebaDeCuatroEstados(ficherosDeTest(SRC), PRODUCCION, SRC);

/* =====================================================================
   NO-VACUIDAD — si el barrido no encuentra nada, el resto miente
   ===================================================================== */

describe("censo de dato de servidor · el barrido encuentra el árbol", () => {
  it("parsea el marcado de producción y halla los transportes", () => {
    expect(PRODUCCION.length).toBeGreaterThan(100);
    expect(CENSO.productores.length).toBeGreaterThan(40);
    expect(CENSO.componentes.length).toBeGreaterThan(15);
  });

  it("el cierre es TRANSITIVO: `FleetPage` es productora sin llamar a `useQuery`", () => {
    // FleetPage llama a useFleet, que llama a useQuery. Si el punto fijo se
    // quedara en un salto, el censo sólo vería los hooks y ni un solo panel.
    expect(CENSO.productores).toContain("features/fleet/useFleet.ts::useFleet");
    expect(CENSO.productores).toContain("features/fleet/FleetPage.tsx::FleetPage");
  });

  it("atraviesa el re-export del canal live", () => {
    // `features/console/socket.ts` re-exporta `useLiveSocket` de `live/socket.ts`.
    // Sin seguir la cadena, `useSiteSoh` no sería productora y la salud del
    // gabinete —que es dato de servidor puro— saldría del censo entera.
    expect(CENSO.productores).toContain("features/console/useSiteSoh.ts::useSiteSoh");
  });

  it("la sesión no se refresca — por eso puede quedar fuera de los transportes", () => {
    // Guarda de la EXCLUSIÓN, no del store (mismo patrón que `--tk-surface-3`
    // en designTokens.test.ts). Sin esto la exención se pudre en silencio: si
    // algún día `me` se refresca, la identidad SÍ podría envejecer en pantalla.
    const store = PRODUCCION.find((f) => f.path.endsWith(join("auth", "session.store.ts")));
    expect(store, "auth/session.store.ts desapareció: revisa la exclusión").toBeDefined();
    const src = (store?.text ?? "").replace(/\/\/[^\n]*/g, "").replace(/\/\*[\s\S]*?\*\//g, "");
    for (const veneno of ["setInterval", "refetchInterval", "@tanstack/react-query"]) {
      expect(
        src.includes(veneno),
        `session.store.ts ahora usa \`${veneno}\`: \`me\` puede envejecer y el store ` +
          "deja de ser identidad estable. Añádelo a TRANSPORTES y vuelve a medir.",
      ).toBe(false);
    }
  });

  it("`useMutation` no es un transporte", () => {
    expect(HOOKS_DE_LECTURA).toContain("useQuery");
    expect(HOOKS_DE_LECTURA).toContain("useInfiniteQuery");
    expect(HOOKS_DE_LECTURA).not.toContain("useMutation");
  });
});

/* =====================================================================
   C-1 · PRECEDENCIA EN UN SOLO SITIO  (criterio 3 · T-2.79.d)
   ===================================================================== */

/**
 * La precedencia es un parámetro del contrato (`STATE_PRECEDENCE` +
 * `resolveState`, en `components/StateFrame.tsx`) y nadie más puede
 * materializar un `data-state`. Por eso `T-2.79.d` se cerró cambiando UNA
 * tabla, no 27 componentes.
 */
describe("censo · la precedencia vive en UN solo sitio", () => {
  it("`STATE_PRECEDENCE` es la tabla, y `resolveState` la única que decide", () => {
    expect([...STATE_PRECEDENCE]).toEqual(["loading", "error", "stale", "empty"]);
    expect(resolveState({ loading: true, error: "x", empty: true, stale: true })).toBe("loading");
    expect(resolveState({ loading: false, error: "x", empty: true, stale: true })).toBe("error");
    // [T-2.79.d · DECIDIDO 2026-08-11] El par en disputa: una lista vacía que
    // además lleva diez minutos sin refrescar. GANA `stale`, y la razón está
    // escrita entera sobre `STATE_PRECEDENCE`: «no hay» es un hecho sobre el
    // mundo y «no lo sé desde las hh:mm» es un hecho sobre nuestro
    // conocimiento; con los dos ciertos, sólo el segundo se puede verificar.
    expect(resolveState({ loading: false, error: null, empty: true, stale: true })).toBe("stale");
    expect(resolveState({ loading: false, error: null, empty: true, stale: false })).toBe("empty");
    expect(resolveState({ loading: false, error: null, empty: false, stale: true })).toBe("stale");
    expect(resolveState({ loading: false, error: null, empty: false, stale: false })).toBe("ready");
  });

  it("`resolveState` OBEDECE a la tabla, no la duplica en su cuerpo", () => {
    // Sin esto `STATE_PRECEDENCE` sería decorado: la función podría seguir un
    // orden distinto del que la tabla anuncia, y T-2.79.d cambiaría el rótulo
    // sin cambiar la conducta. Se apagan los estados uno a uno, en el orden en
    // que van ganando, y la secuencia observada tiene que ser la tabla.
    const activo = { loading: true, error: "x" as string | null, empty: true, stale: true };
    const apagar: Record<string, () => void> = {
      loading: () => (activo.loading = false),
      error: () => (activo.error = null),
      empty: () => (activo.empty = false),
      stale: () => (activo.stale = false),
    };
    const observado: string[] = [];
    for (let i = 0; i < STATE_PRECEDENCE.length; i += 1) {
      const ganador = resolveState(activo);
      observado.push(ganador);
      apagar[ganador]();
    }
    expect(observado).toEqual([...STATE_PRECEDENCE]);
  });

  /**
   * Vacío, y así se queda. `QuorumNodes.tsx:73` copiaba a mano
   * `<div className="soc-stateframe" data-state="empty">`: mismas clases, mismo
   * atributo, precedencia propia. Se arregló en esta tarea usando `StateFrame`.
   */
  const DATA_STATE_A_MANO: string[] = [];

  it("sólo `StateFrame.tsx` materializa `data-state`", () => {
    const foraneos = CENSO.dataStateForaneo
      .filter((x) => !x.startsWith(join("components", "StateFrame.tsx")))
      .sort();
    expect(
      foraneos,
      "marcado que se fabrica su propio `data-state` en vez de usar `StateFrame`. " +
        "Cada copia es una precedencia paralela que T-2.79.d NO podrá cambiar de " +
        `una vez:\n${foraneos.join("\n")}`,
    ).toEqual(DATA_STATE_A_MANO);
  });
});

/* =====================================================================
   C-2 · CONTENCIÓN — dato de servidor pintado FUERA del marco
   ===================================================================== */

/**
 * DEUDA MEDIDA (2026-08-09). Clave → identificadores teñidos que el componente
 * pinta fuera de cualquier `<StateFrame>`. La comparación es de IGUALDAD sobre
 * el mapa completo: un componente nuevo añade clave (rojo), uno arreglado la
 * quita (rojo), y uno que empiece a pintar un dato MÁS cambia su lista (rojo).
 * Los identificadores están en la clave a propósito: sin ellos, un componente
 * ya eximido podría crecer un pintado nuevo sin que nadie se enterase.
 *
 * Cada entrada lleva su razón en `RAZONES`, y el test exige que las dos tablas
 * tengan EXACTAMENTE las mismas claves: aquí no se exime sin explicar.
 */
const FUERA_DEL_MARCO: Record<string, string[]> = {
  "features/building/BuildingPage.tsx::BuildingDashboard": ["siren", "site", "soh"],
  "features/console/ConsolePage.tsx::ConsoleWall": [
    "actions",
    "catalog",
    "critical",
    "detailVisible",
    "epicenterIncident",
    "epicenterSite",
    "features",
    "focusIncident",
    "focusSite",
    "focusSiteId",
    "map",
    "quake",
    "quorumCommanded",
    "relays",
    "soh",
    "staleSince",
  ],
  "features/console/DrillBanner.tsx::DrillBanner": ["drill", "error", "pending"],
  "features/console/EpicenterModal.tsx::EpicenterModal": ["effective"],
  "features/fleet/FleetAdmin.tsx::FleetAdminPanel": ["codeConfigured", "gatewaysOf"],
  "features/fleet/FleetPage.tsx::FleetPage": [
    "activos",
    "codeConfigured",
    "counts",
    "ghosts",
    "maintenance",
    "sinDato",
    "versions",
    "visible",
  ],
  "features/fleet/SiteCard.tsx::SiteCard": ["selfTest"],
  "features/tenants/ComplianceLabelsCard.tsx::ComplianceLabelsCard": [
    "available",
    "doc",
    "unreadable",
  ],
  "features/tenants/UsersCard.tsx::UsersCard": ["data"],
  "features/triage/TriagePage.tsx::TriagePage": [
    "cctv",
    "current",
    "deepLinkMiss",
    "detail",
    "forensics",
    "matrix",
    "staleSince",
    "triage",
  ],
  "shell/OperatorMenu.tsx::OperatorMenu": ["label"],
};

/**
 * Por qué cada una está fuera del marco. Tres clases, y sólo la primera es
 * inocente:
 *
 *   (a) SOBREPUESTO / FORMULARIO — meterlo dentro del marco lo haría
 *       desaparecer en `loading`/`error` justo cuando hace falta, o borraría lo
 *       que el operador está tecleando. Legítimo.
 *   (b) GUARDA A MANO QUE HOY FUNCIONA — el componente distingue "sin dato" por
 *       su cuenta y tiene test que lo mide. Legítimo, pero frágil: es la forma
 *       exacta del bug de T-2.59, y por eso queda censado.
 *   (c) DEUDA — no hay guarda ni prueba. Se declara, no se esconde.
 */
const RAZONES: Record<string, string> = {
  "features/building/BuildingPage.tsx::BuildingDashboard":
    "(c) DEUDA. La cabecera (`site.data.name`, code y lat/lon) y el `<dl>` de SALUD DEL " +
    "GABINETE (`soh`) se guardan a mano: `site.isError` pinta SITIO NO DISPONIBLE con " +
    'REINTENTAR, y `soh?.x ?? "S/D"` evita inventar salud. Pero NINGUNO declara `stale`: ' +
    "un `soh` de hace dos horas se pinta idéntico a uno de hace un segundo, que es " +
    "literalmente el defecto que RO-7.c cerró en el panel del gabinete y aquí sigue " +
    "abierto en la nube. `siren` es estado de mutación y va a SirenTestPanel.",
  "features/console/ConsolePage.tsx::ConsoleWall":
    "(a) SOBREPUESTOS. El riel de detalle (`DetailPanel`), los dos modales (`ComparePanel`, " +
    "`EpicenterModal`) y los dos banners son HERMANOS del StateFrame del wall, no hijos: " +
    "están anclados a la página y meterlos dentro los borraría en `loading`/`error`, que es " +
    "cuando el operador más necesita el detalle del sitio. Cada hijo trae su propio marco " +
    "(DetailPanel tiene tres). Lo que SÍ queda pendiente es que `staleSince` sólo viaja a " +
    "DetailPanel dentro de `link`: los dos modales no reciben frescura ninguna.",
  "features/console/DrillBanner.tsx::DrillBanner":
    "(a) TIRA DE ACCIÓN. `drill-idle` vive fuera del marco porque el e2e de T-1.62 mide que " +
    "no pase de 60 px y porque dentro desaparecería en `loading`, dejando al operador sin " +
    "el botón de INICIAR SIMULACRO. `error` y `pending` vienen de `useMutation` (arrancar un " +
    "simulacro), no son un dato presentado como hecho; `drill === null` sólo abre el botón.",
  "features/console/EpicenterModal.tsx::EpicenterModal":
    "(a) CONTROL DE FORMULARIO. `<input value={coordsDraft ?? formatPoint(effective)}>` es la " +
    "caja de lat/lon manual: tiene que seguir siendo editable mientras `GET /events` carga, " +
    "y dentro del marco el operador perdería lo tecleado en cada refetch. Aparte de esto, el " +
    "modal arrastra deuda real: su StateFrame no declara `empty` ni `staleSince` (ver C-3).",
  "features/fleet/FleetAdmin.tsx::FleetAdminPanel":
    "(a) FORMULARIOS QUE SUSTITUYEN A LA LISTA. `HardwareForm` y `RetireDialog` reemplazan el " +
    "listado mientras se edita: colgarlos del StateFrame de ESTACIONES los haría desaparecer " +
    "en cada refetch con el formulario a medio llenar. `gatewaysOf(site_id)` es la consulta " +
    "ya cargada y `codeConfigured` es un booleano de habilitación, no una medición.",
  "features/fleet/FleetPage.tsx::FleetPage":
    "(b) EL CASO T-2.59, ya arreglado a mano y por eso censado. La tira de KPI es la cabecera " +
    "de la página y vive fuera del marco; su guarda es `sinDato = fleet.loading || " +
    "fleet.error !== null`, que pone `S/D` en los siete contadores en vez del cero " +
    'tranquilizador que dejó a la consola afirmando "flota entera operativa" con la API ' +
    "caída. Igual `maintenance.readError` (C3) y la sección de FANTASMAS, que es un `role=" +
    '"alert"` y tiene que sobrevivir al marco. Funciona hoy porque `FleetPage.test.tsx` lo ' +
    "mide; queda bajo igualdad para que nadie añada el octavo contador sin guarda.",
  "features/fleet/SiteCard.tsx::SiteCard":
    "(c) DEUDA, y de las gordas: la tarjeta NO tiene StateFrame ninguno y no tiene prueba de " +
    "los cuatro estados (ver C-4). Los chips del autodiagnóstico son el acuse de un comando " +
    "que el operador acaba de emitir (`useSelfTest`), con una máquina de fases " +
    "idle/issued/acked/expired/rejected que sí distingue SIN ACUSE (TTL) de RECHAZADO — pero " +
    "esa máquina es paralela a los cuatro estados y nadie la cruza con ellos.",
  "features/tenants/ComplianceLabelsCard.tsx::ComplianceLabelsCard":
    "(a) FORMULARIO Y PIE. Las notas y el alta de afirmaciones cuelgan de `doc`/`unreadable`, " +
    "que el StateFrame de la propia tarjeta ya resolvió justo encima; están fuera porque un " +
    "formulario dentro del marco perdería lo tecleado en cada refetch. `unreadable === null` " +
    "es la puerta que prohíbe editar un registro ilegible —guardar encima lo borraría sin " +
    "que nadie pudiera leer qué decía— y tiene que evaluarse fuera para poder cerrarla.",
  "features/tenants/UsersCard.tsx::UsersCard":
    "(a) RÓTULO DE PROCEDENCIA. La pastilla DIRECTORIO COGNITO / DIRECTORIO SIMULADO va en la " +
    "cabecera de la tarjeta, fuera del marco y con la puerta `data.backend !== null`: dice " +
    "con qué directorio se está hablando, así que tiene que leerse TAMBIÉN mientras la lista " +
    "carga — es el rótulo que avisa de que nada de lo de abajo se escribe de verdad.",
  "features/triage/TriagePage.tsx::TriagePage":
    "(b) MISMO PATRÓN QUE T-2.59, ya arreglado a mano. El rótulo `N INCIDENTES CARGADOS` está " +
    "fuera del marco y su guarda explícita (`triage.loading || triage.error !== null` ⇒ " +
    'SIN DATO · HISTORIAL NO DISPONIBLE) existe porque anunciaba "0 INCIDENTES CARGADOS" al ' +
    "lado del propio mensaje de error, y cero incidentes tras un sismo es la afirmación más " +
    "tranquilizadora de esta pantalla. `InspectionMatrix` y `TriageDetail` son paneles " +
    "hermanos con marco propio; `deepLinkMiss` es un aviso de navegación, no un dato. " +
    "[T-2.82.a] `staleSince` es la EDAD del historial, y no se pinta: baja a `TriageDetail` " +
    "para que el panel del quórum pueda fechar lo que afirma cuando el incidente no " +
    "referencia evento — el dato de esa rama es la fila del incidente, que sale de esta " +
    "consulta. Contarla aquí es correcto (viaja fuera del marco) y es justo lo que hay que " +
    "vigilar: el día que alguien la PINTE en vez de pasarla, sigue censada. " +
    "[T-3.12.c] `cctv` está aquí por la MISMA razón que `forensics`: no se pinta, baja " +
    "entero a `CctvPanel`, que sí tiene su marco con las cuatro entradas y su `staleSince` " +
    "de verdad. Se cuenta igual, y eso es lo correcto: el día que alguien saque una cifra " +
    "de evacuación a esta página sin marco, este censo lo dice.",
  "shell/OperatorMenu.tsx::OperatorMenu":
    '(c) DEUDA menor pero real. `label = profile.data?.display_name ?? me?.role ?? ""` se ' +
    "pinta en la topbar de TODAS las pantallas sin marco ni prueba de cuatro estados. El " +
    "fallback al rol es honesto (nunca inventa un nombre) y un StateFrame en la topbar " +
    "competiría con el de la pantalla de debajo —el mismo motivo por el que el banner de " +
    'privacidad renunció a su REINTENTAR—, pero hoy nada distingue "aún no cargó" de ' +
    '"el perfil falló": las dos cosas se ven como el rol a secas.',
};

describe("censo · nada de dato de servidor se pinta fuera de `StateFrame`", () => {
  it("toda exención lleva su razón escrita (criterio 2)", () => {
    expect(Object.keys(RAZONES).sort()).toEqual(Object.keys(FUERA_DEL_MARCO).sort());
    for (const [k, v] of Object.entries(RAZONES)) {
      expect(v.length, `la razón de ${k} es demasiado corta para ser una razón`).toBeGreaterThan(
        120,
      );
    }
  });

  it("el censo cuadra con la deuda declarada, identificador a identificador", () => {
    const detalle = (clave: string) =>
      CENSO.sitios
        .filter((s) => s.clave === clave)
        .map((s) => `    L${s.linea} ${s.donde} ← ${s.ids.join(", ")}`)
        .join("\n");
    const nuevos = Object.keys(CENSO.fueraDelMarco)
      .filter((k) => !(k in FUERA_DEL_MARCO))
      .map((k) => `\n  ${k}\n${detalle(k)}`);
    expect(
      nuevos,
      "COMPONENTES QUE PINTAN DATO DE SERVIDOR FUERA DE `StateFrame` y no estaban " +
        "censados. Mete el marcado dentro de un `<StateFrame>` con sus cuatro " +
        "entradas — no añadas la línea a FUERA_DEL_MARCO salvo que puedas escribir " +
        `su razón en RAZONES:${nuevos.join("")}`,
    ).toEqual([]);
    expect(
      CENSO.fueraDelMarco,
      "el censo ya no cuadra: o alguien arregló una entrada (borra su línea de " +
        "FUERA_DEL_MARCO y de RAZONES) o un componente ya censado empezó a pintar " +
        "un dato MÁS (mételo en el marco).",
    ).toEqual(FUERA_DEL_MARCO);
  });
});

/* =====================================================================
   C-3 · CABLEADO — todo `<StateFrame>` declara sus cuatro entradas
   ===================================================================== */

/**
 * DEUDA MEDIDA (2026-08-09): once marcos que se callan una entrada. Un
 * `<StateFrame>` sin `staleSince` AFIRMA «este dato no puede envejecer», y sin
 * `empty` afirma «nunca está vacío». Se declaran en vez de rellenarse a ciegas:
 * escribir `staleSince={null}` donde el dato SÍ puede envejecer sería fabricar
 * exactamente la mentira que este censo persigue, y decidir la frescura de once
 * paneles no es una tarea de una línea (cada uno necesita su reloj y su umbral,
 * como `FLEET_STALE_MS` o `HEARTBEAT_STALE_MS`).
 *
 * Comparación por IGUALDAD: un `<StateFrame>` NUEVO que se calle una entrada
 * sale rojo, y arreglar uno de éstos obliga a borrar su línea.
 */
const MARCOS_INCOMPLETOS: string[] = [
  "features/building/BuildingPage.tsx#HISTORIAL DEL SITIO falta staleSince",
  "features/console/ComparePanel.tsx#COMPARATIVA falta error,staleSince",
  "features/console/DetailPanel.tsx#ACCIONES DEL INCIDENTE falta staleSince",
  "features/console/DetailPanel.tsx#CCTV falta error,staleSince",
  "features/console/DetailPanel.tsx#INCIDENTE falta error,staleSince",
  "features/console/DrillModal.tsx#SITIOS falta staleSince",
  "features/console/EpicenterModal.tsx#EVENTO falta empty,staleSince",
  "features/console/IncidentTable.tsx#INCIDENTES ABIERTOS falta error,staleSince",
  "features/fleet/FleetAdmin.tsx#ESTACIONES falta staleSince",
  "features/triage/CatalogPanel.tsx#CATÁLOGO falta staleSince",
  // `StructuralTriage.tsx#Evaluación de campo` salió de esta lista en T-2.82.a:
  // `useDamageReports` ya deriva la edad de su consulta y el marco la declara.
];

describe("censo · todo `<StateFrame>` cablea las cuatro entradas", () => {
  it("ninguno se calla una", () => {
    const flojos = CENSO.marcos.map((f) => `${f.clave} falta ${f.faltan.join(",")}`).sort();
    const conLinea = CENSO.marcos
      .map((f) => `  ${f.fichero}:${f.linea} (${f.clave}) falta ${f.faltan.join(",")}`)
      .sort()
      .join("\n");
    expect(
      flojos,
      "un `<StateFrame>` sin `staleSince` afirma «este dato no puede envejecer», y " +
        "sin `empty` afirma «nunca está vacío». Si es cierto, DILO en el marcado " +
        `(\`staleSince={null}\`) — el silencio es la mentira:\n${conLinea}`,
    ).toEqual(MARCOS_INCOMPLETOS);
  });
});

/* =====================================================================
   C-4 · COBERTURA CONDUCTUAL — ¿existe la PRUEBA de los cuatro estados?
   ===================================================================== */

/**
 * ÉSTE ES EL PRODUCTO DE LA TAREA: los nueve que quedan sin cubrir, con nombre.
 * De los 21 componentes que poseen dato de servidor, 12 tienen un test que
 * llama a `expectFourStates` y estos nueve no. La lista es la deuda, no la
 * excusa; y comparada por igualdad hace que el componente NÚMERO 22 tenga que
 * escribir su prueba o añadirse aquí a la vista de todos.
 */
const SIN_PRUEBA_DE_CUATRO_ESTADOS: string[] = [
  // Cabecera y SALUD DEL GABINETE guardados a mano, sin `stale` (ver C-2).
  "features/building/BuildingPage.tsx::BuildingDashboard",
  // Su marco de SITIOS no declara `staleSince` (C-3) y nadie prueba los cuatro.
  "features/console/DrillModal.tsx::DrillModal",
  // Marco sin `empty` ni `staleSince` (C-3) y el input fuera del marco (C-2).
  "features/console/EpicenterModal.tsx::EpicenterModal",
  // Marco de ESTACIONES sin `staleSince`; los formularios viven fuera (C-2).
  "features/fleet/FleetAdmin.tsx::FleetAdminPanel",
  // No tiene StateFrame NINGUNO: la máquina de fases del self-test va por libre.
  "features/fleet/SiteCard.tsx::SiteCard",
  // Tiene marco completo, pero nadie lo ejerce en los cuatro estados.
  "features/tenants/VisibilityCard.tsx::VisibilityCard",
  // Marco completo salvo `staleSince`; el catálogo es de referencia, no vivo.
  "features/triage/CatalogPanel.tsx::CatalogPanel",
  // [T-2.82.a] Ya NO le falta `staleSince` —su marco declara las cuatro
  // entradas y `StructuralTriage.test.tsx` ejerce el estado `stale` con reloj
  // falso—, pero nadie recorre los cuatro con `expectFourStates`.
  "features/triage/StructuralTriage.tsx::StructuralTriage",
  // Sin marco: el nombre del operador en la topbar de TODAS las pantallas.
  "shell/OperatorMenu.tsx::OperatorMenu",
];

describe("censo · todo componente con dato de servidor tiene su prueba", () => {
  it("`expectFourStates` cubre a todos los censados", () => {
    const sin = CENSO.componentes
      .filter((c) => !CON_PRUEBA.has(c.fichero))
      .map((c) => c.clave)
      .sort();
    expect(
      sin,
      "componentes que POSEEN dato de servidor y no tienen la prueba de los cuatro " +
        "estados. Escribe un test que llame a `expectFourStates` — la lista es la " +
        `deuda, no la excusa:\n${sin.join("\n")}`,
    ).toEqual(SIN_PRUEBA_DE_CUATRO_ESTADOS);
  });

  it("el recuento del censo es el que dice la ficha", () => {
    // Cifras vivas: si el árbol crece, esta línea es la que obliga a volver a
    // mirar el censo en vez de dejarlo envejecer en un comentario.
    expect({
      conDato: CENSO.componentes.length,
      conPrueba: CENSO.componentes.filter((c) => CON_PRUEBA.has(c.fichero)).length,
      sinMarcoPropio: CENSO.componentes.filter((c) => !c.tieneMarco).length,
    }).toEqual({ conDato: 24, conPrueba: 15, sinMarcoPropio: 2 });
  });
});

/* =====================================================================
   EL PROPIO ANALIZADOR — sin esto el censo podría estar leyendo aire
   ===================================================================== */

const RAIZ = "/censo";
const T_FALSO: Transporte[] = [{ file: "/censo/live.ts", export: "useLiveSocket" }];

function analizar(archivos: Record<string, string>) {
  const fuentes: FuenteEntrada[] = Object.entries(archivos).map(([path, text]) => ({ path, text }));
  return censar(fuentes, { root: RAIZ, transportes: T_FALSO });
}

describe("el analizador del censo · probado contra fuentes sintéticas", () => {
  it("caza al que llama a `useQuery` y lo pinta a pelo", () => {
    const c = analizar({
      "/censo/A.tsx": `
        import { useQuery } from "@tanstack/react-query";
        export default function A() {
          const q = useQuery({ queryKey: ["x"], queryFn: f });
          return <div>{q.data?.name}</div>;
        }`,
    });
    expect(c.fueraDelMarco).toEqual({ "A.tsx::A": ["q"] });
  });

  it("no dice nada del mismo componente si el dato va DENTRO del marco", () => {
    const c = analizar({
      "/censo/A.tsx": `
        import { useQuery } from "@tanstack/react-query";
        import StateFrame from "./StateFrame";
        export default function A() {
          const q = useQuery({ queryKey: ["x"], queryFn: f });
          return (
            <StateFrame label="A" loading={q.isPending} error={null} empty={false} staleSince={null}>
              <div>{q.data?.name}</div>
            </StateFrame>
          );
        }`,
    });
    expect(c.fueraDelMarco).toEqual({});
    expect(c.marcos).toEqual([]);
  });

  it("el tinte es TRANSITIVO dentro del componente, no sólo la variable del hook", () => {
    const c = analizar({
      "/censo/A.tsx": `
        import { useQuery } from "@tanstack/react-query";
        export default function A() {
          const q = useQuery({ queryKey: ["x"], queryFn: f });
          const filas = (q.data ?? []).filter(Boolean);
          const total = filas.length;
          return <div>{total}</div>;
        }`,
    });
    expect(c.fueraDelMarco).toEqual({ "A.tsx::A": ["total"] });
  });

  it("el cierre atraviesa módulos: un hook propio delata a su componente", () => {
    const c = analizar({
      "/censo/useCosas.ts": `
        import { useQuery } from "@tanstack/react-query";
        export function useCosas() { return useQuery({ queryKey: ["c"], queryFn: f }); }`,
      "/censo/A.tsx": `
        import { useCosas } from "./useCosas";
        export default function A() {
          const cosas = useCosas();
          return <p>{cosas.data}</p>;
        }`,
    });
    expect(c.productores).toContain("useCosas.ts::useCosas");
    expect(c.fueraDelMarco).toEqual({ "A.tsx::A": ["cosas"] });
  });

  it("atraviesa un re-export para llegar al transporte", () => {
    const c = analizar({
      "/censo/live.ts": `export function useLiveSocket() { return null; }`,
      "/censo/puente.ts": `export { useLiveSocket } from "./live";`,
      "/censo/A.tsx": `
        import { useLiveSocket } from "./puente";
        export default function A() {
          const s = useLiveSocket();
          return <p>{s.status}</p>;
        }`,
    });
    expect(c.fueraDelMarco).toEqual({ "A.tsx::A": ["s"] });
  });

  it("`useMutation` sola no convierte a nadie en panel de datos", () => {
    const c = analizar({
      "/censo/A.tsx": `
        import { useMutation } from "@tanstack/react-query";
        export default function A() {
          const m = useMutation({ mutationFn: f });
          return <button disabled={m.isPending}>{m.isError ? "FALLÓ" : "OK"}</button>;
        }`,
    });
    expect(c.componentes).toEqual([]);
  });

  it("un envoltorio `{cond && <StateFrame/>}` NO es pintar fuera del marco", () => {
    // Sin esta precisión el censo denunciaría justo al código que sí guarda:
    // `CatalogPanel` salía rojo por su propio acordeón.
    const c = analizar({
      "/censo/A.tsx": `
        import { useQuery } from "@tanstack/react-query";
        import StateFrame from "./StateFrame";
        export default function A({ open }) {
          const q = useQuery({ queryKey: ["x"], queryFn: f });
          return <div>{open && (
            <StateFrame label="A" loading={q.isPending} error={q.error} empty={false} staleSince={null}>
              <p>{q.data}</p>
            </StateFrame>
          )}</div>;
        }`,
    });
    expect(c.fueraDelMarco).toEqual({});
  });

  it("no se puede LAVAR el dato metiéndolo en un hijo presentacional", () => {
    // El hijo no se culpa (no puede distinguir vacío de cargando), pero pasarle
    // el dato fuera del marco cuenta como pintarlo: es el caso `KpiStrip`.
    const c = analizar({
      "/censo/Kpi.tsx": `export default function Kpi({ n }) { return <span>{n}</span>; }`,
      "/censo/A.tsx": `
        import { useQuery } from "@tanstack/react-query";
        import Kpi from "./Kpi";
        export default function A() {
          const q = useQuery({ queryKey: ["x"], queryFn: f });
          return <Kpi n={q.data.total} />;
        }`,
    });
    expect(c.fueraDelMarco).toEqual({ "A.tsx::A": ["q"] });
    expect(c.componentes.map((x) => x.clave)).toEqual(["A.tsx::A"]);
  });

  it("`className` y `onClick` no son pintar: gobiernan estilo y acción", () => {
    const c = analizar({
      "/censo/A.tsx": `
        import { useQuery } from "@tanstack/react-query";
        export default function A() {
          const q = useQuery({ queryKey: ["x"], queryFn: f });
          return <div className={q.isError ? "malo" : "bien"} onClick={() => q.refetch()} />;
        }`,
    });
    expect(c.fueraDelMarco).toEqual({});
  });

  it("delata un `data-state` fabricado a mano", () => {
    const c = analizar({
      "/censo/A.tsx": `export default function A() {
        return <div className="soc-stateframe" data-state="empty">SIN DATOS</div>;
      }`,
    });
    expect(c.dataStateForaneo).toEqual(["A.tsx:2"]);
  });

  it("delata un `<StateFrame>` que se calla una entrada", () => {
    const c = analizar({
      "/censo/A.tsx": `
        import StateFrame from "./StateFrame";
        export default function A() {
          return <StateFrame label="A" loading={false}><p>hola</p></StateFrame>;
        }`,
    });
    expect(c.marcos).toEqual([
      {
        fichero: "A.tsx",
        clave: "A.tsx#A",
        linea: 4,
        faltan: ["error", "empty", "staleSince"],
      },
    ]);
  });
});
