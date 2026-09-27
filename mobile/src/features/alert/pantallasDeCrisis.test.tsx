// [T-9.06 + T-9.04] LAS PANTALLAS REALES: vibración en la toma de crisis, y el
// bloqueo persistente del servidor no deja a nadie en un callejón.
//
// UBICACIÓN: fuera de `src/app/` a propósito — `expo-router` barre ese árbol
// con `require.context` y un `*.test.tsx` ahí dentro rompe el bundle. Aquí se
// importan las rutas REALES `crisis.tsx` y `checkin.tsx`: los tests del hook
// dicen que el hook funciona; éstos dicen que la pantalla lo usa.
import type { MobileStateOut } from "@takab/sdk";
import { act, fireEvent, render } from "@testing-library/react-native";
import { Vibration } from "react-native";

import { PATRON_ALERTA, stopAlertVibration } from "./vibration";

import Checkin from "@/app/checkin";
import Crisis from "@/app/crisis";

const SITE = "11111111-1111-1111-1111-111111111111";
const AHORA = Date.now();

// ------------------------------------------------------------------ mocks

const mockReplace = jest.fn();
jest.mock("expo-router", () => {
  const { Text } = jest.requireActual("react-native") as typeof import("react-native");
  return {
    Redirect: (p: { href: string }) => <Text testID="redirect">{p.href}</Text>,
    useRouter: () => ({ replace: mockReplace, push: jest.fn() }),
  };
});

// El bucle de audio toca `expo-audio`; aquí sólo importa que se arranque/pare.
jest.mock("@/features/alert/sound", () => ({
  startAlertLoop: jest.fn(async () => undefined),
  stopAlertLoop: jest.fn(),
}));

let mockPerfil: string | null = "occupant";
jest.mock("@/auth/session.store", () => ({
  useSessionStore: (sel: (s: { status: string; me: null; profile: string | null }) => unknown) =>
    sel({ status: "authenticated", me: null, profile: mockPerfil }),
}));

jest.mock("@/services/mySite", () => ({ useWatchedSiteId: () => SITE }));

type Snapshot = ReturnType<typeof instantanea>;
let mockSnapshot: Snapshot;
jest.mock("@/features/alert/useAlertState", () => ({ useAlertState: () => mockSnapshot }));

// Dependencias del check-in que no son objeto de esta prueba.
jest.mock("@/services/onboarding", () => ({ getGpsConsent: jest.fn(async () => false) }));
jest.mock("@/features/checkin/location", () => ({ captureLocation: jest.fn(async () => null) }));
jest.mock("@/offline/sync", () => ({ drainQueue: jest.fn(async () => undefined) }));
jest.mock("@/offline/queue.store", () => {
  const store = (sel: (s: { items: unknown[] }) => unknown) => sel({ items: [] });
  store.getState = () => ({ enqueueCheckin: jest.fn(async () => undefined), items: [] });
  return { useQueueStore: store };
});

// ------------------------------------------------------------------ datos

function incidente() {
  return {
    incident_id: "inc-1",
    opened_at: new Date(AHORA - 42_000).toISOString(),
    trigger: "sasmex",
    severity: "high",
    state: "open",
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
    ...over,
  } as unknown as MobileStateOut;
}

/** El bloqueo PERSISTENTE del servidor: incidente cerrado, veredicto vivo. */
function bloqueoDelServidor(reason: "no_habitable" | "pendiente_dictamen"): MobileStateOut {
  return estado({
    phase: "reentry_blocked",
    incident: null,
    latest_tier: "normal",
    reentry: {
      blocked: true,
      dictamen_signed: reason === "no_habitable",
      dictamen_status: reason === "no_habitable" ? "do_not_inhabit" : null,
      incident_id: "inc-1",
      reason,
    },
  });
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
    staleSinceMs: null,
    ...over,
  };
}

let vibrate: jest.SpyInstance;
let cancel: jest.SpyInstance;

beforeEach(() => {
  mockPerfil = "occupant";
  mockReplace.mockClear();
  mockSnapshot = instantanea();
  vibrate = jest.spyOn(Vibration, "vibrate").mockImplementation(() => undefined);
  cancel = jest.spyOn(Vibration, "cancel").mockImplementation(() => undefined);
  stopAlertVibration();
  vibrate.mockClear();
  cancel.mockClear();
});

afterEach(() => {
  vibrate.mockRestore();
  cancel.mockRestore();
});

async function asentar(): Promise<void> {
  await act(async () => {});
}

// ------------------------------------------------------------------ tests

describe("[T-9.06] crisis.tsx · vibra mientras la alerta está viva", () => {
  it("con alert_active la pantalla arranca la vibración EN BUCLE", async () => {
    mockSnapshot = instantanea({ state: "alert_active", data: estado() });

    const v = await render(<Crisis />);
    await asentar();

    expect(v.getByText(/EVACÚE/)).toBeTruthy();
    expect(vibrate).toHaveBeenCalledWith([...PATRON_ALERTA], true);
    expect(cancel).not.toHaveBeenCalled();
  });

  it("cuando el servidor deja de sostener la alerta, el motor se CANCELA", async () => {
    mockSnapshot = instantanea({ state: "alert_active", data: estado() });
    const v = await render(<Crisis />);
    await asentar();
    expect(vibrate).toHaveBeenCalledTimes(1);

    mockSnapshot = instantanea({
      state: "checkin_pending",
      data: estado({ phase: "shaking_concluded", latest_tier: "normal" }),
    });
    await v.rerender(<Crisis />);
    await asentar();

    expect(v.getByTestId("redirect")).toHaveTextContent("/checkin");
    expect(cancel).toHaveBeenCalled();
  });

  it("la salida del TÁCTICO calla el altavoz y también el motor", async () => {
    mockPerfil = "tactical";
    mockSnapshot = instantanea({ state: "alert_active", data: estado() });
    const v = await render(<Crisis />);
    await asentar();

    await act(async () => {
      fireEvent.press(v.getByTestId("crisis-salir-tactico"));
    });

    expect(cancel).toHaveBeenCalled();
    expect(mockReplace).toHaveBeenCalledWith("/(brigadista)/panel");
  });

  it("sin alerta viva no vibra nada", async () => {
    mockSnapshot = instantanea({ state: "idle", data: estado({ phase: "idle", incident: null }) });
    await render(<Crisis />);
    await asentar();
    expect(vibrate).not.toHaveBeenCalled();
  });
});

describe("[T-9.04] el bloqueo persistente del servidor va a INICIO, no a un callejón", () => {
  it("crisis.tsx: con phase=reentry_blocked (sin incidente) redirige a INICIO, no al check-in", async () => {
    mockSnapshot = instantanea({ state: "reentry_blocked", data: bloqueoDelServidor("no_habitable") });

    const v = await render(<Crisis />);
    await asentar();

    expect(v.getByTestId("redirect")).toHaveTextContent(/^\/$/);
    expect(vibrate).not.toHaveBeenCalled();
  });

  it("checkin.tsx: con phase=reentry_blocked redirige a INICIO, donde vive el cartel", async () => {
    // Antes caía en «El servidor no reporta ninguna sacudida por la que haya
    // que reportarse»: cierto, y engañoso para quien acaba de leer el bloqueo.
    mockSnapshot = instantanea({
      state: "reentry_blocked",
      data: bloqueoDelServidor("pendiente_dictamen"),
    });

    const v = await render(<Checkin />);
    await asentar();

    expect(v.getByTestId("redirect")).toHaveTextContent(/^\/$/);
    expect(v.queryByText(/no reporta ninguna sacudida/)).toBeNull();
  });

  it("checkin.tsx: el bloqueo del CHECK-IN PROPIO (incidente abierto) sigue igual", async () => {
    // Regresión: `reentry_blocked` de la app con incidente ABIERTO es la
    // pantalla 1.5 de siempre, con su línea de tiempo.
    mockSnapshot = instantanea({
      state: "reentry_blocked",
      hasOwnCheckin: true,
      data: estado({
        phase: "shaking_concluded",
        latest_tier: "normal",
        reentry: { blocked: true, dictamen_status: null, dictamen_signed: false },
      }),
    });

    const v = await render(<Checkin />);
    await asentar();

    expect(v.queryByTestId("redirect")).toBeNull();
    expect(v.getByTestId("reentry-sign")).toHaveTextContent(/REINGRESO PROHIBIDO/);
  });
});
