// [T-9.33 · D-43] La push DICTAMEN_CONFIRM (fase `dictamen_confirm`) abre la
// pantalla de CONFIRMAR DICTAMEN — y solo al TÁCTICO que puede confirmar.
//
// No despierta a nadie (canal `ops`, prioridad normal): no hay toma de pantalla
// al RECIBIRLA, solo al TOCARLA. La push no decide nada: lleva a la pantalla, que
// pregunta al REST cuál es la cabeza vigente y si sigue sin firmar. El ocupante
// jamás, y tampoco un táctico sin `confirm_dictamen`. Una fase de vida (sismo,
// check-in, movimiento, alarma) manda sobre ella.
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
const mockReceived: Listener[] = [];
jest.mock("expo-notifications", () => ({
  setNotificationHandler: jest.fn(),
  addNotificationReceivedListener: jest.fn((fn: Listener) => {
    mockReceived.push(fn);
    return { remove: jest.fn() };
  }),
  addNotificationResponseReceivedListener: jest.fn((fn: Listener) => {
    mockResponded.push(fn);
    return { remove: jest.fn() };
  }),
}));

jest.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: jest.fn() }),
}));

jest.mock("@/services/mySite", () => ({
  useWatchedSiteId: () => "sitio-1",
  adoptarSitioDelPush: jest.fn(),
}));

let mockState: string | null = "idle";
jest.mock("./useAlertState", () => ({
  MOBILE_STATE_KEY: "mobile-state",
  useAlertState: () => ({
    state: mockState,
    data: { phase: mockState, incident: null, building_alarm: null },
  }),
}));

async function entrarComo(
  profile: "occupant" | "tactical",
  confirmDictamen: boolean,
): Promise<void> {
  await act(async () => {
    useSessionStore.getState().setAuthenticated({
      profile,
      idToken: "tok",
      me: {
        sub: "u-1",
        allowed_actions: { confirm_dictamen: confirmDictamen },
      } as unknown as MeResponse,
    });
  });
}

function aviso(phase: string, incidentId = "i-9") {
  return { request: { content: { data: { phase, incident_id: incidentId } } } };
}

async function tocarPush(phase: string, incidentId?: string): Promise<void> {
  await act(async () => {
    for (const fn of mockResponded) {
      fn({ notification: aviso(phase, incidentId) });
    }
  });
}

const DESTINO = { pathname: "/confirmar-dictamen", params: { incident: "i-9" } };

beforeEach(() => {
  mockPush.mockClear();
  mockResponded.length = 0;
  mockReceived.length = 0;
  mockPathname = "/(brigadista)/panel";
  mockState = "idle";
});

describe("[T-9.33] la push DICTAMEN_CONFIRM abre CONFIRMAR DICTAMEN", () => {
  it("táctico con confirm_dictamen ⇒ tocarla abre la pantalla con SU incidente", async () => {
    await entrarComo("tactical", true);
    await render(<CrisisWatcher />);
    await tocarPush("dictamen_confirm");
    expect(mockPush).toHaveBeenCalledWith(DESTINO);
  });

  it("RECIBIRLA no enruta: no es una alarma, se abre al tocarla", async () => {
    await entrarComo("tactical", true);
    await render(<CrisisWatcher />);
    await act(async () => {
      for (const fn of mockReceived) {
        fn(aviso("dictamen_confirm"));
      }
    });
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("ocupante ⇒ JAMÁS, aunque la push le llegara", async () => {
    await entrarComo("occupant", true);
    await render(<CrisisWatcher />);
    await tocarPush("dictamen_confirm");
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("táctico SIN confirm_dictamen ⇒ no abre nada (lo dice el servidor)", async () => {
    await entrarComo("tactical", false);
    await render(<CrisisWatcher />);
    await tocarPush("dictamen_confirm");
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("sin incident_id en la push no hay qué abrir", async () => {
    await entrarComo("tactical", true);
    await render(<CrisisWatcher />);
    await tocarPush("dictamen_confirm", "");
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("con un sismo en curso manda la CRISIS, no el dictamen", async () => {
    mockState = "alert_active";
    mockPathname = "/crisis";
    await entrarComo("tactical", true);
    await render(<CrisisWatcher />);
    await tocarPush("dictamen_confirm");
    expect(mockPush).not.toHaveBeenCalledWith(DESTINO);
  });

  it("ya en la pantalla no empuja otra copia", async () => {
    mockPathname = "/confirmar-dictamen";
    await entrarComo("tactical", true);
    await render(<CrisisWatcher />);
    await tocarPush("dictamen_confirm");
    expect(mockPush).not.toHaveBeenCalled();
  });
});
