// [T-8.04 · D-38] El cierre de sesión DICE POR QUÉ.
//
// Hasta esta ficha `signOut()` era mudo: la pantalla de login no podía distinguir
// «usted cerró sesión» de «su sesión de 30 días terminó» ni de «el servidor
// rechazó el token». La razón queda en el store (`signOutReason`) para que la
// pinte quien la necesite.
//
// Y la PRIMERA causa gana: tras un 401 `sesion_expirada`, el socket vivo se
// entera después (getToken ⇒ null ⇒ `expired`). Si ese segundo aviso pisara al
// primero, la pantalla diría «caducó el token» cuando lo que pasó es que se
// cumplió el mes.
import { useSessionStore } from "./session.store";

jest.mock("expo-secure-store", () => ({
  getItemAsync: jest.fn(async () => null),
  setItemAsync: jest.fn(async () => undefined),
  deleteItemAsync: jest.fn(async () => undefined),
}));

const ME = { role: "brigadista", surface: "mobile" } as never;

function autenticar(): void {
  useSessionStore
    .getState()
    .setAuthenticated({ profile: "tactical", idToken: "tok", me: ME, authAt: 1_000, maxAgeS: 60 });
}

beforeEach(() => {
  useSessionStore.setState({
    status: "booting",
    profile: null,
    idToken: null,
    me: null,
    deniedReason: null,
    signOutReason: null,
    authAt: null,
    maxAgeS: null,
  });
});

describe("signOut(motivo)", () => {
  it("deja el motivo legible y vacía la sesión", () => {
    autenticar();
    useSessionStore.getState().signOut("max_age");
    const s = useSessionStore.getState();
    expect(s.status).toBe("anonymous");
    expect(s.signOutReason).toBe("max_age");
    expect(s.idToken).toBeNull();
    expect(s.authAt).toBeNull();
    expect(s.maxAgeS).toBeNull();
  });

  it("sin motivo cuenta como cierre del USUARIO", () => {
    autenticar();
    useSessionStore.getState().signOut();
    expect(useSessionStore.getState().signOutReason).toBe("user");
  });

  it("`onPress={signOut}` pasa el EVENTO del toque: también es cierre del usuario", () => {
    // `denied.tsx` y `AccountScreen` lo cablean así; el evento no es un motivo.
    autenticar();
    const signOut = useSessionStore.getState().signOut as (e: object) => void;
    signOut({ nativeEvent: {} });
    expect(useSessionStore.getState().signOutReason).toBe("user");
  });

  it("la PRIMERA causa gana: un segundo aviso no reescribe el motivo", () => {
    autenticar();
    useSessionStore.getState().signOut("max_age");
    useSessionStore.getState().signOut("expired");
    expect(useSessionStore.getState().signOutReason).toBe("max_age");
  });

  it("volver a entrar limpia el motivo anterior", () => {
    autenticar();
    useSessionStore.getState().signOut("expired");
    autenticar();
    expect(useSessionStore.getState().signOutReason).toBeNull();
    expect(useSessionStore.getState().authAt).toBe(1_000);
    expect(useSessionStore.getState().maxAgeS).toBe(60);
  });
});
