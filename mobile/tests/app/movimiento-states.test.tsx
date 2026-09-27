// UBICACIÓN: fuera de `src/app/` a propósito — `expo-router` barre TODO lo que
// hay bajo `src/app` con un `require.context`, los `*.test.tsx` incluidos, y la
// app deja de compilar. Misma nota que `alarma-inmueble-states.test.tsx`.
//
// [T-9.11 · D-39] LA PANTALLA DE MOVIMIENTO EN EL INMUEBLE.
//
// Se prueba: los cuatro estados (regla de oro 7), que al ocupante NUNCA se le
// pinta (aunque la fase llegara), que al dejar de ser `building_movement` vuelve
// a INICIO, y que el acuse y REPORTAR DAÑOS salen de `allowed_actions`.
import type { MobileStateOut } from "@takab/sdk";
import { act, fireEvent, render } from "@testing-library/react-native";

import { expectFourStates } from "@/test-utils/expectFourStates";

import Movimiento from "@/app/movimiento";

const SITE = "11111111-1111-1111-1111-111111111111";
const AHORA = Date.now();

// ------------------------------------------------------------------ mocks

const mockPush = jest.fn();
jest.mock("expo-router", () => {
  const { Text } = jest.requireActual("react-native") as typeof import("react-native");
  return {
    Redirect: (p: { href: string }) => <Text testID="redirect">{p.href}</Text>,
    useRouter: () => ({ push: mockPush }),
  };
});

type Sesion = {
  status: string;
  profile: string | null;
  me: { allowed_actions: Record<string, boolean> } | null;
};
const TACTICO: Sesion = {
  status: "authenticated",
  profile: "tactical",
  me: {
    allowed_actions: { manual_activate: true, movement_alert: true, damage_report_submit: true },
  },
};
let mockSesion: Sesion = TACTICO;
jest.mock("@/auth/session.store", () => ({
  useSessionStore: (sel: (s: Sesion) => unknown) => sel(mockSesion),
}));

jest.mock("@/features/alarm/useTacticalAck", () => ({
  useTacticalAck: () => ({ estado: "idle", acusadoEn: null, acusar: jest.fn() }),
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

function estado(over: Partial<MobileStateOut> = {}): MobileStateOut {
  return {
    site_id: SITE,
    site_name: "Torre Reforma",
    server_ts: new Date(AHORA).toISOString(),
    phase: "building_movement",
    incident: {
      incident_id: "inc-1",
      max_pga_g: 0.0123,
      node_count: 1,
      opened_at: new Date(AHORA - 120_000).toISOString(),
      severity: "watch",
      state: "open",
      trigger: "local",
    },
    building_alarm: null,
    latest_tier: "watch",
    my_zone: null,
    reentry: { blocked: false, dictamen_status: null, dictamen_signed: false },
    assembly_point: null,
    compliance_labels: {},
    drill: { active: false, last_note: null, last_started_at: null, next_scheduled_at: null },
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
    staleSinceMs: null as number | null,
    ...over,
  };
}

beforeEach(() => {
  mockPush.mockClear();
  mockSitio = SITE;
  mockSesion = TACTICO;
  mockSnapshot = instantanea();
});

async function asentar(): Promise<void> {
  await act(async () => {});
}

// ------------------------------------------------------------------ tests

describe("[T-9.11] movimiento en el inmueble · contenido", () => {
  it("pinta titular, texto, hora relativa, PGA, acuse y REPORTAR DAÑOS", async () => {
    mockSnapshot = instantanea({
      state: "building_movement",
      data: estado(),
      dataUpdatedAt: AHORA,
    });
    const v = await render(<Movimiento />);
    await asentar();

    expect(v.getByText("MOVIMIENTO EN EL INMUEBLE")).toBeTruthy();
    expect(v.getByText(/No es una alerta sísmica oficial/)).toBeTruthy();
    expect(v.getByText("hace 2 min")).toBeTruthy();
    expect(v.getByTestId("movimiento-pga")).toHaveTextContent(/0\.012 g/);
    expect(v.getByTestId("tactical-ack")).toBeTruthy();
    // Aquí no hay sirena: el pie del acuse no puede hablar de ella.
    expect(v.queryByText(/sirena/i)).toBeNull();

    fireEvent.press(v.getByTestId("movimiento-reportar"));
    expect(mockPush).toHaveBeenCalledWith("/(brigadista)/triage");
  });

  it("sin `damage_report_submit` ni `manual_activate`, ni reportar ni acusar", async () => {
    mockSesion = {
      ...TACTICO,
      me: { allowed_actions: { movement_alert: true } },
    };
    mockSnapshot = instantanea({ state: "building_movement", data: estado() });
    const v = await render(<Movimiento />);
    await asentar();

    expect(v.getByText("MOVIMIENTO EN EL INMUEBLE")).toBeTruthy();
    expect(v.queryByTestId("movimiento-reportar")).toBeNull();
    expect(v.queryByTestId("tactical-ack")).toBeNull();
  });

  it("el OCUPANTE nunca la ve, aunque la fase llegara: vuelve a INICIO", async () => {
    mockSesion = { status: "authenticated", profile: "occupant", me: null };
    mockSnapshot = instantanea({ state: "building_movement", data: estado() });
    const v = await render(<Movimiento />);
    await asentar();

    expect(v.getByTestId("redirect")).toHaveTextContent("/");
    expect(v.queryByText("MOVIMIENTO EN EL INMUEBLE")).toBeNull();
  });

  it("si la fase deja de ser building_movement, vuelve a INICIO", async () => {
    mockSnapshot = instantanea({ state: "idle", data: estado({ phase: "idle", incident: null }) });
    const v = await render(<Movimiento />);
    await asentar();

    expect(v.getByTestId("redirect")).toHaveTextContent("/");
  });

  it("el servidor respondió sin incidente: vacío honesto", async () => {
    mockSnapshot = instantanea({
      state: "building_movement",
      data: estado({ incident: null }),
    });
    const v = await render(<Movimiento />);
    await asentar();

    expect(v.getByTestId("state-empty")).toHaveTextContent(/no reporta ningún movimiento/i);
  });
});

describe("[T-9.11] movimiento + alarma del inmueble a la vez", () => {
  it("con `building_alarm` presente: bloque «ALARMA DEL INMUEBLE ACTIVA» que abre /alarma-inmueble", async () => {
    mockSnapshot = instantanea({
      state: "building_movement",
      data: estado({ building_alarm: { since: new Date(AHORA - 30_000).toISOString() } } as never),
      dataUpdatedAt: AHORA,
    });
    const v = await render(<Movimiento />);
    await asentar();

    expect(v.getByText("MOVIMIENTO EN EL INMUEBLE")).toBeTruthy();
    expect(v.getByText("ALARMA DEL INMUEBLE ACTIVA")).toBeTruthy();
    fireEvent.press(v.getByTestId("movimiento-alarma"));
    expect(mockPush).toHaveBeenCalledWith("/alarma-inmueble");
  });

  it("sin `building_alarm` no hay bloque", async () => {
    mockSnapshot = instantanea({ state: "building_movement", data: estado() });
    const v = await render(<Movimiento />);
    await asentar();

    expect(v.queryByText("ALARMA DEL INMUEBLE ACTIVA")).toBeNull();
  });
});

describe("[T-9.11] movimiento en el inmueble · contrato de 4 estados (regla de oro 7)", () => {
  it("materializa los cuatro", async () => {
    await expectFourStates(
      (e) => {
        mockSitio = e === "empty" ? null : SITE;
        mockSnapshot = instantanea({
          loading: e === "loading",
          error: e === "error" ? "No se pudo consultar el estado del sitio." : null,
          state: e === "stale" ? "building_movement" : null,
          data: e === "stale" ? estado() : null,
          staleSinceMs: e === "stale" ? AHORA - 60_000 : null,
          dataUpdatedAt: e === "stale" ? AHORA - 60_000 : 0,
        });
        return <Movimiento />;
      },
      { asentar },
    );
  });
});
