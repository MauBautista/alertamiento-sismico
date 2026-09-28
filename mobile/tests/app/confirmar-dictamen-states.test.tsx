// UBICACIÓN: fuera de `src/app/` a propósito — `expo-router` barre TODO lo que
// hay bajo `src/app` con un `require.context`, los `*.test.tsx` incluidos.
//
// [T-9.33 · D-43] LA PANTALLA DE CONFIRMAR DICTAMEN.
//
// Se prueba: los cuatro estados (regla de oro 7), que el ocupante JAMÁS la ve,
// que un táctico sin `confirm_dictamen` tampoco, que el incidente sale del
// parámetro de la push (o del estado del sitio), que «no puede leer la cadena»
// no se confunde con «sin red», y que ESCALAR sale de `request_dictamen`.
import type { DictamenOut, MeResponse, MobileStateOut } from "@takab/sdk";
import { act, fireEvent, render } from "@testing-library/react-native";

import { useSessionStore } from "@/auth/session.store";
import { expectFourStates } from "@/test-utils/expectFourStates";

import ConfirmarDictamen from "@/app/confirmar-dictamen";

const AHORA = Date.now();

// ------------------------------------------------------------------ mocks

let mockParams: Record<string, string> = { incident: "i-9" };
jest.mock("expo-router", () => {
  const { Text } = jest.requireActual("react-native") as typeof import("react-native");
  return {
    Redirect: (p: { href: string }) => <Text testID="redirect">{p.href}</Text>,
    useLocalSearchParams: () => mockParams,
  };
});

jest.mock("@/services/mySite", () => ({ useWatchedSiteId: () => "sitio-1" }));

let mockSnapshot: { data: MobileStateOut | null } = { data: null };
jest.mock("@/features/alert/useAlertState", () => ({
  useAlertState: () => mockSnapshot,
}));

const mockConfirmar = jest.fn(async () => undefined);
const mockEscalar = jest.fn(async () => undefined);
let mockIncidenteDelHook: string | null = null;
let mockHook: Record<string, unknown>;
jest.mock("@/features/dictamen/useConfirmarDictamen", () => {
  const actual = jest.requireActual("@/features/dictamen/useConfirmarDictamen");
  return {
    ...actual,
    useConfirmarDictamen: (id: string | null) => {
      mockIncidenteDelHook = id;
      return mockHook;
    },
  };
});

// ------------------------------------------------------------------ datos

function cabeza(over: Partial<DictamenOut> = {}): DictamenOut {
  return {
    dictamen_id: "d-1",
    incident_id: "i-9",
    tenant_id: "t-1",
    status: "inhabit_monitor",
    band: "amarillo",
    signed_by: null,
    signature_kind: null,
    supersedes_dictamen_id: null,
    created_at: new Date(AHORA).toISOString(),
    basis: { motivos: ["sin_calibracion"], evidence: { active_sensors: 2, uncalibrated_sensors: 2 } },
    ...over,
  };
}

function hook(over: Record<string, unknown> = {}, cadena: Record<string, unknown> = {}) {
  const c = {
    data: undefined as DictamenOut[] | undefined,
    isLoading: false,
    isError: false,
    error: null,
    dataUpdatedAt: 0,
    refetch: jest.fn(),
    ...cadena,
  };
  return {
    cadena: c,
    cabeza: c.data?.[0],
    confirmacion: { estado: "idle", mensaje: null },
    escalado: { estado: "idle", mensaje: null },
    confirmar: mockConfirmar,
    escalar: mockEscalar,
    ...over,
  };
}

async function entrarComo(
  profile: "occupant" | "tactical",
  acciones: Record<string, boolean> = { confirm_dictamen: true, request_dictamen: true },
): Promise<void> {
  await act(async () => {
    useSessionStore.getState().setAuthenticated({
      profile,
      idToken: "tok",
      me: { sub: "u-1", allowed_actions: acciones } as unknown as MeResponse,
    });
  });
}

async function asentar(): Promise<void> {
  await act(async () => {});
}

beforeEach(async () => {
  mockParams = { incident: "i-9" };
  mockSnapshot = { data: null };
  mockConfirmar.mockClear();
  mockEscalar.mockClear();
  mockHook = hook({}, { data: [cabeza()], dataUpdatedAt: AHORA });
  await entrarComo("tactical");
});

// ------------------------------------------------------------------ tests

describe("confirmar dictamen · quién la ve", () => {
  it("el ocupante JAMÁS: vuelve a inicio sin pintar nada", async () => {
    await entrarComo("occupant");
    const v = await render(<ConfirmarDictamen />);
    expect(v.getByTestId("redirect")).toHaveTextContent("/");
    expect(v.queryByTestId("confirmar-dictamen")).toBeNull();
  });

  it("un táctico SIN confirm_dictamen tampoco (lo dice el servidor)", async () => {
    await entrarComo("tactical", { confirm_dictamen: false, request_dictamen: true });
    const v = await render(<ConfirmarDictamen />);
    expect(v.getByTestId("redirect")).toHaveTextContent("/");
  });
});

describe("confirmar dictamen · el flujo", () => {
  it("el incidente sale del parámetro de la push", async () => {
    await render(<ConfirmarDictamen />);
    expect(mockIncidenteDelHook).toBe("i-9");
  });

  it("sin parámetro, el del estado del sitio", async () => {
    mockParams = {};
    mockSnapshot = {
      data: { incident: null, reentry: { incident_id: "i-7" } } as unknown as MobileStateOut,
    };
    await render(<ConfirmarDictamen />);
    expect(mockIncidenteDelHook).toBe("i-7");
  });

  it("AMARILLO: explica, y CONFIRMAR / ESCALAR llaman a la nube", async () => {
    const v = await render(<ConfirmarDictamen />);
    await asentar();
    expect(v.getByTestId("confirmar-banda")).toHaveTextContent(/AMARILLO/);
    expect(v.getByTestId("confirmar-porque")).toHaveTextContent(/calibración/);
    await fireEvent.press(v.getByTestId("confirmar-dictamen"));
    expect(mockConfirmar).toHaveBeenCalled();
    await fireEvent.press(v.getByTestId("escalar-inspector"));
    expect(mockEscalar).toHaveBeenCalled();
  });

  it("sin request_dictamen no hay botón de escalar", async () => {
    await entrarComo("tactical", { confirm_dictamen: true, request_dictamen: false });
    const v = await render(<ConfirmarDictamen />);
    await asentar();
    expect(v.queryByTestId("escalar-inspector")).toBeNull();
    expect(v.getByTestId("escalar-sin-permiso")).toBeTruthy();
  });

  it("un 403 al leer la cadena se dice como permiso, no como red caída", async () => {
    const { ErrorDeCadena } = jest.requireActual("@/features/dictamen/useConfirmarDictamen") as {
      ErrorDeCadena: new (s: number) => Error;
    };
    mockHook = hook({}, { isError: true, error: new ErrorDeCadena(403) });
    const v = await render(<ConfirmarDictamen />);
    await asentar();
    expect(v.getByTestId("state-error")).toHaveTextContent(/no puede consultar/);
  });

  it("sin dictamen en la cadena: vacío honesto", async () => {
    mockHook = hook({}, { data: [], dataUpdatedAt: AHORA });
    const v = await render(<ConfirmarDictamen />);
    await asentar();
    expect(v.getByTestId("state-empty")).toHaveTextContent(/Aún no hay dictamen/);
  });
});

describe("confirmar dictamen · contrato de 4 estados (regla de oro 7)", () => {
  it("materializa los cuatro", async () => {
    await expectFourStates(
      (e) => {
        mockParams = e === "empty" ? {} : { incident: "i-9" };
        mockSnapshot = { data: null };
        mockHook = hook(
          {},
          {
            isLoading: e === "loading",
            isError: e === "error",
            error: e === "error" ? new Error("offline") : null,
            data: e === "stale" ? [cabeza()] : undefined,
            dataUpdatedAt: e === "stale" ? AHORA - 10 * 60_000 : 0,
          },
        );
        return <ConfirmarDictamen />;
      },
      { asentar },
    );
  });
});
