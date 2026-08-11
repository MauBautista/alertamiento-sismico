// UBICACIÓN: fuera de `src/app/` a propósito (ver `onboarding/guard.test.tsx`:
// `expo-router` barre los `*.test.tsx` que haya bajo `src/app` y la app no
// arranca).
//
// [T-2.108] La pantalla 2.5 es la que existe para dar CONFIANZA sobre la cola,
// y era la única del stack que no cumplía el contrato de 4 estados (regla de
// oro 7): no tenía `error` ni `stale`. Si abrir la base local cifrada fallaba,
// `hydrated` se quedaba en false para siempre y la pantalla decía "Cargando su
// cola local cifrada…" indefinidamente — un spinner eterno delante de alguien
// que necesita saber si su reporte de daños está a salvo.
//
// Aquí se asserta el TEXTO que la persona lee, no el estado interno.
import { act, render, waitFor } from "@testing-library/react-native";

import {
  configureQueuePersistence,
  resetQueueStoreForTests,
  useQueueStore,
} from "@/offline/queue.store";
import { MemoryQueuePersistence } from "@/offline/store";
import type { QueuePersistence } from "@/offline/store";

import Sync from "@/app/(brigadista)/sync";

jest.mock("expo-crypto", () => {
  let n = 0;
  return {
    CryptoDigestAlgorithm: { SHA256: "SHA-256" },
    digestStringAsync: jest.fn(async (_alg: string, data: string) => `json-${data.length}`),
    randomUUID: jest.fn(() => `uuid-${++n}`),
    getRandomBytesAsync: jest.fn(async () => new Uint8Array(32)),
  };
});

jest.mock("@takab/sdk", () => ({
  submitCheckinIncidentsIncidentIdCheckinsPost: jest.fn(),
  registerEvidenceIncidentsIncidentIdEvidencePost: jest.fn(),
  submitDamageReportIncidentsIncidentIdDamageReportsPost: jest.fn(),
}));

let mockOnline = true;
jest.mock("expo-network", () => ({
  getNetworkStateAsync: jest.fn(async () => ({ isConnected: mockOnline })),
  addNetworkStateListener: jest.fn(() => ({ remove: jest.fn() })),
}));

const CHECKIN = {
  incident_id: "inc-1",
  status: "safe" as const,
  zone_id: "z-1",
  location: null,
  ts_device: "2026-08-10T00:00:00Z",
};

/** Una persistencia que NO abre: disco lleno, SQLCipher ausente, base corrupta. */
class PersistenciaRota implements QueuePersistence {
  async init(): Promise<void> {
    throw new Error("database is locked");
  }
  async all() {
    return [];
  }
  async upsert() {}
  async remove() {}
  encryption() {
    return { active: false, cipher: null };
  }
}

beforeEach(() => {
  mockOnline = true;
  resetQueueStoreForTests();
});

describe("2.5 · contrato de 4 estados (regla de oro 7)", () => {
  it("CARGANDO: mientras la cola local no abre no se pintan contadores en cero", async () => {
    // La lección de T-2.58/59: una tira de KPI fuera del StateFrame pinta
    // ceros que se leen como "no hay nada pendiente".
    configureQueuePersistence(new MemoryQueuePersistence());
    const v = await render(<Sync />);

    expect(v.getByTestId("state-loading")).toBeTruthy();
    expect(v.queryByText("PENDIENTES")).toBeNull();
    expect(v.queryByText(/PENDIENTE\(S\)/)).toBeNull();
  });

  it("ERROR: si la cola local NO abre, se dice — jamás un spinner eterno", async () => {
    configureQueuePersistence(new PersistenciaRota());
    await act(async () => {
      await useQueueStore.getState().hydrate();
    });

    const v = await render(<Sync />);

    expect(v.getByTestId("state-error")).toBeTruthy();
    expect(v.getByTestId("state-error")).toHaveTextContent(/No se pudo abrir su cola local/);
    expect(v.getByTestId("state-error")).toHaveTextContent(/database is locked/);
    expect(v.queryByTestId("state-loading")).toBeNull();
    // Y NO se afirma que no hay nada pendiente: no se sabe.
    expect(v.queryByText("PENDIENTES")).toBeNull();
  });

  it("VACÍO: cola abierta y sin nada dentro — ese sí es el vacío honesto", async () => {
    configureQueuePersistence(new MemoryQueuePersistence());
    await act(async () => {
      await useQueueStore.getState().hydrate();
    });

    const v = await render(<Sync />);

    expect(v.getByTestId("state-empty")).toBeTruthy();
    expect(v.getByText(/Nada por sincronizar/)).toBeTruthy();
    expect(v.queryByTestId("state-error")).toBeNull();
  });

  it("RETENIDO: sin red y con algo en la cola, se dice desde cuándo", async () => {
    mockOnline = false;
    configureQueuePersistence(new MemoryQueuePersistence());
    await act(async () => {
      await useQueueStore.getState().hydrate();
      await useQueueStore.getState().enqueueCheckin(CHECKIN);
    });

    const v = await render(<Sync />);

    await waitFor(() => expect(v.getByTestId("state-stale")).toBeTruthy());
    expect(v.getByTestId("state-stale")).toHaveTextContent(/DATOS RETENIDOS/);
    // El contenido sigue visible: "retenido" no es "no hay nada".
    expect(v.getByText("Check-in de vida")).toBeTruthy();
  });

  it("con red y cola llena NO se pinta el banner de retenidos (no sería cierto)", async () => {
    configureQueuePersistence(new MemoryQueuePersistence());
    await act(async () => {
      await useQueueStore.getState().hydrate();
      await useQueueStore.getState().enqueueCheckin(CHECKIN);
    });

    const v = await render(<Sync />);

    await waitFor(() => expect(v.getByText("Check-in de vida")).toBeTruthy());
    expect(v.queryByTestId("state-stale")).toBeNull();
  });
});

describe("2.5 · el banner offline dice la VERDAD de lo que la cola guarda", () => {
  it("nombra fotos forenses, reportes de daños y check-ins — los tres tipos que admite", async () => {
    // Este es el defecto de T-2.108 en una frase: el banner prometía "sus
    // capturas y reportes" cuando la cola solo aceptaba check-ins.
    mockOnline = false;
    configureQueuePersistence(new MemoryQueuePersistence());
    await act(async () => {
      await useQueueStore.getState().hydrate();
    });

    const v = await render(<Sync />);

    await waitFor(() => expect(v.getByTestId("offline-banner")).toBeTruthy());
    const banner = v.getByTestId("offline-banner");
    expect(banner).toHaveTextContent(/fotos forenses/);
    expect(banner).toHaveTextContent(/reportes de daños/);
    expect(banner).toHaveTextContent(/check-ins/);
    expect(banner).toHaveTextContent(/se enviarán automáticamente al recuperar la red/);
  });

  it("con red no hay banner offline", async () => {
    configureQueuePersistence(new MemoryQueuePersistence());
    await act(async () => {
      await useQueueStore.getState().hydrate();
    });

    const v = await render(<Sync />);

    await waitFor(() => expect(v.getByTestId("state-empty")).toBeTruthy());
    expect(v.queryByTestId("offline-banner")).toBeNull();
  });
});
