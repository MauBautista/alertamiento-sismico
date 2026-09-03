// UBICACIÓN: fuera de `src/app/` a propósito — `expo-router` barre TODO lo que
// hay bajo `src/app` con un `require.context`, los `*.test.tsx` incluidos, y la
// app deja de compilar. Misma nota que `crisis-states.test.tsx`.
//
// [T-2.118] `triage.tsx` tenía el MARCO desde T-2.108 pero no la PRUEBA: el
// censo de T-2.111 lo midió y lo dejó por escrito. Tener las cuatro entradas
// cableadas en el marcado no demuestra que la pantalla las ALCANCE — un
// `loading` que nunca se resuelve sigue cableado igual de bien.
//
// Lo que aquí se mide es el texto que lee el táctico, y la distinción que más
// cuesta: «no hay incidente» (vacío honesto) NO es «no pudimos preguntar».
import type { MobileStateOut } from "@takab/sdk";
import { act, render } from "@testing-library/react-native";

import { expectFourStates } from "@/test-utils/expectFourStates";

import Triage from "@/app/(brigadista)/triage";

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

let mockSitio: string | null = SITE;
jest.mock("@/services/mySite", () => ({
  useWatchedSiteId: () => mockSitio,
}));

type Snapshot = ReturnType<typeof instantanea>;
let mockSnapshot: Snapshot;
jest.mock("@/features/alert/useAlertState", () => ({
  useAlertState: () => mockSnapshot,
}));

// La cola es una escritura LOCAL y su desenlace lo prueba `queue.test.ts`;
// aquí sólo estorbaría con `expo-sqlite`.
jest.mock("@/offline/queue.store", () => ({
  useQueueStore: Object.assign(jest.fn(), {
    getState: () => ({ enqueueDamageReport: jest.fn(async () => ({ id: "q-1" })) }),
  }),
}));
jest.mock("@/offline/sync", () => ({ drainQueue: jest.fn(async () => undefined) }));

// ------------------------------------------------------------------ datos

function estado(): MobileStateOut {
  return {
    site_id: SITE,
    site_name: "Torre Reforma",
    server_ts: new Date(AHORA).toISOString(),
    phase: "checkin_pending",
    incident: {
      incident_id: "inc-1",
      opened_at: new Date(AHORA - 600_000).toISOString(),
      trigger: "sasmex",
      max_pga_g: 0.152,
      node_count: null,
    },
    latest_tier: "evacuate_or_hold",
    my_zone: { zone_id: "z-1", name: "Piso 12", evac_policy: "evacuate" },
    reentry: { blocked: true, dictamen_status: null, dictamen_signed: false },
    assembly_point: null,
    compliance_labels: {},
    drill: { active: false, last_note: null, last_started_at: null, next_scheduled_at: null },
  } as unknown as MobileStateOut;
}

function instantanea(over: Record<string, unknown> = {}) {
  return {
    state: null as string | null,
    data: null as MobileStateOut | null,
    hasOwnCheckin: false,
    refetch: jest.fn(),
    dataUpdatedAt: 0,
    loading: false,
    error: null as string | null,
    // [T-5.21] `stale: boolean` → `staleSinceMs`: la frescura es un INSTANTE.
    staleSinceMs: null,
    ...over,
  };
}

beforeEach(() => {
  mockSitio = SITE;
  mockSnapshot = instantanea();
});

async function asentar(): Promise<void> {
  await act(async () => {});
}

// ------------------------------------------------------------------ tests

describe("2.4 · triage · el vacío honesto no tapa el fallo", () => {
  it("sin incidente DICE que no hay nada que levantar, sin formulario", async () => {
    mockSnapshot = instantanea({ data: estado(), state: "idle" });
    mockSnapshot.data = { ...estado(), incident: null } as unknown as MobileStateOut;

    const v = await render(<Triage />);
    await asentar();

    expect(v.getByTestId("state-empty")).toBeTruthy();
    expect(v.getByTestId("state-empty")).toHaveTextContent(/Sin incidente activo en su sitio/);
    expect(v.queryByTestId("state-error")).toBeNull();
  });

  it("si `mobile-state` falla, el error GANA al vacío — no se afirma que no hay incidente", async () => {
    // Es el defecto que T-2.111 cazó en `lista.tsx`: una frase tranquilizadora
    // tapando un fallo. Aquí se mide que no vuelva.
    mockSnapshot = instantanea({ error: "No se pudo consultar el estado del sitio." });

    const v = await render(<Triage />);
    await asentar();

    expect(v.getByTestId("state-error")).toBeTruthy();
    expect(v.getByTestId("state-error")).toHaveTextContent(
      /No se pudo consultar el estado del sitio/,
    );
    expect(v.queryByText(/Sin incidente activo en su sitio/)).toBeNull();
  });

  it("con dato VIEJO el formulario sigue disponible, bajo el banner de retenidos", async () => {
    // Levantar daños es una escritura LOCAL: que el snapshot esté viejo no
    // puede bloquear al táctico que ya está frente al muro agrietado.
    mockSnapshot = instantanea({
      data: estado(),
      // [T-5.21] Viejo de verdad: el instante ES la frescura.
      staleSinceMs: AHORA - 4 * 60_000,
      dataUpdatedAt: AHORA - 4 * 60_000,
    });

    const v = await render(<Triage />);
    await asentar();

    expect(v.getByTestId("state-stale")).toBeTruthy();
    expect(v.getByTestId("state-stale")).toHaveTextContent(/DATOS RETENIDOS/);
    expect(v.queryByTestId("state-empty")).toBeNull();
  });
});

describe("2.4 · triage · contrato de 4 estados (regla de oro 7)", () => {
  it("materializa los cuatro", async () => {
    await expectFourStates(
      (e) => {
        mockSitio = SITE;
        mockSnapshot = instantanea({
          loading: e === "loading",
          error: e === "error" ? "No se pudo consultar el estado del sitio." : null,
          data: e === "stale" ? estado() : null,
          // [T-5.21] La frescura es un INSTANTE, y sale del mismo `dataUpdatedAt`
          // que el fixture declara: así no puede decir «viejo» y «fresco» a la vez.
          staleSinceMs: e === "stale" ? AHORA - 60_000 : null,
          dataUpdatedAt: e === "stale" ? AHORA - 60_000 : 0,
        });
        return <Triage />;
      },
      { asentar },
    );
  });
});
