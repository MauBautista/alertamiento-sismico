// El 401 que cierra la sesión es un cerrojo más, y hay que saber cuál lo dispara.
//
// `app/index.tsx:34` es el ÚNICO sitio de la app que reacciona a quedarse sin
// sesión, y durante el onboarding esa ruta no está montada: el stack de
// `app/onboarding/` no tiene guarda. Así que un `signOut()` disparado ahí no
// lleva a nadie al login — deja a la persona en la pantalla, sin token y sin
// avisar. Para un occupant eso es una trampa: el paso siguiente (enrolamiento)
// necesita sesión viva para canjear el código, nunca la completa y por tanto
// nunca se marca el onboarding como hecho ⇒ no llega al check-in de vida ni al
// botón de pánico.
//
// El aviso de privacidad es una llamada de CUMPLIMIENTO. Darle el poder de
// cerrar sesiones invierte exactamente la prioridad de las reglas de oro 1 y 2.
import { client } from "@takab/sdk";

import { configureApiClient } from "./sdk";

jest.mock("@takab/sdk", () => ({
  client: {
    setConfig: jest.fn(),
    interceptors: {
      request: { use: jest.fn() },
      response: { use: jest.fn() },
    },
  },
}));

jest.mock("../auth/session.store", () => ({
  useSessionStore: {
    getState: () => ({ idToken: "tok", signOut: mockSignOut }),
  },
}));

const mockSignOut = jest.fn();

type Interceptor = (response: { status: number }, request: { url: string }) => unknown;

let alResponder: Interceptor;

beforeAll(() => {
  configureApiClient();
  alResponder = (client.interceptors.response.use as jest.Mock).mock.calls[0][0] as Interceptor;
});

beforeEach(() => {
  mockSignOut.mockClear();
});

function responder(status: number, path: string): void {
  alResponder({ status }, { url: `https://api.takab.test${path}` });
}

describe("interceptor de respuesta — quién puede cerrar la sesión", () => {
  it("un 401 de una ruta de la que la app DEPENDE cierra la sesión", () => {
    responder(401, "/me");
    expect(mockSignOut).toHaveBeenCalledTimes(1);
  });

  it("un 401 del aviso de privacidad NO cierra la sesión", () => {
    // Si la cerrara, un defecto de permisos en un endpoint de cumplimiento
    // expulsaría a toda la flota del onboarding —en silencio, sin siquiera
    // mandarla al login— antes de llegar al check-in de vida.
    responder(401, "/privacy/consent");
    expect(mockSignOut).not.toHaveBeenCalled();
  });

  it("tampoco lo hace el 401 del texto del aviso ni el del historial", () => {
    responder(401, "/privacy/notice?purpose=app_mobile");
    responder(401, "/privacy/consent/history");
    expect(mockSignOut).not.toHaveBeenCalled();
  });

  it("un token realmente caducado SIGUE muriendo: la siguiente ruta real lo cierra", () => {
    // La exención no resucita sesiones: solo mueve el sitio donde se declaran
    // muertas a una ruta que la app sí necesita.
    responder(401, "/privacy/consent");
    responder(401, "/mobile/site/state");
    expect(mockSignOut).toHaveBeenCalledTimes(1);
  });

  it("un 403 no expulsa (es autorización fina del backend)", () => {
    responder(403, "/me");
    expect(mockSignOut).not.toHaveBeenCalled();
  });

  it("una respuesta buena no toca la sesión", () => {
    responder(200, "/me");
    expect(mockSignOut).not.toHaveBeenCalled();
  });
});
