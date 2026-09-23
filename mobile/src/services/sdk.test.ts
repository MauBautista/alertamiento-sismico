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
//
// [T-8.04 · A-001/A-005] UN 401 YA NO ES UNA EXPULSIÓN, ES UNA PREGUNTA.
//
// Hasta esta ficha el primer 401 hacía `signOut()`. El ID token vive 60 min, así
// que a la hora exacta la app pedía contraseña (y TOTP a los tácticos) aunque el
// refresh token siguiera vivo 30 días. Ahora:
//   · `sesion_expirada` (D-38: la sesión cumplió la edad de su rol) ⇒ fuera con
//     motivo `max_age`, SIN intentar renovar: renovar no la revive;
//   · cualquier otro 401 ⇒ se renueva UNA vez; sólo `dead` expulsa, `offline`
//     conserva la sesión, y con `ok` una lectura (GET) se repite con el token nuevo.
import { client } from "@takab/sdk";

import { ensureFreshToken, refreshSession, secondsLeft, signOutDead } from "../auth/refresh";
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
    getState: () => ({ idToken: mockEstado.idToken, signOut: mockSignOut }),
  },
}));

jest.mock("../auth/refresh", () => ({
  RENEW_MARGIN_S: 300,
  ensureFreshToken: jest.fn(async () => "ok"),
  refreshSession: jest.fn(async () => "dead"),
  secondsLeft: jest.fn(() => 3000),
  signOutDead: jest.fn(),
}));

const mockSignOut = jest.fn();
const mockEstado: { idToken: string | null } = { idToken: "tok" };

const refresh = refreshSession as jest.Mock;
const ensureFresh = ensureFreshToken as jest.Mock;
const restante = secondsLeft as jest.Mock;
const muerta = signOutDead as jest.Mock;

type ResInterceptor = (
  response: Response,
  request: Request,
  options: { fetch?: (r: Request) => Promise<Response> },
) => Promise<Response>;
type ReqInterceptor = (request: Request) => Promise<Request>;

let alResponder: ResInterceptor;
let alPedir: ReqInterceptor;
const reintento = jest.fn<Promise<Response>, [Request]>();

beforeAll(() => {
  configureApiClient();
  alPedir = (client.interceptors.request.use as jest.Mock).mock.calls[0][0] as ReqInterceptor;
  alResponder = (client.interceptors.response.use as jest.Mock).mock.calls[0][0] as ResInterceptor;
});

beforeEach(() => {
  jest.clearAllMocks();
  mockEstado.idToken = "tok";
  refresh.mockResolvedValue("dead");
  ensureFresh.mockResolvedValue("ok");
  restante.mockReturnValue(3000);
  reintento.mockResolvedValue(new Response("{}", { status: 200 }));
});

function peticion(path: string, init: RequestInit = {}, token = "tok"): Request {
  return new Request(`https://api.takab.test${path}`, {
    ...init,
    headers: { Authorization: `Bearer ${token}` },
  });
}

function respuesta(status: number, body: unknown = {}, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), { status, headers });
}

async function responder(status: number, path: string, init: RequestInit = {}) {
  return alResponder(respuesta(status), peticion(path, init), { fetch: reintento });
}

describe("interceptor de respuesta — quién puede cerrar la sesión", () => {
  it("un 401 de una ruta de la que la app DEPENDE pregunta primero; si el refresh murió, cierra", async () => {
    await responder(401, "/me");
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(muerta).toHaveBeenCalledTimes(1);
  });

  it("un 401 del aviso de privacidad NO cierra la sesión", async () => {
    // Si la cerrara, un defecto de permisos en un endpoint de cumplimiento
    // expulsaría a toda la flota del onboarding —en silencio, sin siquiera
    // mandarla al login— antes de llegar al check-in de vida.
    await responder(401, "/privacy/consent");
    expect(muerta).not.toHaveBeenCalled();
    expect(mockSignOut).not.toHaveBeenCalled();
  });

  it("tampoco lo hace el 401 del texto del aviso ni el del historial", async () => {
    await responder(401, "/privacy/notice?purpose=app_mobile");
    await responder(401, "/privacy/consent/history");
    expect(muerta).not.toHaveBeenCalled();
    expect(mockSignOut).not.toHaveBeenCalled();
  });

  it("un token realmente caducado SIGUE muriendo: la siguiente ruta real lo cierra", async () => {
    // La exención no resucita sesiones: solo mueve el sitio donde se declaran
    // muertas a una ruta que la app sí necesita.
    await responder(401, "/privacy/consent");
    await responder(401, "/mobile/site/state");
    expect(muerta).toHaveBeenCalledTimes(1);
  });

  it("un 403 no expulsa (es autorización fina del backend)", async () => {
    await responder(403, "/me");
    expect(refresh).not.toHaveBeenCalled();
    expect(muerta).not.toHaveBeenCalled();
  });

  it("una respuesta buena no toca la sesión", async () => {
    await responder(200, "/me");
    expect(refresh).not.toHaveBeenCalled();
    expect(muerta).not.toHaveBeenCalled();
  });
});

describe("[T-8.04] 401 ⇒ renovar, y sólo 'dead' expulsa", () => {
  it("refresh 'ok' ⇒ NO se cierra la sesión", async () => {
    refresh.mockResolvedValue("ok");
    await responder(401, "/mobile/site/state");
    expect(muerta).not.toHaveBeenCalled();
    expect(mockSignOut).not.toHaveBeenCalled();
  });

  it("refresh 'offline' ⇒ la sesión se conserva y la respuesta sigue su camino", async () => {
    refresh.mockResolvedValue("offline");
    const r = await responder(401, "/mobile/site/state");
    expect(r.status).toBe(401);
    expect(muerta).not.toHaveBeenCalled();
    expect(mockSignOut).not.toHaveBeenCalled();
  });

  it("con 'ok', una LECTURA se repite UNA vez con el token nuevo y se devuelve esa respuesta", async () => {
    refresh.mockImplementation(async () => {
      mockEstado.idToken = "tok-nuevo";
      return "ok";
    });
    reintento.mockResolvedValue(respuesta(200, { ok: true }));

    const r = await responder(401, "/sites/abc/mobile-state");

    expect(reintento).toHaveBeenCalledTimes(1);
    const repetida = reintento.mock.calls[0][0];
    expect(repetida.method).toBe("GET");
    expect(repetida.url).toBe("https://api.takab.test/sites/abc/mobile-state");
    expect(repetida.headers.get("Authorization")).toBe("Bearer tok-nuevo");
    expect(r.status).toBe(200);
  });

  it("una ESCRITURA no se repite (su cuerpo ya se consumió): la reintenta quien la hizo", async () => {
    refresh.mockResolvedValue("ok");
    const r = await responder(401, "/incidents/1/checkins", {
      method: "POST",
      body: JSON.stringify({ a: 1 }),
    });
    expect(reintento).not.toHaveBeenCalled();
    expect(r.status).toBe(401);
    expect(muerta).not.toHaveBeenCalled();
  });

  it("si la lectura repetida con token RECIÉN renovado vuelve a dar 401, la sesión está muerta", async () => {
    refresh.mockResolvedValue("ok");
    reintento.mockResolvedValue(respuesta(401));
    await responder(401, "/me");
    expect(muerta).toHaveBeenCalledTimes(1);
  });

  it("si otro camino YA renovó (la petición llevaba el token viejo), no se gasta otro refresh", async () => {
    mockEstado.idToken = "tok-ya-nuevo";
    restante.mockReturnValue(3000);
    await alResponder(respuesta(401), peticion("/me", {}, "tok-viejo"), { fetch: reintento });
    expect(refresh).not.toHaveBeenCalled();
    expect(reintento).toHaveBeenCalledTimes(1);
    expect(reintento.mock.calls[0][0].headers.get("Authorization")).toBe("Bearer tok-ya-nuevo");
  });
});

describe("[T-8.04 · D-38] sesion_expirada ⇒ fuera con motivo, SIN renovar", () => {
  it("por la cabecera WWW-Authenticate", async () => {
    const r = respuesta(401, { detail: "otra cosa" }, {
      "WWW-Authenticate": 'Bearer error="invalid_token", error_description="sesion_expirada"',
    });
    await alResponder(r, peticion("/me"), { fetch: reintento });
    expect(mockSignOut).toHaveBeenCalledWith("max_age");
    expect(refresh).not.toHaveBeenCalled();
  });

  it("por el cuerpo {detail: 'sesion_expirada'}", async () => {
    await alResponder(respuesta(401, { detail: "sesion_expirada" }), peticion("/me"), {
      fetch: reintento,
    });
    expect(mockSignOut).toHaveBeenCalledWith("max_age");
    expect(refresh).not.toHaveBeenCalled();
  });

  it("el cuerpo sigue legible después (el SDK lo parsea para el error)", async () => {
    const r = await alResponder(respuesta(401, { detail: "sesion_expirada" }), peticion("/me"), {
      fetch: reintento,
    });
    await expect(r.json()).resolves.toEqual({ detail: "sesion_expirada" });
  });

  it("un 401 del aviso de privacidad con sesion_expirada tampoco expulsa desde ahí", async () => {
    await alResponder(respuesta(401, { detail: "sesion_expirada" }), peticion("/privacy/consent"), {
      fetch: reintento,
    });
    expect(mockSignOut).not.toHaveBeenCalled();
  });
});

describe("[T-8.04] interceptor de petición — no mandar tokens vencidos", () => {
  it("renueva (si hace falta) ANTES de poner el Bearer, y pone el token resultante", async () => {
    ensureFresh.mockImplementation(async () => {
      mockEstado.idToken = "tok-renovado";
      return "ok";
    });
    const req = await alPedir(new Request("https://api.takab.test/me"));
    expect(ensureFresh).toHaveBeenCalled();
    expect(req.headers.get("Authorization")).toBe("Bearer tok-renovado");
  });

  it("sin sesión no pregunta a nadie ni pone cabecera", async () => {
    mockEstado.idToken = null;
    const req = await alPedir(new Request("https://api.takab.test/health"));
    expect(ensureFresh).not.toHaveBeenCalled();
    expect(req.headers.get("Authorization")).toBeNull();
  });

  it("si al renovar resulta que la sesión está muerta, se declara (salvo en rutas exentas)", async () => {
    ensureFresh.mockResolvedValue("dead");
    await alPedir(new Request("https://api.takab.test/mobile/site/state"));
    expect(muerta).toHaveBeenCalledTimes(1);
    await alPedir(new Request("https://api.takab.test/privacy/consent"));
    expect(muerta).toHaveBeenCalledTimes(1);
  });
});
