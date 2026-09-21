// UBICACIÓN: fuera de `src/app/` a propósito (ver `crisis-states.test.tsx`).
//
// [T-2.118] LA CÁMARA FORENSE NO PRESENTA EL DATO DEL SERVIDOR: LO SELLA.
//
// De las 11 rutas con dato de servidor, ésta es la única cuyo dato no se pinta.
// `camera.tsx` lee `mobile-state` para tomar `incident_id` y `max_pga_g` y
// HORNEARLOS en la marca de agua de una foto de evidencia. Por eso el defecto
// aquí es de otra especie: un número viejo en pantalla se corrige al refrescar;
// un número viejo horneado en el pixel entra en la cadena de custodia con una
// atribución que no corresponde, y ya no se corrige nunca.
//
// LA DECISIÓN (la razón larga vive en `src/app/camera.tsx`):
//   1. NO se deja de sellar. La evidencia es perecedera —el muro se apuntala,
//      el escombro se retira, el edificio se entrega— y la falta de red es
//      justo el escenario para el que existe esta cámara (T-2.108 movió la
//      subida a la cola offline precisamente por eso). Negarse a capturar
//      convierte un problema de ETIQUETA en una pérdida TOTAL.
//   2. Se sella DECLARANDO la edad, y se declara en el pixel: es el único
//      lugar del que el aviso no se puede separar después, porque entra en el
//      SHA-256 junto con la imagen.
//   3. Se le dice a la persona ANTES de disparar, no después: el banner de
//      retenidos va sobre el visor.
//   4. Sin snapshot NINGUNO no se sella: no habría a qué incidente atribuir la
//      foto. Y se dice que no se pudo preguntar — que no es lo mismo que «no
//      hay incidente», el embuste que T-2.111 cazó en `lista.tsx` y que esta
//      pantalla cometía con la frase «Sin incidente activo».
import type { MobileStateOut } from "@takab/sdk";
import {
  act,
  fireEvent,
  render,
  within,
  type RenderResult,
} from "@testing-library/react-native";
import type { TestInstance } from "test-renderer";

import { expectFourStates } from "@/test-utils/expectFourStates";
import { watermarkLines } from "@/features/forensic/watermark";

import Camera from "@/app/camera";

const SITE = "11111111-1111-1111-1111-111111111111";
// [T-5.21] El «ahora» del fixture es RELATIVO al reloj de verdad. Era un epoch
// clavado en 2027, y desde que la frescura sale del reloj —y no de que la
// consulta falle— un `dataUpdatedAt` en el futuro sale «fresco» y el estado
// `stale` no se materializaba. Contar hacia atrás desde `Date.now()` hace que
// «hace tres minutos» signifique de verdad hace tres minutos.
const AHORA = Date.now();

// ------------------------------------------------------------------ mocks

const mockBack = jest.fn();
jest.mock("expo-router", () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), back: mockBack }),
}));

jest.mock("expo-crypto", () => ({ randomUUID: () => "ev-1" }));

let mockPermiso: { granted: boolean } | null = { granted: true };
jest.mock("expo-camera", () => {
  // [T-2.125] `requireActual` y no `require()`: dentro de una factoría de
  // `jest.mock` no se puede importar arriba (se hoistea), pero sí se puede pedir
  // el módulo REAL — que aquí es además la misma instancia, porque ni
  // `react-native` ni `react` están moqueados.
  const { View } = jest.requireActual("react-native") as typeof import("react-native");
  const React = jest.requireActual("react") as typeof import("react");
  // `forwardRef` + `useImperativeHandle` para que `cameraRef.current` exista:
  // sin eso el disparador no llega nunca a la vista de revisión, que es
  // justamente la que view-shot hornea.
  // El `ref` va tipado desde que `React` dejó de entrar como `any` por un
  // `require()` sin tipos (T-2.125): `unknown` ya no cuela en `useImperativeHandle`.
  function Visor(_p: unknown, ref: import("react").Ref<unknown>) {
    React.useImperativeHandle(ref, () => ({
      takePictureAsync: async () => ({ uri: "file:///shot.jpg" }),
    }));
    return <View testID="camera-view" />;
  }
  return {
    CameraView: React.forwardRef(Visor),
    useCameraPermissions: () => [mockPermiso, jest.fn()],
  };
});

let mockSitio: string | null = SITE;
jest.mock("@/services/mySite", () => ({
  useWatchedSiteId: () => mockSitio,
}));

type Snapshot = ReturnType<typeof instantanea>;
let mockSnapshot: Snapshot;
jest.mock("@/features/alert/useAlertState", () => ({
  useAlertState: () => mockSnapshot,
}));

jest.mock("@/auth/session.store", () => ({
  useSessionStore: (sel: (s: { me: { sub: string } }) => unknown) => sel({ me: { sub: "op-abc12345" } }),
}));

const mockCapturar = jest.fn(async () => ({ uri: "file:///x.jpg", sha256: "h", bytes: 10 }));
jest.mock("@/features/forensic/capture", () => ({
  captureForensicPhoto: (...a: unknown[]) => mockCapturar(...(a as [])),
}));
jest.mock("@/features/damage/draft.store", () => ({
  useDamageDraft: (sel: (s: { addEvidence: () => void }) => unknown) =>
    sel({ addEvidence: jest.fn() }),
}));
const mockEncolar = jest.fn(async () => ({ id: "q-1" }));
jest.mock("@/offline/queue.store", () => ({
  useQueueStore: Object.assign(jest.fn(), {
    getState: () => ({ enqueueEvidence: mockEncolar }),
  }),
}));
jest.mock("@/offline/sync", () => ({ drainQueue: jest.fn(async () => undefined) }));

// ------------------------------------------------------------------ datos

function estado(): MobileStateOut {
  return {
    site_id: SITE,
    site_name: "Torre Reforma",
    server_ts: new Date(AHORA).toISOString(),
    phase: "shaking_concluded",
    incident: {
      incident_id: "inc-1",
      opened_at: new Date(AHORA - 900_000).toISOString(),
      trigger: "sasmex",
      max_pga_g: 0.152,
      node_count: null,
    },
    latest_tier: "evacuate_or_hold",
    my_zone: null,
    reentry: { blocked: true, dictamen_status: null, dictamen_signed: false },
    assembly_point: null,
    compliance_labels: {},
    drill: { active: false, last_note: null, last_started_at: null, next_scheduled_at: null },
    site_health: {} as never,
  } as unknown as MobileStateOut;
}

function instantanea(over: Record<string, unknown> = {}) {
  return {
    state: null as string | null,
    data: null as MobileStateOut | null,
    hasOwnCheckin: false,
    refetch: jest.fn(),
    dataUpdatedAt: AHORA,
    loading: false,
    error: null as string | null,
    // [T-5.21] `stale: boolean` → `staleSinceMs`: la frescura es un INSTANTE.
    staleSinceMs: null,
    ...over,
  };
}

beforeEach(() => {
  jest.clearAllMocks();
  mockCapturar.mockResolvedValue({ uri: "file:///x.jpg", sha256: "h", bytes: 10 });
  mockEncolar.mockResolvedValue({ id: "q-1" });
  mockPermiso = { granted: true };
  mockSitio = SITE;
  mockSnapshot = instantanea();
});

async function asentar(): Promise<void> {
  await act(async () => {});
}

/** Dispara y llega a la vista de REVISIÓN, que es la que view-shot hornea. */
async function capturar(v: RenderResult): Promise<void> {
  await act(async () => {
    fireEvent.press(v.getByTestId("shutter"));
  });
  await asentar();
}

// ------------------------------------------------------------------ tests

describe("2.3 · cámara forense · con qué se puede y con qué NO se puede sellar", () => {
  it("sin snapshot y con fallo, DICE que no pudo preguntar — no «sin incidente activo»", async () => {
    // El embuste de `lista.tsx` (T-2.111) en versión forense: afirmar que no
    // hay incidente cuando lo que pasa es que no se pudo consultar. Aquí llega
    // más lejos: si la persona se lo cree, no levanta la evidencia.
    mockSnapshot = instantanea({ error: "No se pudo consultar el estado del sitio." });

    const v = await render(<Camera />);
    await asentar();

    expect(v.getByTestId("state-error")).toBeTruthy();
    expect(v.getByTestId("state-error")).toHaveTextContent(/no se pudo consultar/i);
    // Accionable y honesto: dice qué NO se ha hecho y qué se puede hacer.
    expect(v.getByTestId("state-error")).toHaveTextContent(/no se ha perdido ninguna foto/i);
    expect(v.getByTestId("state-retry")).toBeTruthy();
    expect(v.queryByText(/Sin incidente activo/)).toBeNull();
    // Y NO se ofrece el disparador: no habría a qué incidente atribuir la foto.
    expect(v.queryByTestId("camera-view")).toBeNull();
  });

  it("el servidor RESPONDIÓ y no hay incidente: ése sí es el vacío honesto", async () => {
    mockSnapshot = instantanea({
      data: { ...estado(), incident: null } as unknown as MobileStateOut,
    });

    const v = await render(<Camera />);
    await asentar();

    expect(v.getByTestId("state-empty")).toHaveTextContent(/Sin incidente activo/);
    expect(v.queryByTestId("state-error")).toBeNull();
  });

  it("sin sitio vigilado lo dice, en vez de girar", async () => {
    mockSitio = null;

    const v = await render(<Camera />);
    await asentar();

    expect(v.getByTestId("state-empty")).toHaveTextContent(/no está vinculado a ningún edificio/i);
  });
});

describe("2.3 · cámara forense · el sello VIEJO se declara, no se calla ni se niega", () => {
  it("con snapshot retenido SE PUEDE SEGUIR CAPTURANDO (la evidencia es perecedera)", async () => {
    mockSnapshot = instantanea({
      data: estado(),
      // [T-5.21] Viejo de verdad: el instante ES la frescura.
      staleSinceMs: AHORA - 18 * 60_000,
      dataUpdatedAt: AHORA - 18 * 60_000,
    });

    const v = await render(<Camera />);
    await asentar();

    // Negarse a capturar sería perder la evidencia, no protegerla.
    expect(v.getByTestId("camera-view")).toBeTruthy();
    expect(v.getByTestId("shutter")).toBeTruthy();
  });

  it("y se AVISA antes de disparar, no después", async () => {
    mockSnapshot = instantanea({
      data: estado(),
      // [T-5.21] Viejo de verdad: el instante ES la frescura.
      staleSinceMs: AHORA - 18 * 60_000,
      dataUpdatedAt: AHORA - 18 * 60_000,
    });

    const v = await render(<Camera />);
    await asentar();

    expect(v.getByTestId("state-stale")).toHaveTextContent(/DATOS RETENIDOS/);
  });

  it("la advertencia va HORNEADA en el pixel: la lleva la marca que se captura", async () => {
    // Es el punto entero de la decisión: el aviso viaja DENTRO de la imagen y
    // entra en el SHA-256, así que no se puede separar de la evidencia. Por eso
    // se asserta sobre la marca del `composeRef` —la que view-shot hornea—, no
    // sobre un rótulo de pantalla que no viajaría con el archivo.
    mockSnapshot = instantanea({
      data: estado(),
      // [T-5.21] Viejo de verdad: el instante ES la frescura.
      staleSinceMs: AHORA - 18 * 60_000,
      dataUpdatedAt: AHORA - 18 * 60_000,
    });

    const v = await render(<Camera />);
    await asentar();
    await capturar(v);

    expect(v.getByTestId("watermark")).toHaveTextContent(/METADATOS RETENIDOS/);
    // `AHORA - 18 min` en ABSOLUTO: el exhibit se lee meses después, así que la
    // marca no puede llevar «hace 18 min». El literal se DERIVA del mismo
    // instante que el fixture: escrito a mano era `2027-01-15 07:42:00Z`, del
    // epoch clavado que esta ficha retiró, y habría vuelto a caducar solo.
    const selloEsperado = new Date(AHORA - 18 * 60_000)
      .toISOString()
      .replace("T", " ")
      .replace(/\.\d+Z$/, "Z");
    // Regex y no cadena: el matcher de RN compone el texto de varios `Text` y
    // con una cadena no encuentra la subcadena aunque esté (la versión anterior
    // de este test ya usaba regex por lo mismo).
    expect(v.getByTestId("watermark")).toHaveTextContent(
      new RegExp(`SNAPSHOT ${selloEsperado.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`),
    );
    // Y el sello completo sigue ahí: la advertencia AÑADE, no sustituye.
    expect(v.getByTestId("watermark")).toHaveTextContent(/PGA 0.152 g \(gabinete\)/);
  });

  it("con snapshot FRESCO la marca no lleva advertencia (sería falsa)", async () => {
    mockSnapshot = instantanea({ data: estado() });

    const v = await render(<Camera />);
    await asentar();
    await capturar(v);

    expect(v.queryByTestId("state-stale")).toBeNull();
    expect(v.getByTestId("watermark")).not.toHaveTextContent(/RETENIDOS/);
    expect(v.getByTestId("watermark")).toHaveTextContent(/EVIDENCIA FORENSE/);
  });

  it("la marca sigue trayendo el PGA del gabinete, no un hueco", async () => {
    // La advertencia AÑADE, no sustituye: el sello completo sigue ahí.
    expect(
      watermarkLines({
        tsDevice: new Date(AHORA).toISOString(),
        ntpOffsetMs: null,
        gps: null,
        pgaG: 0.152,
        operatorId: "op-abc12345",
        siteId: SITE,
        // [T-2.135] En el manifiesto, no en el pixel: este mismo caso lo prueba
        // más abajo `watermark.test.ts` comparando las líneas con y sin él.
        incidentId: "inc-1",
        snapshotStaleSinceMs: AHORA - 18 * 60_000,
      }).join("\n"),
    ).toMatch(/PGA 0.152 g \(gabinete\)/);
  });
});

describe("2.3 · cámara forense · contrato de 4 estados (regla de oro 7)", () => {
  it("materializa los cuatro", async () => {
    await expectFourStates(
      (e) => {
        mockPermiso = { granted: true };
        mockSitio = e === "empty" ? null : SITE;
        mockSnapshot = instantanea({
          loading: e === "loading",
          error: e === "error" ? "No se pudo consultar el estado del sitio." : null,
          data: e === "stale" ? estado() : null,
          // [T-5.21] La frescura es un INSTANTE, del mismo `dataUpdatedAt`
          // que el fixture declara: no puede decir «viejo» y «fresco» a la vez.
          staleSinceMs: e === "stale" ? AHORA - 60_000 : null,
          dataUpdatedAt: e === "stale" ? AHORA - 60_000 : AHORA,
        });
        return <Camera />;
      },
      { asentar },
    );
  });

  it("el permiso de cámara AÚN SIN RESOLVER es `loading` declarado, no un giro suelto", async () => {
    // Antes era un `ActivityIndicator` a pelo, fuera de todo marco: el mismo
    // patrón que esta ficha persigue, sólo que en la precondición del aparato.
    mockPermiso = null;

    const v = await render(<Camera />);
    await asentar();

    expect(v.getByTestId("state-loading")).toBeTruthy();
  });

  it("EXENCIÓN DECLARADA · el permiso DENEGADO no es uno de los cuatro estados", async () => {
    // Es una precondición del APARATO, no un dato de servidor, y tiene su
    // propio remedio (el botón de conceder). Meterla en el marco la dejaría sin
    // acción, que es peor. Se declara aquí para que la exención se pueda leer.
    mockPermiso = { granted: false };

    const v = await render(<Camera />);
    await asentar();

    expect(v.getByText(/necesita permiso de cámara/)).toBeTruthy();
    expect(v.queryByTestId("state-empty")).toBeNull();
    expect(v.queryByTestId("state-error")).toBeNull();
  });
});

describe("2.3 · cámara forense · [T-7.58] «USAR ESTA FOTO» no puede no hacer nada", () => {
  /** Lleva hasta el botón de confirmar, que es donde se decide si hay evidencia. */
  async function confirmar(v: RenderResult): Promise<void> {
    await act(async () => {
      fireEvent.press(v.getByTestId("use-photo"));
    });
    await asentar();
  }

  it("si la foto sellada no quedó en el disco, LO DICE y no se vuelve atrás", async () => {
    // El fallo que se midió en el Pixel el 2026-09-19: la foto se perdía al
    // moverla al directorio privado. Lo único que veía el brigadista era el
    // `ENOENT` crudo de la plataforma, y el flujo `02` se quedaba en «0 foto(s)».
    // Lo que NO puede pasar es volver a la pantalla anterior como si nada:
    // el reporte se enviaría sin la prueba del daño y nadie se enteraría.
    mockSnapshot = instantanea({ data: estado() });
    mockCapturar.mockRejectedValue(
      new Error(
        "la foto sellada no quedó en el disco tras moverla " +
          "(file:///doc/forensic/evidence-ev-1.jpg). No se ha guardado nada.",
      ),
    );

    const v = await render(<Camera />);
    await asentar();
    await capturar(v);
    await confirmar(v);

    expect(v.getByText(/No se pudo guardar la evidencia en este teléfono/)).toBeTruthy();
    // El motivo viaja hasta la pantalla (T-7.31): sin él no se distingue un
    // teléfono sin espacio de una captura que reventó.
    expect(v.getByText(/no quedó en el disco tras moverla/)).toBeTruthy();
    expect(v.getByText(/No se ha guardado nada/)).toBeTruthy();
    // Y sobre todo: ni se encola evidencia falsa ni se sale de la cámara.
    expect(mockEncolar).not.toHaveBeenCalled();
    expect(mockBack).not.toHaveBeenCalled();
  });

  it("con la foto en el disco, se encola con SU huella y entonces sí se vuelve", async () => {
    // El contraste que le da sentido al anterior: el camino sano encola el
    // PUNTERO al archivo privado con el SHA-256 sellado en la captura.
    mockSnapshot = instantanea({ data: estado() });

    const v = await render(<Camera />);
    await asentar();
    await capturar(v);
    await confirmar(v);

    expect(mockEncolar).toHaveBeenCalledTimes(1);
    const [registro, huella] = mockEncolar.mock.calls[0] as unknown as [
      Record<string, unknown>,
      string,
    ];
    expect(registro.incident_id).toBe("inc-1");
    expect(registro.uri).toBe("file:///x.jpg");
    expect(huella).toBe("h");
    expect(mockBack).toHaveBeenCalledTimes(1);
  });
});

// ===========================================================================
// [T-7.27 · D-32] LA FOTO PUEDE SALIR DEL INMUEBLE HACIA UN TERCERO
// ===========================================================================
//
// Hasta esta ficha el único aviso de esta pantalla era «METADATOS RETENIDOS»,
// que habla de la EDAD del dato con el que se sella — no de a dónde va la
// imagen. `D-32` decidió que la capa narrativa reciba las fotos del reporte de
// daños: salen del edificio hacia OpenRouter (Estados Unidos) y el proveedor
// del modelo. Quien fotografía un daño tiene que poder decidir sabiéndolo.
//
// POR QUÉ EN LOS DOS MOMENTOS, y no solo en uno:
//   · EN EL VISOR, porque encuadrar ya es una decisión: en un pasillo
//     evacuado entran caras, matrículas y papeles que nadie eligió mandar.
//   · EN LA REVISIÓN, porque «USAR ESTA FOTO» es el toque que la encola — es
//     el instante en que la imagen deja de ser sólo de este teléfono.
// El aviso del visor no cubre el segundo: entre uno y otro la persona ya ha
// disparado, y el repertorio de T-2.104 dice que lo que se lee primero manda.
describe("[T-7.27] el aviso de que la foto puede salir del inmueble", () => {
  async function conIncidente(): Promise<RenderResult> {
    mockSnapshot = instantanea({ data: estado() });
    const v = await render(<Camera />);
    await asentar();
    return v;
  }

  it("está sobre el VISOR, antes de disparar", async () => {
    const v = await conIncidente();

    expect(v.getByTestId("aviso-ia")).toHaveTextContent(/PUEDE SALIR DEL INMUEBLE/);
    expect(v.getByTestId("shutter")).toBeTruthy();
  });

  it("sigue estando en la REVISIÓN, que es el toque que la manda", async () => {
    const v = await conIncidente();
    await capturar(v);

    expect(v.getByTestId("use-photo")).toBeTruthy();
    expect(v.getByTestId("aviso-ia")).toHaveTextContent(/PUEDE SALIR DEL INMUEBLE/);
    expect(v.getByTestId("aviso-ia")).toHaveTextContent(/FUERA DE MÉXICO/);
    expect(v.getByTestId("aviso-ia")).toHaveTextContent(/NO DECIDE/);
  });

  it("convive con el de metadatos retenidos: ninguno tapa al otro", async () => {
    // Son avisos de especies distintas —uno sobre la FIABILIDAD del sello,
    // otro sobre su DESTINO— y los dos son ciertos a la vez. Sustituir uno por
    // el otro dejaría a la persona informada a medias justo en el caso peor:
    // sin red, con el dato viejo y a punto de levantar la única prueba que va
    // a existir de ese daño.
    mockSnapshot = instantanea({
      data: estado(),
      staleSinceMs: AHORA - 18 * 60_000,
      dataUpdatedAt: AHORA - 18 * 60_000,
    });

    const v = await render(<Camera />);
    await asentar();

    expect(v.getByTestId("state-stale")).toHaveTextContent(/DATOS RETENIDOS/);
    expect(v.getByTestId("aviso-ia")).toHaveTextContent(/PUEDE SALIR DEL INMUEBLE/);
  });

  it("NO se pinta cuando no hay nada que fotografiar", async () => {
    // Sin incidente no hay cámara, y un aviso sobre una transferencia que no
    // puede ocurrir es ruido que gasta la atención del aviso que sí importa.
    mockSnapshot = instantanea({
      data: { ...estado(), incident: null } as unknown as MobileStateOut,
    });

    const v = await render(<Camera />);
    await asentar();

    expect(v.queryByTestId("aviso-ia")).toBeNull();
  });
});

// ===========================================================================
// [T-7.27 · D-32] LO QUE SE HORNEA EN EL JPEG ES EL SUBÁRBOL DE `composeRef`
// ===========================================================================
//
// Este bloque existe porque el que había estaba escrito A LA ALTURA EQUIVOCADA.
// `watermark.test.ts` comprueba que el aviso de IA no aparece en
// `watermarkLines()` ni en `forensicMetadata()`, y las dos son FUNCIONES PURAS:
// nadie obliga a la pantalla a pasar por ellas para pintar algo dentro del árbol
// que view-shot captura. Medido el 2026-09-21: moviendo `<AvisoIA/>` dentro del
// `<View ref={composeRef}>` la suite entera de `mobile` quedaba en verde —725 de
// 725— con el aviso cocido en el bitmap, dentro del SHA-256 de la evidencia y
// de viaje hacia el tercero. Una guarda ausente con nombre de guarda.
//
// Y ahora pesa el doble: `T-7.26`/`T-7.27` acaban de abrir el camino por el que
// ese mismo JPEG sale del inmueble hacia OpenRouter. Lo que se hornee aquí no se
// puede quitar después —ni recortando, ni re-codificando— y viaja.
//
// LO QUE MIDE, en este orden y sin saltarse el primero:
//   1. EL ANCLA. Que el `ref` que recibe `captureForensicPhoto` es el del View
//      que lleva `testID="compose"`. Sin esto, los dos criterios de abajo
//      podrían estar midiendo un View cualquiera de la pantalla y nadie se
//      enteraría — que es exactamente el defecto que este bloque repara.
//   2. Que el aviso de IA no está DENTRO de ese árbol.
//   3. Que dentro no hay MÁS texto que el sello. Es el criterio general: la
//      spec §2.3 enumera lo que va en el pixel, y cualquier rótulo nuevo que se
//      cuele ahí cambia los bytes y, con ellos, la huella de toda la evidencia
//      futura (T-2.135). Un criterio que sólo nombrara al aviso de IA dejaría
//      pasar al siguiente aviso que a alguien le parezca buena idea hornear.
//
// ⚠️ LO QUE **NO** MIDE: aquí no corre `view-shot` ni sale un JPEG. Lo que se
// mide es el ÁRBOL que se le entrega, que es de lo que el JPEG se compone; que
// la captura nativa cueza ese árbol y no otro es cosa del teléfono, y eso sigue
// exigiendo el Pixel — está en `pendiente` con el coste de pantalla del aviso.
describe("[T-7.27] lo que se HORNEA en el JPEG: el subárbol de `composeRef`", () => {
  /** Texto de un subárbol, en orden, tal como quedaría cocido en el bitmap. */
  function textoDe(nodo: TestInstance): string {
    return within(nodo)
      .queryAllByText(/.+/)
      .map((t) => String(t.props.children))
      .join("\u241E");
  }

  /** Deja la pantalla en REVISIÓN y devuelve la vista y el `ref` que se selló. */
  async function revisarYConfirmar(): Promise<{
    v: RenderResult;
    ref: { current: { props: Record<string, unknown> } | null };
  }> {
    mockSnapshot = instantanea({ data: estado() });
    const v = await render(<Camera />);
    await asentar();
    await capturar(v);
    await act(async () => {
      fireEvent.press(v.getByTestId("use-photo"));
    });
    await asentar();
    expect(mockCapturar).toHaveBeenCalledTimes(1);
    const [ref] = mockCapturar.mock.calls[0] as unknown as [
      { current: { props: Record<string, unknown> } | null },
    ];
    return { v, ref };
  }

  it("ANCLA · el `testID` que se mide es el del View cuyo `ref` se sella", async () => {
    // Si esto falla, los dos criterios de abajo NO significan nada: estarían
    // midiendo otro View. Por eso va primero y por eso falla por su cuenta.
    const { ref } = await revisarYConfirmar();

    expect(ref.current).not.toBeNull();
    expect(ref.current?.props.testID).toBe("compose");
  });

  it("CRITERIO · el aviso de IA queda FUERA del árbol que se hornea", async () => {
    const { v } = await revisarYConfirmar();

    const cocido = v.getByTestId("compose");
    expect(within(cocido).queryByTestId("aviso-ia")).toBeNull();
    expect(textoDe(cocido)).not.toMatch(/PUEDE SALIR DEL INMUEBLE|FUERA DE MÉXICO|NO DECIDE/);
    // Y no se pone verde por desaparición: el aviso SIGUE en la pantalla, fuera.
    expect(v.getByTestId("aviso-ia")).toHaveTextContent(/PUEDE SALIR DEL INMUEBLE/);
  });

  it("CRITERIO · dentro de `composeRef` no hay más texto que el sello", async () => {
    const { v } = await revisarYConfirmar();

    const cocido = v.getByTestId("compose");
    const sello = within(cocido).getByTestId("watermark");
    // Igualdad, no inclusión: cualquier rótulo nuevo horneado rompe esto aunque
    // no diga ni «IA» ni «INMUEBLE». Y el control de que no mide el vacío: el
    // sello trae texto de verdad.
    expect(textoDe(sello)).toMatch(/EVIDENCIA FORENSE/);
    expect(textoDe(cocido)).toBe(textoDe(sello));
  });
});
