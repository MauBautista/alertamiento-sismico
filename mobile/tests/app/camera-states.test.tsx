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
import { act, fireEvent, render, type RenderResult } from "@testing-library/react-native";

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

jest.mock("expo-router", () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), back: jest.fn() }),
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

jest.mock("@/features/forensic/capture", () => ({
  captureForensicPhoto: jest.fn(async () => ({ uri: "file:///x.jpg", sha256: "h", bytes: 10 })),
}));
jest.mock("@/features/damage/draft.store", () => ({
  useDamageDraft: (sel: (s: { addEvidence: () => void }) => unknown) =>
    sel({ addEvidence: jest.fn() }),
}));
jest.mock("@/offline/queue.store", () => ({
  useQueueStore: Object.assign(jest.fn(), {
    getState: () => ({ enqueueEvidence: jest.fn(async () => ({ id: "q-1" })) }),
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
