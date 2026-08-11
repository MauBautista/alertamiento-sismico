// UBICACIÓN: fuera de `src/app/` a propósito — `expo-router` barre TODO lo que
// hay bajo `src/app` con un `require.context`, los `*.test.tsx` incluidos, y la
// app deja de compilar (el 2026-08-08 entraron tres y nadie se enteró en un
// día). Misma nota que `sync-states.test.tsx`.
//
// [T-2.111] LA PANTALLA DE CRISIS GIRABA PARA SIEMPRE SIN SITIO VIGILADO.
//
// `crisis.tsx` resolvía `if (!data?.incident)` con un `ActivityIndicator` y el
// rótulo «VERIFICANDO ALERTA CON EL SERVIDOR…». Sin sitio vigilado la consulta
// de `mobile-state` ni siquiera se habilita (`enabled: siteId != null`), así
// que `data` es null PARA SIEMPRE: el ocupante se queda mirando un spinner en
// la pantalla que existe para decirle si tiene que evacuar. Es la regla de oro
// 7 al revés — un estado que no puede resolverse, pintado como si estuviera
// cargando.
//
// Aquí se asserta el TEXTO que lee la persona, y se pasa el gate de los cuatro
// estados (`expectFourStates`, el equivalente móvil del de la consola).
import type { MobileStateOut } from "@takab/sdk";
import { act, render } from "@testing-library/react-native";

import { expectFourStates } from "@/test-utils/expectFourStates";

import Crisis from "@/app/crisis";

const SITE = "11111111-1111-1111-1111-111111111111";
const AHORA = 1_800_000_000_000;

// ------------------------------------------------------------------ mocks

jest.mock("expo-router", () => {
  const { Text } = require("react-native");
  return {
    Redirect: (p: { href: string }) => <Text testID="redirect">{p.href}</Text>,
  };
});

// El bucle de audio toca `expo-audio`: fuera del alcance de esta ficha.
jest.mock("@/features/alert/sound", () => ({
  startAlertLoop: jest.fn(async () => undefined),
  stopAlertLoop: jest.fn(),
}));

jest.mock("@/auth/session.store", () => ({
  useSessionStore: (sel: (s: { status: string; me: null }) => unknown) =>
    sel({ status: "authenticated", me: null }),
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

// ------------------------------------------------------------------ datos

function incidente() {
  return {
    incident_id: "inc-1",
    opened_at: new Date(AHORA - 42_000).toISOString(),
    trigger: "sasmex",
    max_pga_g: null,
    node_count: null,
  };
}

function estado(over: Partial<MobileStateOut> = {}): MobileStateOut {
  return {
    site_id: SITE,
    site_name: "Torre Reforma",
    server_ts: new Date(AHORA).toISOString(),
    phase: "alert_active",
    incident: incidente(),
    latest_tier: "evacuate_or_hold",
    my_zone: { zone_id: "z-1", name: "Piso 12", evac_policy: "evacuate" },
    reentry: { blocked: false, dictamen_status: null, dictamen_signed: false },
    assembly_point: null,
    compliance_labels: {},
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

beforeEach(() => {
  mockSitio = SITE;
  mockSnapshot = instantanea();
});

async function asentar(): Promise<void> {
  await act(async () => {});
}

// ------------------------------------------------------------------ tests

describe("1.2/1.3 · crisis · sin sitio vigilado DECLARA, no gira", () => {
  it("dice que no hay edificio vinculado y qué hacer — jamás un spinner eterno", async () => {
    mockSitio = null;
    mockSnapshot = instantanea();

    const v = await render(<Crisis />);
    await asentar();

    expect(v.getByTestId("state-empty")).toBeTruthy();
    expect(v.getByTestId("state-empty")).toHaveTextContent(/no está vinculado a ningún edificio/i);
    expect(v.queryByTestId("state-loading")).toBeNull();
    expect(v.queryByText(/VERIFICANDO ALERTA CON EL SERVIDOR/)).toBeNull();
  });

  it("si `mobile-state` falla y no hay dato, lo DICE con reintento", async () => {
    mockSnapshot = instantanea({ error: "No se pudo consultar el estado del sitio." });

    const v = await render(<Crisis />);
    await asentar();

    expect(v.getByTestId("state-error")).toBeTruthy();
    expect(v.getByTestId("state-error")).toHaveTextContent(
      /No se pudo consultar el estado del sitio/,
    );
    expect(v.getByTestId("state-retry")).toBeTruthy();
    expect(v.queryByTestId("state-loading")).toBeNull();
  });

  it("con dato VIEJO se pinta la instrucción PERO bajo el banner de retenidos", async () => {
    mockSnapshot = instantanea({
      state: "alert_active",
      data: estado(),
      stale: true,
      dataUpdatedAt: AHORA - 5 * 60_000,
    });

    const v = await render(<Crisis />);
    await asentar();

    expect(v.getByTestId("state-stale")).toBeTruthy();
    expect(v.getByTestId("state-stale")).toHaveTextContent(/DATOS RETENIDOS/);
    expect(v.getByText(/EVACÚE/)).toBeTruthy();
  });
});

describe("1.2/1.3 · crisis · contrato de 4 estados (regla de oro 7)", () => {
  it("materializa los cuatro", async () => {
    await expectFourStates(
      (e) => {
        mockSitio = e === "empty" ? null : SITE;
        mockSnapshot = instantanea({
          loading: e === "loading",
          error: e === "error" ? "No se pudo consultar el estado del sitio." : null,
          state: e === "stale" ? "alert_active" : null,
          data: e === "stale" ? estado() : null,
          stale: e === "stale",
          dataUpdatedAt: e === "stale" ? AHORA - 60_000 : 0,
        });
        return <Crisis />;
      },
      { asentar },
    );
  });
});
