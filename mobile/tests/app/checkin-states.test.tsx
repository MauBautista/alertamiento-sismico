// UBICACIÓN: fuera de `src/app/` a propósito — `expo-router` barre TODO lo que
// hay bajo `src/app` con un `require.context` y un `*.test.tsx` ahí dentro
// rompe el bundle. Misma nota que `sync-states.test.tsx`.
//
// [T-2.111] EL CHECK-IN DE VIDA GIRABA SIN SITIO Y SE TRAGABA EL FALLO LOCAL.
//
// Dos defectos del mismo género en la pantalla con la que una persona dice que
// está viva:
//
//  1. `if (state === null || incident === null)` pintaba un `ActivityIndicator`
//     con «VERIFICANDO ESTADO CON EL SERVIDOR…». Sin sitio vigilado la consulta
//     de `mobile-state` no se habilita, así que ese estado NO SE RESUELVE NUNCA.
//  2. `submit()` hacía `void (async () => { … await enqueueCheckin(…);
//     setBusy(null); })()` sin `try`. Encolar es una escritura en la base local
//     cifrada y PUEDE fallar (disco lleno, SQLCipher ausente, base bloqueada —
//     el caso que `sync-states.test.tsx` ya midió). Al fallar, `setBusy(null)`
//     no corría: el botón se quedaba con el spinner dentro, la persona creía
//     haber avisado y NO HABÍA NADA guardado en ninguna parte.
import type { MobileStateOut } from "@takab/sdk";
import { act, fireEvent, render } from "@testing-library/react-native";

import { expectFourStates } from "@/test-utils/expectFourStates";

import Checkin from "@/app/checkin";

const SITE = "11111111-1111-1111-1111-111111111111";
const AHORA = 1_800_000_000_000;

// ------------------------------------------------------------------ mocks

jest.mock("expo-router", () => {
  const { Text } = require("react-native");
  return { Redirect: (p: { href: string }) => <Text testID="redirect">{p.href}</Text> };
});

jest.mock("@/auth/session.store", () => ({
  useSessionStore: (sel: (s: { status: string; me: null }) => unknown) =>
    sel({ status: "authenticated", me: null }),
}));

let mockSitio: string | null = SITE;
jest.mock("@/services/mySite", () => ({ useWatchedSiteId: () => mockSitio }));

type Snapshot = ReturnType<typeof instantanea>;
let mockSnapshot: Snapshot;
jest.mock("@/features/alert/useAlertState", () => ({ useAlertState: () => mockSnapshot }));

jest.mock("@/services/onboarding", () => ({ getGpsConsent: jest.fn(async () => false) }));
jest.mock("@/features/checkin/location", () => ({ captureLocation: jest.fn(async () => null) }));
jest.mock("@/offline/sync", () => ({ drainQueue: jest.fn(async () => undefined) }));

const mockEncolar = jest.fn(async () => undefined);
jest.mock("@/offline/queue.store", () => {
  const store = (sel: (s: { items: unknown[] }) => unknown) => sel({ items: [] });
  store.getState = () => ({ enqueueCheckin: mockEncolar, items: [] });
  return { useQueueStore: store };
});

// ------------------------------------------------------------------ datos

function estado(over: Partial<MobileStateOut> = {}): MobileStateOut {
  return {
    site_id: SITE,
    site_name: "Torre Reforma",
    server_ts: new Date(AHORA).toISOString(),
    phase: "shaking_concluded",
    incident: {
      incident_id: "inc-1",
      opened_at: new Date(AHORA - 120_000).toISOString(),
      trigger: "sasmex",
      max_pga_g: null,
      node_count: null,
    },
    latest_tier: "watch",
    my_zone: { zone_id: "z-1", name: "Piso 12", evac_policy: "evacuate" },
    reentry: { blocked: true, dictamen_status: null, dictamen_signed: false },
    assembly_point: null,
    compliance_labels: {},
    ...over,
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
    stale: false,
    ...over,
  };
}

/** La pantalla en su estado ÚTIL: sacudida concluida, sin check-in propio. */
function pendiente(over: Record<string, unknown> = {}) {
  return instantanea({ state: "checkin_pending", data: estado(), ...over });
}

beforeEach(() => {
  mockSitio = SITE;
  mockSnapshot = instantanea();
  mockEncolar.mockReset();
  mockEncolar.mockResolvedValue(undefined);
});

async function asentar(): Promise<void> {
  await act(async () => {});
}

// ------------------------------------------------------------------ tests

describe("1.4 · check-in · sin sitio vigilado DECLARA, no gira", () => {
  it("dice que no hay edificio vinculado — jamás «VERIFICANDO…» eterno", async () => {
    mockSitio = null;

    const v = await render(<Checkin />);
    await asentar();

    expect(v.getByTestId("state-empty")).toBeTruthy();
    expect(v.getByTestId("state-empty")).toHaveTextContent(/no está vinculado a ningún edificio/i);
    expect(v.queryByTestId("state-loading")).toBeNull();
    expect(v.queryByText(/VERIFICANDO ESTADO CON EL SERVIDOR/)).toBeNull();
  });

  it("si `mobile-state` falla se DICE, con reintento", async () => {
    mockSnapshot = instantanea({ error: "No se pudo consultar el estado del sitio." });

    const v = await render(<Checkin />);
    await asentar();

    expect(v.getByTestId("state-error")).toBeTruthy();
    expect(v.getByTestId("state-retry")).toBeTruthy();
  });
});

describe("1.4 · check-in · un fallo al guardar NO se traga (regla de oro 7)", () => {
  it("el botón vuelve de ENVIANDO y se dice que NO se guardó nada", async () => {
    mockSnapshot = pendiente();
    mockEncolar.mockRejectedValue(new Error("database is locked"));

    const v = await render(<Checkin />);
    await asentar();

    await act(async () => {
      fireEvent.press(v.getByTestId("btn-safe"));
    });
    await asentar();

    // 1) El botón NO se quedó ocupado: se puede volver a intentar.
    expect(v.getByText("ESTOY BIEN")).toBeTruthy();
    // 2) Y se dice la verdad: no se guardó, no se envió, hay que reintentar.
    expect(v.getByTestId("checkin-outcome")).toHaveTextContent(/No se pudo guardar su check-in/);
    expect(v.getByTestId("checkin-outcome")).toHaveTextContent(/vuelva a pulsar/i);
  });

  it("cuando SÍ se guarda no se pinta ningún error", async () => {
    mockSnapshot = pendiente();

    const v = await render(<Checkin />);
    await asentar();

    await act(async () => {
      fireEvent.press(v.getByTestId("btn-safe"));
    });
    await asentar();

    expect(mockEncolar).toHaveBeenCalledTimes(1);
    expect(v.queryByTestId("checkin-outcome")).toBeNull();
  });
});

describe("1.4 · check-in · contrato de 4 estados (regla de oro 7)", () => {
  it("materializa los cuatro", async () => {
    await expectFourStates(
      (e) => {
        mockSitio = e === "empty" ? null : SITE;
        mockSnapshot = instantanea({
          loading: e === "loading",
          error: e === "error" ? "No se pudo consultar el estado del sitio." : null,
          state: e === "stale" ? "checkin_pending" : null,
          data: e === "stale" ? estado() : null,
          stale: e === "stale",
          dataUpdatedAt: e === "stale" ? AHORA - 60_000 : 0,
        });
        return <Checkin />;
      },
      { asentar },
    );
  });
});
