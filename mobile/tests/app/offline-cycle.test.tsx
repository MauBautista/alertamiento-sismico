// UBICACIÓN: fuera de `src/app/` a propósito — `expo-router` barre TODO lo que
// hay en `src/app` con un `require.context`, los `*.test.tsx` incluidos, y la
// app deja de arrancar. (Misma nota que `tests/app/onboarding/guard.test.tsx`.)
//
// [T-2.108] EL CICLO COMPLETO DE LA SPEC §7 · 2.5:
//     avión → captura → formulario → red → sync automática SIN INTERVENCIÓN.
//
// Este fichero existe porque la pantalla de sincronización prometía —en un
// banner, con todas sus letras— que «sus capturas y reportes se guardan
// localmente y se enviarán automáticamente al recuperar la red», y la cola
// SOLO admitía check-ins: la cámara forense y el formulario de daños hacían
// POST directo. Sin red, la foto forense y el reporte de daños se PERDÍAN, y
// la única pantalla que existe para dar confianza sobre la cola era la que
// mentía sobre su contenido (regla de oro 7).
//
// Se moquean SOLO las fronteras nativas (cámara, view-shot, sistema de
// ficheros, cripto, red, router) y el HTTP del SDK. La cola, el motor de
// sincronización, la captura forense y las tres pantallas corren DE VERDAD:
// ahí vivía el fallo.
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";

import { drainQueue } from "@/offline/sync";
import {
  configureQueuePersistence,
  resetQueueStoreForTests,
  useQueueStore,
} from "@/offline/queue.store";
import { MemoryQueuePersistence } from "@/offline/store";
import { useDamageDraft } from "@/features/damage/draft.store";

import { OfflineSyncGate } from "@/offline/OfflineSyncGate";

import Camera from "@/app/camera";
import Sync from "@/app/(brigadista)/sync";
import Triage from "@/app/(brigadista)/triage";

// ─── Sistema de ficheros en memoria ──────────────────────────────────────────
// La captura forense corre de verdad contra este FS: es donde se comprueba que
// el fichero que se encola es EL MISMO que se subirá (integridad SHA-256).
const mockFs = new Map<string, Uint8Array>();

jest.mock("expo-file-system", () => {
  class Dir {
    uri: string;
    constructor(...parts: unknown[]) {
      this.uri = parts.map(String).join("/");
    }
    get exists() {
      return true;
    }
    create() {}
  }
  class F {
    uri: string;
    constructor(a: unknown, b?: unknown) {
      const base = typeof a === "string" ? a : (a as { uri: string }).uri;
      this.uri = b === undefined ? base : `${base}/${String(b)}`;
    }
    get exists() {
      return mockFsRef.has(this.uri);
    }
    get size() {
      return mockFsRef.get(this.uri)?.length ?? 0;
    }
    delete() {
      mockFsRef.delete(this.uri);
    }
    move(dest: { uri: string }) {
      const bytes = mockFsRef.get(this.uri);
      if (bytes) {
        mockFsRef.set(dest.uri, bytes);
        mockFsRef.delete(this.uri);
      }
      this.uri = dest.uri;
    }
    async bytes() {
      const b = mockFsRef.get(this.uri);
      if (!b) {
        throw new Error(`ENOENT ${this.uri}`);
      }
      return b;
    }
  }
  return { Directory: Dir, File: F, Paths: { document: "file:///doc" } };
});
// `jest.mock` se iza: la fábrica no puede cerrar sobre `mockFs` por nombre
// directo antes de su declaración, pero sí a través de esta referencia.
const mockFsRef = mockFs;

jest.mock("react-native-view-shot", () => ({
  captureRef: jest.fn(async () => {
    mockFsRef.set("file:///cache/shot.jpg", new Uint8Array([9, 8, 7, 6, 5]));
    return "file:///cache/shot.jpg";
  }),
}));

jest.mock("expo-crypto", () => {
  let n = 0;
  return {
    CryptoDigestAlgorithm: { SHA256: "SHA-256" },
    // Hash de TEXTO (payloads canónicos de la cadena de custodia).
    digestStringAsync: jest.fn(async (_alg: string, data: string) => `json-${data.length}`),
    // Hash de BYTES: determinista y sensible al contenido — alterar un byte
    // cambia la huella, que es justo lo que la §2.3 exige poder demostrar.
    digest: jest.fn(async (_alg: string, data: Uint8Array) =>
      Uint8Array.from([data.length, ...Array.from(data).slice(0, 4)]),
    ),
    randomUUID: jest.fn(() => `uuid-${++n}`),
    getRandomBytesAsync: jest.fn(async () => new Uint8Array(32)),
  };
});

// ─── Cámara ──────────────────────────────────────────────────────────────────
jest.mock("expo-camera", () => {
  const React = jest.requireActual("react") as typeof import("react");
  const RN = jest.requireActual("react-native") as typeof import("react-native");
  const CameraView = React.forwardRef((props: Record<string, unknown>, ref) => {
    React.useImperativeHandle(ref, () => ({
      takePictureAsync: async () => ({ uri: "file:///cache/raw.jpg" }),
    }));
    return React.createElement(RN.View, props);
  });
  CameraView.displayName = "CameraView";
  return {
    CameraView,
    useCameraPermissions: () => [{ granted: true }, jest.fn()],
  };
});

// ─── Red ─────────────────────────────────────────────────────────────────────
let mockOnline = false;
const mockNetListeners: ((s: { isConnected: boolean }) => void)[] = [];
jest.mock("expo-network", () => ({
  getNetworkStateAsync: jest.fn(async () => ({ isConnected: mockOnline })),
  addNetworkStateListener: jest.fn((cb: (s: { isConnected: boolean }) => void) => {
    mockNetListeners.push(cb);
    return { remove: jest.fn() };
  }),
}));

const mockRouter = { push: jest.fn(), replace: jest.fn(), back: jest.fn() };
jest.mock("expo-router", () => ({ useRouter: () => mockRouter }));

jest.mock("@/auth/session.store", () => ({
  useSessionStore: (sel: (s: unknown) => unknown) => sel({ me: { sub: "op-1" }, status: "authenticated" }),
}));

jest.mock("@/services/mySite", () => ({ useWatchedSiteId: () => "site-1" }));

jest.mock("@/features/alert/useAlertState", () => ({
  useAlertState: () => ({
    data: { incident: { incident_id: "inc-1", max_pga_g: 0.12 }, my_zone: { zone_id: "z-1" } },
    loading: false,
    error: null,
    stale: false,
    dataUpdatedAt: 0,
  }),
}));

// ─── Frontera HTTP ───────────────────────────────────────────────────────────
const mockRegisterEvidence = jest.fn();
const mockSubmitDamage = jest.fn();
const mockSubmitCheckin = jest.fn();
jest.mock("@takab/sdk", () => ({
  registerEvidenceIncidentsIncidentIdEvidencePost: (...a: unknown[]) => mockRegisterEvidence(...a),
  submitDamageReportIncidentsIncidentIdDamageReportsPost: (...a: unknown[]) => mockSubmitDamage(...a),
  submitCheckinIncidentsIncidentIdCheckinsPost: (...a: unknown[]) => mockSubmitCheckin(...a),
}));

const fetchMock = jest.fn();

beforeEach(async () => {
  mockFs.clear();
  mockNetListeners.length = 0;
  mockOnline = false;
  jest.clearAllMocks();
  (globalThis as { fetch: unknown }).fetch = fetchMock;
  resetQueueStoreForTests();
  configureQueuePersistence(new MemoryQueuePersistence());
  await useQueueStore.getState().hydrate();
  useDamageDraft.getState().reset();
});

/** Modo avión: cualquier llamada de red MUERE como muere `fetch` sin red. */
function sinRed(): void {
  const boom = () => Promise.reject(new TypeError("Network request failed"));
  mockRegisterEvidence.mockImplementation(boom);
  mockSubmitDamage.mockImplementation(boom);
  fetchMock.mockImplementation(boom);
}

/** Vuelve la red: el registro firma un PUT y el reporte aterriza. */
function conRed(): void {
  mockRegisterEvidence.mockResolvedValue({
    data: { evidence_id: "ev-servidor-1", upload_url: "https://s3/put?sig" },
    response: { status: 201 },
  });
  fetchMock.mockResolvedValue({ ok: true, status: 200 });
  mockSubmitDamage.mockResolvedValue({
    data: { report_id: "rep-1" },
    response: { status: 201 },
  });
}

/** La cámara y el formulario disparan `void drainQueue()` al encolar (es lo
 *  que hace que el ciclo sea "sin intervención"). Ese drenaje sigue vivo tras
 *  el `await` de la pantalla, y el motor tiene un candado de una pasada: sin
 *  esperar aquí, el drenaje del propio test saldría de vacío. */
async function colaEnReposo() {
  await waitFor(() =>
    expect(useQueueStore.getState().items.some((i) => i.state === "uploading")).toBe(false),
  );
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

async function capturarFoto() {
  const v = await render(<Camera />);
  await fireEvent.press(v.getByText("CAPTURAR"));
  await waitFor(() => expect(v.getByText("USAR ESTA FOTO")).toBeTruthy());
  await fireEvent.press(v.getByText("USAR ESTA FOTO"));
  await waitFor(() => expect(mockRouter.back).toHaveBeenCalled());
  await colaEnReposo();
  await v.unmount();
}

async function llenarReporte() {
  const v = await render(<Triage />);
  await fireEvent.press(v.getByTestId("cat-people_trapped").children[0] as never);
  await fireEvent.press(v.getByTestId("submit-damage"));
  await waitFor(() =>
    expect(useQueueStore.getState().items.some((i) => i.kind === "damage_report")).toBe(true),
  );
  await colaEnReposo();
  return v;
}

describe("[T-2.108] avión → captura → formulario → red → sync automática", () => {
  it("EN AVIÓN la foto forense y el reporte QUEDAN EN LA COLA, no se pierden", async () => {
    sinRed();

    await capturarFoto();
    await llenarReporte();

    const items = useQueueStore.getState().items;
    expect(items.map((i) => i.kind).sort()).toEqual(["damage_report", "evidence"]);
    expect(items.every((i) => i.state === "pending")).toBe(true);

    // Sin red NO se intentó ningún POST directo: el dato está a salvo en disco.
    expect(mockSubmitDamage).not.toHaveBeenCalled();
  });

  it("la pantalla de sincronización NOMBRA lo que de verdad hay en la cola", async () => {
    sinRed();
    await capturarFoto();
    await llenarReporte();

    const v = await render(<Sync />);
    await waitFor(() => expect(v.getByText(/Foto forense/)).toBeTruthy());
    expect(v.getByText(/Reporte de daños/)).toBeTruthy();
    expect(v.getAllByText("PENDIENTE").length).toBe(2);
    expect(v.getByText(/2 PENDIENTE\(S\)/)).toBeTruthy();
  });

  it("vuelve la red ⇒ se despachan SOLOS, con el enlace forense intacto", async () => {
    sinRed();
    await capturarFoto();
    await llenarReporte();
    const capturado = useQueueStore.getState().items.find((i) => i.kind === "evidence");
    mockRegisterEvidence.mockClear();

    conRed();
    mockOnline = true;
    // +1 min: el intento fallido en avión dejó a la foto con su backoff, así
    // que el drenaje que la recoge es uno POSTERIOR (el tic de 15 s de
    // `OfflineSyncGate` o el aviso de red) — nadie toca nada.
    await act(async () => {
      await drainQueue(Date.now() + 60_000);
    });

    // La foto viajó con la huella sellada AL CAPTURAR, sin recalcularla…
    expect(mockRegisterEvidence).toHaveBeenCalledTimes(1);
    expect(mockRegisterEvidence.mock.calls[0][0].body.sha256).toBe(capturado?.sha256);

    // …y el reporte se ligó al evidence_id REAL que devolvió el servidor.
    expect(mockSubmitDamage).toHaveBeenCalledTimes(1);
    expect(mockSubmitDamage.mock.calls[0][0].body.evidence_ids).toEqual(["ev-servidor-1"]);
    expect(mockSubmitDamage.mock.calls[0][0].body.categories).toEqual([
      { key: "people_trapped", severity: "medium" },
    ]);

    expect(useQueueStore.getState().items.every((i) => i.state === "synced")).toBe(true);
  });

  it("SIN INTERVENCIÓN: basta con que vuelva la red, nadie pulsa nada", async () => {
    // El criterio de aceptación de §7·2.5 dice "sync automática sin
    // intervención". Quien lo cumple es el listener de red de
    // `OfflineSyncGate`: aquí no se llama a `drainQueue` ni se pulsa un botón.
    conRed();
    const foto = await useQueueStore.getState().enqueueEvidence(
      {
        incident_id: "inc-1",
        uri: "file:///doc/forensic/evidence-x.jpg",
        content_type: "image/jpeg",
        bytes: 5,
        ts_device: "2026-08-10T00:00:00Z",
      },
      "da-igual-el-valor",
    );
    mockFs.set("file:///doc/forensic/evidence-x.jpg", new Uint8Array([9, 8, 7, 6, 5]));
    await useQueueStore.getState().enqueueDamageReport(
      {
        incident_id: "inc-1",
        categories: [{ key: "structural", severity: "high" }],
        notes: null,
        zone_id: "z-1",
        evidence_refs: [foto.id],
        ts_device: "2026-08-10T00:00:00Z",
      },
      0,
    );
    // La huella tiene que ser la del fichero, o la comprobación de integridad
    // lo rechaza: se sella igual que en captura.
    await useQueueStore
      .getState()
      .apply({ ...useQueueStore.getState().items[0], sha256: "0509080706" });

    await render(<OfflineSyncGate />);
    await act(async () => {
      mockNetListeners.forEach((cb) => cb({ isConnected: true }));
    });

    await waitFor(() =>
      expect(useQueueStore.getState().items.every((i) => i.state === "synced")).toBe(true),
    );
    expect(mockSubmitDamage.mock.calls[0][0].body.evidence_ids).toEqual(["ev-servidor-1"]);
  });

  it("el reporte con PERSONAS ATRAPADAS se despacha antes que lo demás", async () => {
    sinRed();
    // Un check-in cualquiera, encolado ANTES que el reporte urgente.
    await useQueueStore.getState().enqueueCheckin({
      incident_id: "inc-1",
      status: "safe",
      zone_id: "z-1",
      location: null,
      ts_device: "2026-08-10T00:00:00Z",
    });
    await llenarReporte();

    conRed();
    const orden: string[] = [];
    mockSubmitCheckin.mockImplementation(async () => {
      orden.push("checkin");
      return { data: { ok: true }, response: { status: 201 } };
    });
    mockSubmitDamage.mockImplementation(async () => {
      orden.push("damage_report");
      return { data: { report_id: "r" }, response: { status: 201 } };
    });

    await act(async () => {
      await drainQueue(Date.now() + 60_000);
    });

    expect(orden).toEqual(["damage_report", "checkin"]);
  });
});
