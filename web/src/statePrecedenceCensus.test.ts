// [T-2.79.d + T-2.82.a] EL CENSO DE LA PRECEDENCIA: que la tabla no se pueda sortear.
//
// `STATE_PRECEDENCE` (en `components/StateFrame.tsx`) decide qué gana cuando dos
// estados son ciertos a la vez, y T-2.79.d decidió que entre `empty` y `stale`
// gana `stale`. Pero una tabla central sólo gobierna si nadie puede esquivarla
// desde su componente, y hay exactamente dos formas de esquivarla:
//
//   1. APAGAR el `empty` cuando el dato está viejo. Es lo que hacía
//      `PrivacyConsentBanner` (`empty={sereno && …}`, y `sereno` exige
//      `staleSince === null`): la tabla nunca llegaba a ver el par en disputa, y
//      el resultado era la franja muda —`DATOS RETENIDOS · hh:mm UTC` y debajo
//      NADA—. Una precedencia local, escrita en un `&&`.
//   2. CLAVAR la frescura a `null`, que es afirmar «este dato no puede
//      envejecer» sin haberlo comprobado. En la pantalla donde el inspector
//      FIRMA un dictamen lo hacían todos los paneles (T-2.82.a).
//
// El analizador vive en `test-utils/statePrecedenceCensus.ts` —allí está
// explicada la señal estructural de cada una—; aquí están las afirmaciones, la
// DEUDA declarada y las pruebas del propio analizador contra fuentes sintéticas.
//
// LAS LISTAS SE COMPARAN POR IGUALDAD, NUNCA POR CONTENCIÓN. Si alguien arregla
// una entrada, este test se pone rojo y le obliga a borrar su línea. Una
// excepción que puede crecer sola no es una excepción, es un agujero — misma
// lección que `serverDataCensus.test.ts` y `mobile/src/screenStateCensus.test.ts`.

import { join, resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { STATE_PRECEDENCE } from "./components/StateFrame";
import { fuentesDeProduccion } from "./test-utils/serverDataCensus";
import {
  arbolDeLaPagina,
  frescuraClavada,
  marcosDe,
  parsear,
  precedenciasLocales,
  type FuenteEntrada,
} from "./test-utils/statePrecedenceCensus";

const SRC = resolve(process.cwd(), "src");

const PRODUCCION = fuentesDeProduccion(SRC);
const MODS = parsear(PRODUCCION);
const MARCOS = marcosDe(MODS, SRC);

/**
 * LA RAÍZ DE LA PÁGINA — y es lo ÚNICO escrito a mano de todo el censo.
 *
 * No se enumeran paneles: se enumera el punto de entrada, y de ahí se calcula
 * el cierre por etiquetas JSX. Que la raíz siga siendo la pantalla de firma no
 * se cree, se comprueba abajo (`la raíz es de verdad donde se firma`): si
 * alguien mueve el acto de firmar a otro fichero, el censo se pone rojo en vez
 * de seguir vigilando una pantalla que ya no es la que importa.
 */
const PANTALLA_DE_FIRMA = "features/triage/TriageDetail.tsx";

const ARBOL = arbolDeLaPagina(MODS, SRC, PANTALLA_DE_FIRMA);

/* =====================================================================
   C-0 · NO-VACUIDAD — si el barrido no encuentra nada, el resto miente
   ===================================================================== */

describe("censo de precedencia · el barrido encuentra el árbol", () => {
  it("parsea el marcado de producción y halla los marcos", () => {
    expect(PRODUCCION.length).toBeGreaterThan(100);
    expect(MARCOS.length).toBeGreaterThan(20);
  });

  it("la raíz es de verdad donde se firma el dictamen", () => {
    // Guarda de la RAÍZ. El censo entero cuelga de este fichero: si el acto de
    // firmar se muda, vigilar aquí sería vigilar una pantalla cualquiera.
    const fuente = PRODUCCION.find((f) => f.path === resolve(SRC, PANTALLA_DE_FIRMA));
    expect(fuente, `${PANTALLA_DE_FIRMA} desapareció: mueve la raíz del censo`).toBeDefined();
    expect(fuente?.text).toContain("FIRMAR DICTAMEN");
    expect(fuente?.text).toContain("detail.sign(");
  });

  it("el árbol de la página SE DERIVA de las etiquetas JSX, no de una lista", () => {
    // El cierre atraviesa el import: `TriageDetail` monta `<QuorumNodes>` y de
    // ahí sale su fichero. El panel número cuatro entrará solo.
    expect(ARBOL).toContain(PANTALLA_DE_FIRMA);
    expect(ARBOL).toContain("features/triage/QuorumNodes.tsx");
    expect(ARBOL).toContain("features/triage/StructuralTriage.tsx");
    expect(ARBOL).toContain("components/StateFrame.tsx");
    expect(ARBOL.length).toBeGreaterThan(5);
  });
});

/* =====================================================================
   C-1 · PRECEDENCIA LOCAL — nadie apaga su `empty` por la frescura
   ===================================================================== */

/**
 * VACÍA, Y ASÍ SE QUEDA. Medía UNA el 2026-08-11 —el `empty={sereno && …}` de
 * `PrivacyConsentBanner`, que es el defecto literal de T-2.79.d— y esa entrada
 * se pagó, no se declaró.
 *
 * Un marco cuyo `empty` dependa de su propio `staleSince` está decidiendo por su
 * cuenta el par que `STATE_PRECEDENCE` decide para toda la consola, y lo decide
 * al revés: apagando el estado que tiene texto. No añadas la línea salvo que
 * puedas escribir su razón encima.
 */
const PRECEDENCIA_LOCAL: string[] = [];

describe("censo · nadie apaga su `empty` porque el dato esté viejo (T-2.79.d)", () => {
  it("cuadra con la deuda declarada", () => {
    const medido = precedenciasLocales(MARCOS);
    const claves = medido.map((p) => p.clave).sort();
    const detalle = medido
      .map((p) => `  ${p.fichero}:${p.linea} (${p.clave}) — vía ${p.via.join(", ")}`)
      .join("\n");
    expect(
      claves,
      "MARCOS QUE APAGAN SU `empty` CUANDO EL DATO ESTÁ VIEJO. Eso es una " +
        "precedencia LOCAL: `STATE_PRECEDENCE` decidió que gana `stale` y FECHA la " +
        "ausencia, pero un `empty` apagado deja el marco sin nada que decir — la " +
        `franja muda de T-2.79.d. Declara el \`empty\` tal cual es:\n${detalle}`,
    ).toEqual(PRECEDENCIA_LOCAL);
  });

  it("la tabla que este censo defiende es la que decidió T-2.79.d", () => {
    // Sin esto el censo podría estar guardando una precedencia distinta de la
    // que la ficha decidió, y nadie lo notaría.
    expect([...STATE_PRECEDENCE]).toEqual(["loading", "error", "stale", "empty"]);
  });
});

/* =====================================================================
   C-2 · LA PANTALLA DONDE SE FIRMA — ningún panel clava su frescura
   ===================================================================== */

/**
 * VACÍA — LOS OCHO MARCOS DE LA PANTALLA DE FIRMA ESTÁN PAGADOS (2026-08-12).
 *
 * Medía SIETE el 2026-08-11, con un solo panel cableado (`ComplianceDeclared`).
 * Los siete se pagaron en T-2.82.a: cuatro (`BITÁCORA`, `QUÓRUM~2`, `DICTAMEN`,
 * `EVIDENCIA`) esperaban LA MISMA pieza —`Resource<T>` de `useIncidentDetail.ts`
 * sin marca de tiempo—, y por eso se hizo UNA vez ahí dentro en vez de cuatro
 * relojes a mano en el marcado; `QUÓRUM` recibe la edad del INCIDENTE, que baja
 * desde `TriagePage`; y `Evaluación de campo` la de su propia consulta, que
 * `useDamageReports` ahora deriva.
 *
 * NO AÑADAS UNA LÍNEA AQUÍ SIN SU RAZÓN MEDIDA. Escribir un `staleSince`
 * inventado es fabricar la mentira que este censo persigue, así que declarar la
 * deuda es legítimo; lo que no lo es es declararla sin decir qué falta y dónde
 * está el cambio. Comparada por IGUALDAD: un panel nuevo que clave `null` sale
 * rojo, y arreglar uno obliga a borrar su línea.
 */
const FRESCURA_CLAVADA: string[] = [];

/** Qué le falta a cada uno, y en qué fichero está el cambio. */
const RAZONES: Record<string, string> = {};

describe("censo · ningún panel de la pantalla de firma clava su frescura (T-2.82.a)", () => {
  it("toda exención lleva su razón escrita", () => {
    expect(Object.keys(RAZONES).sort()).toEqual([...FRESCURA_CLAVADA].sort());
    for (const [k, v] of Object.entries(RAZONES)) {
      expect(v.length, `la razón de ${k} es demasiado corta para ser una razón`).toBeGreaterThan(
        120,
      );
    }
  });

  it("la pieza que desbloqueó a cuatro de ellos SIGUE en su sitio", () => {
    // El reverso exacto del test que había aquí, que exigía que la pieza
    // FALTARA para que la excusa no envejeciera en un comentario. Pagada la
    // deuda, el riesgo se da la vuelta: quitar la edad de `Resource<T>` no
    // rompería ninguna prueba de panel —todas seguirían pintando, sólo que sin
    // poder decir nunca que el dato está viejo— y los cuatro marcos volverían a
    // mentir en silencio. Se vigila la RAÍZ, no cada consumidor.
    const hook = PRODUCCION.find((f) => f.path.endsWith(join("triage", "useIncidentDetail.ts")));
    expect(hook, "useIncidentDetail.ts desapareció: revisa el censo").toBeDefined();
    const iface = (hook?.text ?? "").split("export interface Resource<T>")[1]?.split("}")[0] ?? "";
    expect(iface, "no se encontró la interfaz `Resource<T>`").not.toBe("");
    expect(
      /staleSince/.test(iface),
      "`Resource<T>` dejó de llevar la edad de su consulta: BITÁCORA, QUÓRUM~2, " +
        "DICTAMEN y EVIDENCIA vuelven a no poder declarar su dato viejo en la " +
        "pantalla donde se firma un dictamen.",
    ).toBe(true);
  });

  it("la lista vacía NO lo está por vacuidad: los ocho marcos siguen ahí", () => {
    // El agujero que abre pagar la deuda. Mientras la lista tenía siete
    // entradas, un analizador que se quedara ciego se delataba solo; con la
    // lista vacía, encontrar CERO marcos también «cuadra». Este test cierra esa
    // puerta: la población se sigue DERIVANDO del árbol —no se enumera para
    // vigilar—, y lo que se fija es que la derivación siga viendo los ocho
    // paneles que el inspector tiene delante al firmar.
    const enLaPagina = MARCOS.filter((m) => ARBOL.includes(m.fichero)).map((m) => m.clave);
    expect(enLaPagina).toEqual([
      "features/triage/ComplianceDeclared.tsx#MARCO DECLARADO",
      "features/triage/IncidentTimeline.tsx#BITÁCORA",
      "features/triage/PostEventSummary.tsx#RESUMEN POST-EVENTO",
      "features/triage/QuorumNodes.tsx#QUÓRUM",
      "features/triage/QuorumNodes.tsx#QUÓRUM~2",
      "features/triage/StructuralTriage.tsx#Evaluación de campo",
      "features/triage/TriageDetail.tsx#DICTAMEN",
      "features/triage/TriageDetail.tsx#EVIDENCIA",
    ]);
  });

  it("cuadra con la deuda declarada", () => {
    const medido = frescuraClavada(MODS, SRC, MARCOS, ARBOL);
    const claves = medido.map((f) => `${f.clave} · ${f.motivo}`).sort();
    const detalle = medido
      .map((f) => `  ${f.fichero}:${f.linea} (${f.clave}) — ${f.detalle}`)
      .join("\n");
    expect(
      claves,
      "PANELES DE LA PANTALLA DONDE SE FIRMA UN DICTAMEN QUE NO PUEDEN DECLARAR SU " +
        "DATO VIEJO. Un dato congelado se pinta como vivo, que es exactamente lo que " +
        "la regla de oro 7 prohíbe — y aquí encima alguien firma encima de él. " +
        `Cablea la edad de su consulta:\n${detalle}`,
    ).toEqual(FRESCURA_CLAVADA);
  });
});

/* =====================================================================
   EL PROPIO ANALIZADOR — sin esto el censo podría estar leyendo aire
   ===================================================================== */

const RAIZ = "/censo";

function analizar(archivos: Record<string, string>) {
  const fuentes: FuenteEntrada[] = Object.entries(archivos).map(([path, text]) => ({ path, text }));
  const mods = parsear(fuentes);
  return { mods, marcos: marcosDe(mods, RAIZ) };
}

describe("el analizador · probado contra fuentes sintéticas", () => {
  it("DENUNCIA el `empty={sereno && …}` ORIGINAL del banner de privacidad", () => {
    // Éste es el código que estaba en `main` esta mañana, reducido a lo que
    // importa. Si el analizador no lo caza, el censo no vale nada.
    const { marcos } = analizar({
      "/censo/Banner.tsx": `
        import StateFrame from "./StateFrame";
        export default function Banner({ loading, error, dataUpdatedAt, status }) {
          const staleSince = !loading && !error && now - dataUpdatedAt > MS ? dataUpdatedAt : null;
          const notice = status?.notice ?? null;
          const sereno = !loading && !error && staleSince === null;
          return (
            <StateFrame label="Aviso" loading={loading} error={error}
              empty={sereno && (status === null || notice === null)}
              staleSince={staleSince}>
              {notice && <p>hola</p>}
            </StateFrame>
          );
        }`,
    });
    const medido = precedenciasLocales(marcos);
    expect(medido.map((p) => p.clave)).toEqual(["Banner.tsx#Aviso"]);
    expect(medido[0].via).toContain("sereno");
    expect(medido[0].via).toContain("staleSince");
  });

  it("CALLA con el mismo banner ya arreglado", () => {
    const { marcos } = analizar({
      "/censo/Banner.tsx": `
        import StateFrame from "./StateFrame";
        export default function Banner({ loading, error, dataUpdatedAt, status }) {
          const staleSince = !loading && !error && now - dataUpdatedAt > MS ? dataUpdatedAt : null;
          const notice = status?.notice ?? null;
          return (
            <StateFrame label="Aviso" loading={loading} error={error}
              empty={!loading && !error && (status === null || notice === null)}
              staleSince={staleSince}>
              {notice && <p>hola</p>}
            </StateFrame>
          );
        }`,
    });
    expect(precedenciasLocales(marcos)).toEqual([]);
  });

  it("no confunde COMPARTIR LA CONSULTA con decidir la precedencia", () => {
    // El falso positivo que haría inútil al censo: `q` alimenta a los cuatro
    // props porque ES la consulta. Un identificador que también entra en
    // `loading`/`error` no es el veredicto de frescura.
    const { marcos } = analizar({
      "/censo/Panel.tsx": `
        import StateFrame from "./StateFrame";
        export default function Panel() {
          const q = useFleet();
          return (
            <StateFrame label="FLOTA" loading={q.isPending} error={q.error}
              empty={q.data?.length === 0} staleSince={q.dataUpdatedAt}>
              <p>{q.data}</p>
            </StateFrame>
          );
        }`,
    });
    expect(precedenciasLocales(marcos)).toEqual([]);
  });

  it("caza el apagado aunque vaya por DOS saltos de variable", () => {
    // La deriva no se escribe siempre en una línea: `empty` mira a `hayAlgo`,
    // que mira a `fresco`, que mira a `staleSince`. El cierre es transitivo.
    const { marcos } = analizar({
      "/censo/Panel.tsx": `
        import StateFrame from "./StateFrame";
        export default function Panel({ items }) {
          const staleSince = viejo ? cuando : null;
          const fresco = staleSince === null;
          const hayAlgo = fresco && items.length === 0;
          return (
            <StateFrame label="X" loading={false} error={null}
              empty={hayAlgo} staleSince={staleSince}>
              <p>{items}</p>
            </StateFrame>
          );
        }`,
    });
    expect(precedenciasLocales(marcos).map((p) => p.clave)).toEqual(["Panel.tsx#X"]);
  });

  it("el árbol de la página atraviesa el import de la etiqueta JSX", () => {
    const { mods } = analizar({
      "/censo/Pagina.tsx": `
        import Hijo from "./Hijo";
        export default function Pagina() { return <div><Hijo /></div>; }`,
      "/censo/Hijo.tsx": `
        import Nieto from "./Nieto";
        export default function Hijo() { return <Nieto />; }`,
      "/censo/Nieto.tsx": `export default function Nieto() { return <p>x</p>; }`,
      "/censo/Suelto.tsx": `export default function Suelto() { return <p>y</p>; }`,
    });
    // `Suelto` NO cuelga de la página: el cierre no lo arrastra.
    expect(arbolDeLaPagina(mods, RAIZ, "Pagina.tsx")).toEqual([
      "Hijo.tsx",
      "Nieto.tsx",
      "Pagina.tsx",
    ]);
  });

  it("DENUNCIA el `staleSince={null}` clavado, y sólo dentro del árbol", () => {
    const { mods, marcos } = analizar({
      "/censo/Pagina.tsx": `
        import StateFrame from "./StateFrame";
        import Hijo from "./Hijo";
        export default function Pagina() {
          return (<div>
            <StateFrame label="A" loading={false} error={null} empty={false} staleSince={null}>
              <p>a</p>
            </StateFrame>
            <Hijo />
          </div>);
        }`,
      "/censo/Hijo.tsx": `
        import StateFrame from "./StateFrame";
        export default function Hijo({ edad }) {
          return <StateFrame label="B" loading={false} error={null} empty={false} staleSince={edad}><p>b</p></StateFrame>;
        }`,
      "/censo/Fuera.tsx": `
        import StateFrame from "./StateFrame";
        export default function Fuera() {
          return <StateFrame label="C" loading={false} error={null} empty={false} staleSince={null}><p>c</p></StateFrame>;
        }`,
    });
    const arbol = arbolDeLaPagina(mods, RAIZ, "Pagina.tsx");
    const medido = frescuraClavada(mods, RAIZ, marcos, arbol);
    // `A` clava el null; `B` recibe `edad` por prop y NADIE se la pasa; `C`
    // está fuera del árbol de la página y no es asunto de este censo.
    expect(medido.map((f) => `${f.clave} · ${f.motivo}`)).toEqual([
      "Hijo.tsx#B · prop-sin-cablear",
      "Pagina.tsx#A · nulo",
    ]);
  });

  it("CALLA cuando la edad viaja de verdad hasta el hijo", () => {
    const { mods, marcos } = analizar({
      "/censo/Pagina.tsx": `
        import Hijo from "./Hijo";
        export default function Pagina({ q }) { return <Hijo staleSince={q.staleSince} />; }`,
      "/censo/Hijo.tsx": `
        import StateFrame from "./StateFrame";
        export default function Hijo({ staleSince }) {
          return <StateFrame label="B" loading={false} error={null} empty={false} staleSince={staleSince}><p>b</p></StateFrame>;
        }`,
    });
    const arbol = arbolDeLaPagina(mods, RAIZ, "Pagina.tsx");
    expect(frescuraClavada(mods, RAIZ, marcos, arbol)).toEqual([]);
  });

  it("sigue la propiedad por SU nombre, no por el literal `staleSince`", () => {
    // [T-2.82.a] El panel del quórum pinta DOS datos distintos —el incidente en
    // la rama `absent`, el evento en la otra— y por tanto recibe DOS edades, que
    // no pueden llamarse las dos `staleSince`. Buscando en el sitio de montaje un
    // atributo llamado literalmente `staleSince`, el censo denunciaba como
    // «prop-sin-cablear» a un panel PERFECTAMENTE cableado: un falso positivo
    // que empuja a renombrar la prop para contentar al analizador, que es
    // gobernar por el test en vez de por el código.
    const { mods, marcos } = analizar({
      "/censo/Pagina.tsx": `
        import Hijo from "./Hijo";
        export default function Pagina({ q }) { return <Hijo edadDelEvento={q.staleSince} />; }`,
      "/censo/Hijo.tsx": `
        import StateFrame from "./StateFrame";
        export default function Hijo({ edadDelEvento }) {
          return <StateFrame label="B" loading={false} error={null} empty={false} staleSince={edadDelEvento}><p>b</p></StateFrame>;
        }`,
    });
    const arbol = arbolDeLaPagina(mods, RAIZ, "Pagina.tsx");
    expect(frescuraClavada(mods, RAIZ, marcos, arbol)).toEqual([]);
  });

  it("…y sigue delatando a esa MISMA prop cuando la montan con `null`", () => {
    // La otra mitad: seguir el nombre no puede convertirse en dejar de mirar.
    const { mods, marcos } = analizar({
      "/censo/Pagina.tsx": `
        import Hijo from "./Hijo";
        export default function Pagina() { return <Hijo edadDelEvento={null} />; }`,
      "/censo/Hijo.tsx": `
        import StateFrame from "./StateFrame";
        export default function Hijo({ edadDelEvento }) {
          return <StateFrame label="B" loading={false} error={null} empty={false} staleSince={edadDelEvento}><p>b</p></StateFrame>;
        }`,
    });
    const arbol = arbolDeLaPagina(mods, RAIZ, "Pagina.tsx");
    const medido = frescuraClavada(mods, RAIZ, marcos, arbol);
    expect(medido.map((f) => `${f.clave} · ${f.motivo}`)).toEqual([
      "Hijo.tsx#B · prop-sin-cablear",
    ]);
    expect(medido[0].detalle).toContain("edadDelEvento");
  });

  it("un `<StateFrame>` que NO declara `staleSince` también cuenta", () => {
    // El silencio es la mentira: sin la entrada, el marco afirma «este dato no
    // puede envejecer» sin decirlo.
    const { mods, marcos } = analizar({
      "/censo/Pagina.tsx": `
        import StateFrame from "./StateFrame";
        export default function Pagina() {
          return <StateFrame label="A" loading={false} error={null} empty={false}><p>a</p></StateFrame>;
        }`,
    });
    const arbol = arbolDeLaPagina(mods, RAIZ, "Pagina.tsx");
    expect(frescuraClavada(mods, RAIZ, marcos, arbol).map((f) => f.motivo)).toEqual(["ausente"]);
  });
});
