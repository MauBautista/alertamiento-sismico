// UBICACIÓN: fuera de `src/app/` a propósito (ver `crisis-states.test.tsx`).
//
// [T-2.118] El panel táctico es la pantalla que T-2.58/59 pilló pintando
// features CONGELADAS como vivas en el gabinete, y la tira de KPI de la consola
// pintando ceros con la API caída. Aquí se mide que el marco de la RUTA no deje
// pasar nada de eso: sin dato del servidor no se pinta ni una métrica.
//
// El censo de T-2.111 dejó esta ruta en la deuda anotando «varios StateFrame
// hermanos»; medido hoy, la ruta materializa UNO solo (`PanelView` es
// presentacional puro y no monta marcos), así que `expectFourStates` aplica
// directo y la nota queda corregida por medición.
import type { MobileStateOut } from "@takab/sdk";
import { act, render } from "@testing-library/react-native";

import { expectFourStates } from "@/test-utils/expectFourStates";

import Panel from "@/app/(brigadista)/panel";

const SITE = "11111111-1111-1111-1111-111111111111";
const AHORA = 1_800_000_000_000;

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

jest.mock("@/auth/session.store", () => ({
  useSessionStore: (sel: (s: { status: string; me: unknown }) => unknown) =>
    sel({
      status: "authenticated",
      me: { sub: "u-1", allowed_actions: { manual_activate: true, siren_silence: true } },
    }),
}));

// Socket mudo: el marco de la ruta lo gobierna `mobile-state`, no el live.
jest.mock("@/live/socket", () => ({
  getLiveSocket: () => ({
    status: "ready",
    connect: jest.fn(),
    close: jest.fn(),
    onStatus: () => () => undefined,
    subscribe: () => () => undefined,
  }),
}));

// La traza REST del incidente es accesoria al marco (sólo alimenta el detalle);
// su desenlace lo posee react-query. Aquí se deja muda.
jest.mock("@tanstack/react-query", () => ({
  useQuery: () => ({
    data: undefined,
    isLoading: false,
    isError: false,
    failureCount: 0,
    dataUpdatedAt: 0,
    refetch: jest.fn(),
  }),
}));

// ------------------------------------------------------------------ datos

function estado(): MobileStateOut {
  return {
    site_id: SITE,
    site_name: "Torre Reforma",
    server_ts: new Date(AHORA).toISOString(),
    phase: "idle",
    incident: null,
    latest_tier: "normal",
    my_zone: null,
    reentry: { blocked: false, dictamen_status: null, dictamen_signed: false },
    assembly_point: null,
    compliance_labels: {},
    drill: { active: false, last_note: null, last_started_at: null, next_scheduled_at: null },
    site_health: {
      status: "OPERATIVO",
      heartbeat_at: new Date(AHORA - 60_000).toISOString(),
      age_s: 60,
      has_wr1: true,
      mqtt_rtt_ms: 77,
      seedlink_lag_s: 1.2,
      ntp_offset_ms: -0.2,
      cpu_temp_c: 51.3,
      power_status: null,
      battery_pct: null,
      cert_days_remaining: 120,
    },
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
    stale: false,
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

describe("2.1 · panel · sin dato del servidor NO se pinta ni una métrica", () => {
  it("sin sitio vigilado dice qué hacer y con quién, no un panel en ceros", async () => {
    mockSitio = null;

    const v = await render(<Panel />);
    await asentar();

    expect(v.getByTestId("state-empty")).toHaveTextContent(/Sin sitio vigilado/);
    expect(v.getByTestId("state-empty")).toHaveTextContent(/administrador/);
    expect(v.queryByText(/OPERATIVO/)).toBeNull();
  });

  it("si `mobile-state` falla, la salud del gabinete NO aparece", async () => {
    // La trampa de T-2.58/59 en una línea: un KPI fuera del marco se lee como
    // «todo en orden» justo cuando nadie puede saberlo.
    mockSnapshot = instantanea({ error: "No se pudo consultar el estado del sitio." });

    const v = await render(<Panel />);
    await asentar();

    expect(v.getByTestId("state-error")).toHaveTextContent(
      /No se pudo consultar el estado del sitio/,
    );
    expect(v.queryByText(/OPERATIVO/)).toBeNull();
    expect(v.queryByText(/TORRE REFORMA/)).toBeNull();
  });

  it("con dato VIEJO el panel se pinta bajo el banner de retenidos", async () => {
    mockSnapshot = instantanea({
      data: estado(),
      stale: true,
      dataUpdatedAt: AHORA - 9 * 60_000,
    });

    const v = await render(<Panel />);
    await asentar();

    expect(v.getByTestId("state-stale")).toHaveTextContent(/DATOS RETENIDOS/);
    expect(v.getByText(/TORRE REFORMA/)).toBeTruthy();
  });
});

describe("2.1 · panel · contrato de 4 estados (regla de oro 7)", () => {
  it("materializa los cuatro", async () => {
    await expectFourStates(
      (e) => {
        mockSitio = e === "empty" ? null : SITE;
        mockSnapshot = instantanea({
          loading: e === "loading",
          error: e === "error" ? "No se pudo consultar el estado del sitio." : null,
          data: e === "stale" ? estado() : null,
          stale: e === "stale",
          dataUpdatedAt: e === "stale" ? AHORA - 60_000 : AHORA,
        });
        return <Panel />;
      },
      { asentar },
    );
  });
});
