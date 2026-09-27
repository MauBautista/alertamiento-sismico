// [D-42] EL ADMINISTRADOR DESPIERTA… y la app sabe DÓNDE.
//
// `tenant_admin` ve todo su cliente (`site_scope: "*"`): no tiene sitio vigilado,
// así que sin esto `useAlertState(null)` no consultaba ningún `mobile-state` y un
// push de MOVIMIENTO le sonaba sin llevarlo a ninguna parte. La nube pone el
// `site_id` del incidente en el payload: la app lo ADOPTA como sitio vigilado
// (solo para los roles de todo el cliente) y a partir de ahí manda el REST.
// Un ocupante o un táctico con alcance por inmueble NUNCA adopta: ya tienen el suyo.
import { act, render } from "@testing-library/react-native";
import type { MeResponse } from "@takab/sdk";

import { useSessionStore } from "@/auth/session.store";
import { resetWatchedSiteForTests } from "@/services/mySite";

import { CrisisWatcher } from "./CrisisWatcher";

jest.mock("expo-secure-store", () => {
  const disco = new Map<string, string>();
  return {
    getItemAsync: jest.fn(async (k: string) => disco.get(k) ?? null),
    setItemAsync: jest.fn(async (k: string, v: string) => void disco.set(k, v)),
    deleteItemAsync: jest.fn(async (k: string) => void disco.delete(k)),
  };
});

const mockPush = jest.fn();
jest.mock("expo-router", () => ({
  useRouter: () => ({ push: mockPush }),
  usePathname: () => "/(brigadista)/panel",
}));

type Listener = (r: unknown) => void;
const mockReceived: Listener[] = [];
const mockResponded: Listener[] = [];
let mockUltimaRespuesta: unknown = null;
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
  getLastNotificationResponseAsync: jest.fn(async () => mockUltimaRespuesta),
}));

jest.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: jest.fn() }),
}));

// El REST de ESE inmueble dice movimiento; sin sitio no hay consulta ni fase.
const mockConsultados: (string | null)[] = [];
jest.mock("./useAlertState", () => ({
  MOBILE_STATE_KEY: "mobile-state",
  useAlertState: (siteId: string | null) => {
    mockConsultados.push(siteId);
    const phase = siteId === "sitio-x" ? "building_movement" : null;
    return { state: phase, data: phase ? { phase, incident: { incident_id: "i-1" } } : undefined };
  },
}));

function contenido(site_id: string, phase = "building_movement") {
  return { request: { content: { data: { type: "incident", site_id, incident_id: "i-1", phase } } } };
}

async function entrar(profile: "occupant" | "tactical", me: Partial<MeResponse>): Promise<void> {
  await act(async () => {
    useSessionStore.getState().setAuthenticated({
      profile,
      idToken: "tok",
      me: { sub: "u-1", ...me } as unknown as MeResponse,
    });
  });
}

beforeEach(() => {
  mockPush.mockClear();
  mockReceived.length = 0;
  mockResponded.length = 0;
  mockConsultados.length = 0;
  mockUltimaRespuesta = null;
  resetWatchedSiteForTests();
});

afterEach(() => {
  useSessionStore.getState().signOut("user");
});

describe("[D-42] el rol de todo el cliente adopta el sitio del push", () => {
  it("admin toca la push de MOVIMIENTO ⇒ fija el sitio y termina en /movimiento", async () => {
    await entrar("tactical", { role: "tenant_admin", site_scope: "*" });
    await render(<CrisisWatcher />);
    expect(mockPush).not.toHaveBeenCalled();
    await act(async () => {
      for (const fn of mockResponded) fn({ notification: contenido("sitio-x") });
    });
    expect(mockConsultados).toContain("sitio-x");
    expect(mockPush).toHaveBeenCalledWith("/movimiento");
  });

  it("admin RECIBE la push en primer plano ⇒ también adopta el sitio", async () => {
    await entrar("tactical", { role: "tenant_admin", site_scope: "*" });
    await render(<CrisisWatcher />);
    await act(async () => {
      for (const fn of mockReceived) fn(contenido("sitio-x"));
    });
    expect(mockPush).toHaveBeenCalledWith("/movimiento");
  });

  it("arranque en FRÍO: la push que abrió la app también se adopta", async () => {
    mockUltimaRespuesta = { notification: contenido("sitio-x") };
    await entrar("tactical", { role: "tenant_admin", site_scope: "*" });
    await render(<CrisisWatcher />);
    await act(async () => {
      for (let i = 0; i < 5; i++) await Promise.resolve();
    });
    expect(mockPush).toHaveBeenCalledWith("/movimiento");
  });

  it("ocupante ⇒ NUNCA adopta un sitio de una push", async () => {
    await entrar("occupant", { role: "occupant", site_scope: [] as unknown as "*" });
    await render(<CrisisWatcher />);
    await act(async () => {
      for (const fn of mockResponded) fn({ notification: contenido("sitio-x") });
      for (const fn of mockReceived) fn(contenido("sitio-x"));
    });
    expect(mockConsultados).not.toContain("sitio-x");
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("brigadista con alcance POR INMUEBLE ⇒ no adopta (ya tiene el suyo)", async () => {
    await entrar("tactical", { role: "brigadista", site_scope: ["sitio-propio"] });
    await render(<CrisisWatcher />);
    await act(async () => {
      for (const fn of mockResponded) fn({ notification: contenido("sitio-x") });
    });
    expect(mockConsultados).not.toContain("sitio-x");
  });
});
