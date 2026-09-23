// Cliente único del SDK — espejo de web/src/auth/apiClient.ts:
// baseUrl + Bearer del store + SOLO el 401 puede cerrar sesión (un 403 es
// autorización fina del backend y no expulsa), y ni siquiera todos: los del
// aviso de privacidad no expulsan (ver `RUTAS_QUE_NO_CIERRAN_SESION`). La app
// móvil no duplica clientes HTTP fuera de @takab/sdk (spec §13.5).
//
// [T-8.04 · A-001/A-005] Un 401 ya NO es una expulsión: es una pregunta.
//   · antes de mandar, el token se renueva si está por vencer (barato: compara
//     `exp`; sólo ESPERA si ya no sirve);
//   · 401 `sesion_expirada` (D-38: la sesión cumplió la edad de su rol) ⇒ fuera
//     con motivo `max_age`, sin intentar renovar — renovar no la revive;
//   · cualquier otro 401 ⇒ UNA renovación; sólo `dead` expulsa, `offline`
//     conserva la sesión y con `ok` una LECTURA se repite con el token nuevo.
import { client } from "@takab/sdk";

import { API_BASE_URL } from "../auth/config";
import {
  ensureFreshToken,
  refreshSession,
  RENEW_MARGIN_S,
  type RefreshOutcome,
  secondsLeft,
  signOutDead,
} from "../auth/refresh";
import { useSessionStore } from "../auth/session.store";

/** Rutas cuyo 401 NO cierra la sesión.
 *
 * El aviso de privacidad es CUMPLIMIENTO, no sesión. Si su 401 pudiera cerrar
 * la sesión, un defecto de permisos en ese endpoint expulsaría a toda la flota
 * durante el onboarding — y en silencio: `app/index.tsx:34` es el único sitio
 * que reacciona a quedarse anónimo, y el stack de `app/onboarding/` no lo tiene
 * montado, así que nadie va al login. Un occupant se quedaría además atascado
 * en enrolamiento (canjear el código exige sesión viva) y no llegaría nunca al
 * check-in de vida ni al botón de pánico (reglas de oro 1 y 2).
 *
 * Esto no resucita sesiones: un token de verdad caducado se declara muerto en
 * la siguiente ruta de la que la app SÍ depende (`/me`, estado del sitio,
 * check-in). Solo se le quita a la vía de cumplimiento el poder de expulsar.
 */
const RUTAS_QUE_NO_CIERRAN_SESION = ["/privacy/consent", "/privacy/notice"];

/** Por debajo de esto el token ya no sirve para mandar: la petición ESPERA a la
 * renovación. Entre esto y `RENEW_MARGIN_S` se renueva en segundo plano y la
 * petición sale con el token actual, que todavía vale. */
const ESPERAR_BAJO_S = 30;
/** Cuánto espera una petición a Cognito con el token ya vencido. */
const ESPERA_MAXIMA_MS = 8_000;

/** Métodos que se pueden repetir tras renovar: no llevan cuerpo que ya se
 * consumió y no cambian nada en el servidor. */
const METODOS_REPETIBLES = new Set(["GET", "HEAD"]);

function cierraSesion(url: string): boolean {
  return !RUTAS_QUE_NO_CIERRAN_SESION.some((ruta) => url.includes(ruta));
}

/** El contrato de T-8.02: cabecera `WWW-Authenticate … error_description=
 * "sesion_expirada"` o cuerpo `{"detail": "sesion_expirada"}`. El cuerpo se lee
 * de un CLON: el original lo sigue parseando el SDK. */
async function esSesionExpirada(response: Response): Promise<boolean> {
  const www = response.headers.get("WWW-Authenticate") ?? "";
  if (/error_description="?sesion_expirada"?/.test(www)) {
    return true;
  }
  try {
    const body: unknown = await response.clone().json();
    return (
      typeof body === "object" &&
      body !== null &&
      (body as { detail?: unknown }).detail === "sesion_expirada"
    );
  } catch {
    return false;
  }
}

function bearerDe(request: Request): string | null {
  const h = request.headers.get("Authorization");
  return h?.startsWith("Bearer ") ? h.slice("Bearer ".length) : null;
}

let configured = false;

export function configureApiClient(): void {
  if (configured) {
    return;
  }
  configured = true;
  client.setConfig({ baseUrl: API_BASE_URL });

  client.interceptors.request.use(async (request) => {
    if (useSessionStore.getState().idToken) {
      // Si falta poco, arranca la renovación sin esperarla (vuelo único)…
      const enFondo = ensureFreshToken(RENEW_MARGIN_S);
      // …y sólo si el token ya no sirve, espera (se suma al mismo vuelo).
      const ahora = await ensureFreshToken(ESPERAR_BAJO_S, { timeoutMs: ESPERA_MAXIMA_MS });
      const declararSiMuerta = (r: RefreshOutcome) => {
        if (r === "dead" && cierraSesion(request.url)) {
          signOutDead();
        }
      };
      if (ahora === "dead") {
        declararSiMuerta(ahora);
      } else {
        void enFondo.then(declararSiMuerta);
      }
    }
    const { idToken } = useSessionStore.getState();
    if (idToken) {
      request.headers.set("Authorization", `Bearer ${idToken}`);
    }
    return request;
  });

  client.interceptors.response.use(async (response, request, options) => {
    if (response.status !== 401 || !cierraSesion(request.url)) {
      return response;
    }
    if (await esSesionExpirada(response)) {
      useSessionStore.getState().signOut("max_age");
      return response;
    }
    // ¿Otro camino ya renovó después de que esta petición saliera? Entonces el
    // 401 es del token viejo y no hace falta gastar otro refresh.
    const usado = bearerDe(request);
    const actual = useSessionStore.getState().idToken;
    const yaRenovado =
      actual !== null && usado !== null && actual !== usado && secondsLeft(actual) > ESPERAR_BAJO_S;
    const outcome: RefreshOutcome = yaRenovado ? "ok" : await refreshSession();
    if (outcome === "dead") {
      signOutDead();
      return response;
    }
    if (outcome === "offline" || !METODOS_REPETIBLES.has(request.method.toUpperCase())) {
      // Sin red: la sesión se queda. Una escritura no se repite aquí (su cuerpo
      // ya se consumió): la reintenta quien la hizo (React Query, cola offline).
      return response;
    }
    const nuevo = useSessionStore.getState().idToken;
    if (!nuevo) {
      return response;
    }
    const headers = new Headers(request.headers);
    headers.set("Authorization", `Bearer ${nuevo}`);
    try {
      const doFetch = options.fetch ?? globalThis.fetch;
      const repetida = await doFetch(new Request(request.url, { method: request.method, headers }));
      if (repetida.status === 401) {
        // Un token RECIÉN renovado y aun así rechazado: la sesión no sirve.
        if (await esSesionExpirada(repetida)) {
          useSessionStore.getState().signOut("max_age");
        } else {
          signOutDead();
        }
      }
      return repetida;
    } catch {
      return response; // la repetición falló por red: se devuelve el 401 original
    }
  });
}
