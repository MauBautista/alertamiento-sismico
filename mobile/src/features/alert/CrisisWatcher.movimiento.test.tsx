// [T-9.11 · D-39] MOVIMIENTO EN EL INMUEBLE: el vigilante lo anuncia al TÁCTICO
// y NUNCA al ocupante.
//
// La nube solo sirve `phase="building_movement"` a los roles con
// `movement_alert`; aun así la app no se fía: con perfil de ocupante no hay toma
// de pantalla aunque la fase llegara. Se anuncia UNA VEZ por incidente (la
// brigada tiene que poder ir a REPORTAR DAÑOS sin que la devuelvan a la fuerza),
// y tocar la push de movimiento la vuelve a abrir.
import { act, render } from "@testing-library/react-native";
import type { MeResponse } from "@takab/sdk";

import { useSessionStore } from "@/auth/session.store";

import { CrisisWatcher } from "./CrisisWatcher";

const mockPush = jest.fn();
let mockPathname = "/(brigadista)/panel";
jest.mock("expo-router", () => ({
  useRouter: () => ({ push: mockPush }),
  usePathname: () => mockPathname,
}));

type Listener = (r: unknown) => void;
const mockResponded: Listener[] = [];
jest.mock("expo-notifications", () => ({
  setNotificationHandler: jest.fn(),
  addNotificationReceivedListener: jest.fn(() => ({ remove: jest.fn() })),
  addNotificationResponseReceivedListener: jest.fn((fn: Listener) => {
    mockResponded.push(fn);
    return { remove: jest.fn() };
  }),
}));

jest.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: jest.fn() }),
}));

jest.mock("@/services/mySite", () => ({ useWatchedSiteId: () => "sitio-1" }));

let mockState: string | null = "building_movement";
let mockIncidente = "i-1";
let mockAlarmaDesde: string | null = null;
jest.mock("./useAlertState", () => ({
  MOBILE_STATE_KEY: "mobile-state",
  useAlertState: () => ({
    state: mockState,
    data: {
      phase: mockState,
      incident: { incident_id: mockIncidente },
      building_alarm: mockAlarmaDesde ? { since: mockAlarmaDesde } : null,
    },
  }),
}));

async function entrarComo(profile: "occupant" | "tactical"): Promise<void> {
  await act(async () => {
    useSessionStore.getState().setAuthenticated({
      profile,
      idToken: "tok",
      me: { sub: "u-1" } as unknown as MeResponse,
    });
  });
}

async function tocarPush(phase: string): Promise<void> {
  await act(async () => {
    for (const fn of mockResponded) {
      fn({ notification: { request: { content: { data: { phase } } } } });
    }
  });
}

async function montar(): Promise<{ rerender: () => Promise<void> }> {
  const r = await render(<CrisisWatcher />);
  return {
    rerender: async () => {
      await r.rerender(<CrisisWatcher />);
    },
  };
}

beforeEach(() => {
  mockPush.mockClear();
  mockResponded.length = 0;
  mockPathname = "/(brigadista)/panel";
  mockState = "building_movement";
  mockIncidente = "i-1";
  mockAlarmaDesde = null;
});

describe("[T-9.11] toma de pantalla del movimiento en el inmueble", () => {
  it("táctico ⇒ abre /movimiento", async () => {
    await entrarComo("tactical");
    await montar();
    expect(mockPush).toHaveBeenCalledWith("/movimiento");
  });

  it("ocupante ⇒ NUNCA, aunque la fase llegara (la app no se fía)", async () => {
    await entrarComo("occupant");
    await montar();
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("se anuncia UNA vez por incidente: re-renderizar no lo devuelve", async () => {
    await entrarComo("tactical");
    const r = await montar();
    expect(mockPush).toHaveBeenCalledTimes(1);
    mockPathname = "/(brigadista)/triage";
    await r.rerender();
    expect(mockPush).toHaveBeenCalledTimes(1);
  });

  it("un incidente NUEVO vuelve a anunciarse", async () => {
    await entrarComo("tactical");
    const r = await montar();
    mockIncidente = "i-2";
    await r.rerender();
    expect(mockPush).toHaveBeenCalledTimes(2);
  });

  it("ya en /movimiento no empuja otra copia", async () => {
    await entrarComo("tactical");
    mockPathname = "/movimiento";
    await montar();
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("tocar la push de MOVIMIENTO la vuelve a abrir (con la fase confirmada por REST)", async () => {
    await entrarComo("tactical");
    await montar();
    expect(mockPush).toHaveBeenCalledTimes(1);
    await tocarPush("building_movement");
    expect(mockPush).toHaveBeenCalledTimes(2);
    expect(mockPush).toHaveBeenLastCalledWith("/movimiento");
  });

  it("tocar la push de movimiento como ocupante no abre nada", async () => {
    await entrarComo("occupant");
    await montar();
    await tocarPush("building_movement");
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("tocar la push sin que el REST confirme la fase no enruta", async () => {
    await entrarComo("tactical");
    mockState = "idle";
    await montar();
    await tocarPush("building_movement");
    expect(mockPush).not.toHaveBeenCalled();
  });
});

// [T-9.11 · D-39] La alarma de pánico NO se la traga el movimiento: la nube manda
// `building_alarm` también en `building_movement`. Cuando el movimiento termina y
// la alarma SIGUE, la fase vuelve a `building_alarm` y la alarma tiene que
// anunciarse — aunque haya estado presente (y sin anunciar) durante el movimiento.
describe("[T-9.11] movimiento con alarma del inmueble presente", () => {
  it("al volver la fase a building_alarm, la alarma se anuncia", async () => {
    mockAlarmaDesde = "2026-09-27T10:00:00Z";
    await entrarComo("tactical");
    const r = await montar();
    expect(mockPush).toHaveBeenLastCalledWith("/movimiento");

    mockPathname = "/movimiento";
    mockState = "building_alarm";
    await r.rerender();
    expect(mockPush).toHaveBeenLastCalledWith("/alarma-inmueble");
  });

  it("si la brigada ya abrió la alarma DESDE el movimiento, no se le re-empuja", async () => {
    mockAlarmaDesde = "2026-09-27T10:00:00Z";
    await entrarComo("tactical");
    const r = await montar();
    const antes = mockPush.mock.calls.length;

    mockPathname = "/alarma-inmueble";
    await r.rerender();
    mockState = "building_alarm";
    await r.rerender();
    expect(mockPush.mock.calls.length).toBe(antes);
  });

  // El caso que se tragaba: la alarma ya se había anunciado, llega un movimiento
  // (la brigada pasa a /movimiento) y, al terminar, /movimiento suelta a INICIO.
  // Con `alarmaAnunciada` todavía en ese `since`, la alarma —que SIGUE sonando—
  // no se volvía a anunciar y la brigada se quedaba en INICIO.
  it("alarma anunciada → movimiento → vuelve la alarma: se anuncia OTRA vez", async () => {
    mockAlarmaDesde = "2026-09-27T10:00:00Z";
    mockState = "building_alarm";
    await entrarComo("tactical");
    const r = await montar();
    expect(mockPush).toHaveBeenLastCalledWith("/alarma-inmueble");

    mockPathname = "/alarma-inmueble";
    mockState = "building_movement";
    await r.rerender();
    expect(mockPush).toHaveBeenLastCalledWith("/movimiento");

    mockPathname = "/movimiento";
    await r.rerender();
    mockPathname = "/";
    mockState = "building_alarm";
    await r.rerender();
    expect(mockPush).toHaveBeenLastCalledWith("/alarma-inmueble");
    expect(mockPush).toHaveBeenCalledTimes(3);
  });
});
