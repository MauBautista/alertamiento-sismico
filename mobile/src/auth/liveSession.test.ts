// [T-8.04 · A-002 §4] EL CANAL LIVE RENUEVA EN VEZ DE EXPULSAR.
//
// El servidor cierra el WS con 4401 al vencer el `exp` del token del handshake
// (60 min), aunque el REST ya se haya renovado. Hasta esta ficha, `socket.ts`
// respondía a ese cierre RUTINARIO con `signOut()`: el panel del brigadista
// echaba a su dueño cada hora.
//
// Ahora el socket (el `LiveSocket` compartido, T-8.03) pide UN token nuevo y
// reconecta; sólo si la renovación está muerta se cierra la sesión. `offline`
// NO expulsa: el canal se aparca y se reanuda solo cuando llega un token nuevo.
// Y 4440 (D-38, la sesión cumplió la edad de su rol) cierra con motivo `max_age`.
//
// Vive en `auth/` y no junto a `live/socket.ts` por el reparto de ficheros de la
// ficha; prueba ese módulo de verdad, con un WebSocket de mentira.
import { refreshSession } from "@/auth/refresh";
import { useSessionStore } from "@/auth/session.store";
import { getLiveSocket, resetLiveSocketForTests } from "@/live/socket";

import { fakeJwt, nowS } from "./testJwt";

jest.mock("@/auth/config", () => ({
  ...jest.requireActual("@/auth/config"),
  API_BASE_URL: "https://api.takab.test",
}));

jest.mock("@/auth/refresh", () => {
  const actual = jest.requireActual("@/auth/refresh");
  return {
    ...actual,
    refreshSession: jest.fn(),
    ensureFreshToken: jest.fn(async () => "ok"),
  };
});

jest.mock("expo-secure-store", () => ({
  getItemAsync: jest.fn(async () => null),
  setItemAsync: jest.fn(async () => undefined),
  deleteItemAsync: jest.fn(async () => undefined),
}));

const refresh = refreshSession as jest.Mock;

class FakeWS {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;
  static abiertos: FakeWS[] = [];
  readyState = FakeWS.CONNECTING;
  enviados: string[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: ((e: { code: number }) => void) | null = null;
  constructor(public url: string) {
    FakeWS.abiertos.push(this);
  }
  send(d: string) {
    this.enviados.push(d);
  }
  close() {
    this.readyState = FakeWS.CLOSED;
  }
  abrir() {
    this.readyState = FakeWS.OPEN;
    this.onopen?.();
  }
  cerrar(code: number) {
    this.readyState = FakeWS.CLOSED;
    this.onclose?.({ code });
  }
  /** Token del frame de auth (el primero que manda el cliente). */
  tokenEnviado(): string | null {
    const f = this.enviados[0];
    return f ? (JSON.parse(f) as { token?: string }).token ?? null : null;
  }
}

const ultimo = () => FakeWS.abiertos[FakeWS.abiertos.length - 1];
const flush = async () => {
  for (let i = 0; i < 5; i += 1) {
    await new Promise((r) => setTimeout(r, 0));
  }
};

const T1 = fakeJwt({ exp: nowS() + 30 });
const T2 = fakeJwt({ exp: nowS() + 3600 });

beforeAll(() => {
  (globalThis as unknown as { WebSocket: unknown }).WebSocket = FakeWS;
});

beforeEach(() => {
  jest.clearAllMocks();
  resetLiveSocketForTests();
  FakeWS.abiertos = [];
  useSessionStore.setState({
    status: "authenticated",
    profile: "tactical",
    idToken: T1,
    me: null,
    deniedReason: null,
    signOutReason: null,
    authAt: Date.now(),
    maxAgeS: 2_592_000,
  });
});

async function conectar() {
  getLiveSocket().connect();
  await flush();
  const ws = ultimo();
  ws.abrir();
  return ws;
}

describe("4401 ⇒ renovar y reconectar", () => {
  it("refresh 'ok' ⇒ reconecta con el token NUEVO y la sesión sigue", async () => {
    refresh.mockImplementation(async () => {
      useSessionStore.setState({ idToken: T2 });
      return "ok";
    });
    const ws = await conectar();
    expect(ws.tokenEnviado()).toBe(T1);

    ws.cerrar(4401);
    await flush();

    expect(refresh).toHaveBeenCalledTimes(1);
    const nuevo = ultimo();
    expect(nuevo).not.toBe(ws);
    nuevo.abrir();
    expect(nuevo.tokenEnviado()).toBe(T2);
    expect(useSessionStore.getState().status).toBe("authenticated");
  });

  it("refresh 'dead' ⇒ sesión cerrada con motivo 'expired'", async () => {
    refresh.mockResolvedValue("dead");
    const ws = await conectar();
    ws.cerrar(4401);
    await flush();
    expect(useSessionStore.getState().status).toBe("anonymous");
    expect(useSessionStore.getState().signOutReason).toBe("expired");
  });

  it("refresh 'offline' ⇒ la sesión SE QUEDA; el canal se reanuda al llegar un token nuevo", async () => {
    refresh.mockResolvedValue("offline");
    const ws = await conectar();
    ws.cerrar(4401);
    await flush();

    expect(useSessionStore.getState().status).toBe("authenticated");
    const antes = FakeWS.abiertos.length;

    // Vuelve la red: otro camino (REST, primer plano) renueva el token.
    useSessionStore.setState({ idToken: T2 });
    await flush();

    expect(FakeWS.abiertos.length).toBe(antes + 1);
    ultimo().abrir();
    expect(ultimo().tokenEnviado()).toBe(T2);
  });

  it("si el REST ya renovó después del handshake, el 4401 no gasta otro refresh", async () => {
    const ws = await conectar();
    useSessionStore.setState({ idToken: T2 }); // renovado por otro camino
    ws.cerrar(4401);
    await flush();
    expect(refresh).not.toHaveBeenCalled();
    ultimo().abrir();
    expect(ultimo().tokenEnviado()).toBe(T2);
  });
});

describe("[D-38] 4440 ⇒ fuera con motivo 'max_age', sin renovar", () => {
  it("cierra la sesión y NO pregunta a Cognito", async () => {
    const ws = await conectar();
    ws.cerrar(4440);
    await flush();
    expect(refresh).not.toHaveBeenCalled();
    expect(useSessionStore.getState().signOutReason).toBe("max_age");
  });
});

describe("el canal sigue a la sesión", () => {
  it("al cerrarse la sesión, el socket se cierra (no reintenta con un token que ya no existe)", async () => {
    const ws = await conectar();
    const cerrar = jest.spyOn(ws, "close");
    useSessionStore.getState().signOut("user");
    await flush();
    expect(cerrar).toHaveBeenCalled();
    expect(getLiveSocket().status).toBe("closed");
  });

  it("antes de conectar se pide un token fresco", async () => {
    const { ensureFreshToken } = jest.requireMock("@/auth/refresh") as {
      ensureFreshToken: jest.Mock;
    };
    await conectar();
    expect(ensureFreshToken).toHaveBeenCalled();
  });
});
