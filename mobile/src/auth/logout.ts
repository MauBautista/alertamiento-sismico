// [T-8.04 · A-020] Cerrar sesión DE VERDAD — el botón «Cerrar sesión».
//
// `signOut(motivo)` del store es el cierre LOCAL (lo usan el 401 y el 4401: sin
// red ni navegador). Éste es el del usuario, y además de borrar el almacén
// apaga lo que el cierre local dejaba vivo:
//   1. el token push de ESTE aparato (`DELETE /me/push-tokens/{id}`): si no, el
//      teléfono de alguien que ya no está sigue recibiendo las alertas del edificio;
//   2. el refresh token en Cognito (`/oauth2/revoke`): con los 30/90 días de D-38,
//      un refresh olvidado es una sesión de un mes esperando a quien lo encuentre;
//   3. la cookie de la Hosted UI (`/logout` del dominio del pool): si no, el
//      siguiente «INICIAR SESIÓN» entra con la identidad ANTERIOR sin pedir nada
//      (medido en el Pixel, T-7.56). `prompt=login` NO sirve de sustituto: AWS
//      sólo lo honra en «managed login», y los dos dominios son
//      `managed_login_version = 1` (Hosted UI clásica, identity/main.tf).
//   4. por último, el almacén y el estado (`signOut("user")`).
//
// Best-effort y en ese orden: ningún paso que falle impide el siguiente, cada
// uno tiene tope de tiempo, y el paso 4 corre SIEMPRE (finally).
//
// ⚠️ ANDROID: el paso 3 vuelve por el deep link `takab://auth/logout`, que llega
// a expo-router como navegación igual que `/auth/callback`. Sin una ruta
// `app/auth/logout.tsx` (un `<Redirect href="/" />` basta) Android pinta
// «Unmatched Route» al terminar. Esa ruta NO es de esta ficha (reparto de
// ficheros): quien cablee `logout()` en la pantalla de Cuenta tiene que crearla.
import * as AuthSession from "expo-auth-session";
import * as WebBrowser from "expo-web-browser";

import { unregisterOwnPushToken } from "@/services/push";

import { discoveryFor, LOGOUT_URI, POOLS, poolConfigured } from "./config";
import { loadSession } from "./secureTokens";
import { useSessionStore } from "./session.store";

export interface LogoutReport {
  /** Baja del token push propio. `skipped` = no había sesión con la que pedirla. */
  push: "revoked" | "none" | "error" | "skipped";
  /** `sent`: Cognito contestó al revoke. `expo-auth-session` no mira el código
   * HTTP de esa respuesta, así que «contestó» es lo único que se puede afirmar. */
  refresh: "sent" | "none" | "error";
  /** `closed`: la Hosted UI volvió por `LOGOUT_URI`; `dismissed`: la persona
   * cerró el navegador antes; `skipped`: sin red o sin pool configurado. */
  hostedUi: "closed" | "dismissed" | "timeout" | "skipped" | "error";
}

const PUSH_TIMEOUT_MS = 6_000;
const REVOKE_TIMEOUT_MS = 6_000;
const HOSTED_UI_TIMEOUT_MS = 10_000;

const TIMEOUT = Symbol("timeout");

function conTope<T>(p: Promise<T>, ms: number): Promise<T | typeof TIMEOUT> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  return Promise.race([
    p,
    new Promise<typeof TIMEOUT>((resolve) => {
      timer = setTimeout(() => resolve(TIMEOUT), ms);
    }),
  ]).finally(() => clearTimeout(timer));
}

/** Un fallo de RED (no una respuesta rara): sin red no tiene sentido abrir un
 * navegador que se quedaría en blanco hasta el tope. */
const esFalloDeRed = (err: unknown): boolean => err instanceof TypeError;

let enCurso: Promise<LogoutReport> | null = null;

/** Cierre de sesión explícito del usuario. Dos toques seguidos ⇒ una secuencia. */
export function logout(opts: { hostedUiTimeoutMs?: number } = {}): Promise<LogoutReport> {
  if (enCurso === null) {
    enCurso = secuencia(opts.hostedUiTimeoutMs ?? HOSTED_UI_TIMEOUT_MS).finally(() => {
      enCurso = null;
    });
  }
  return enCurso;
}

async function secuencia(hostedUiTimeoutMs: number): Promise<LogoutReport> {
  const informe: LogoutReport = { push: "skipped", refresh: "none", hostedUi: "skipped" };
  try {
    const stored = await loadSession().catch(() => null);
    const profile = stored?.profile ?? useSessionStore.getState().profile;
    const pool = profile ? POOLS[profile] : null;

    // 1 · push — mientras la sesión sigue viva (el DELETE lleva Bearer).
    if (useSessionStore.getState().idToken) {
      try {
        const r = await conTope(unregisterOwnPushToken(), PUSH_TIMEOUT_MS);
        informe.push = r === TIMEOUT ? "error" : r;
      } catch {
        informe.push = "error";
      }
    }

    // 2 · revocar el refresh token del pool que lo emitió.
    let sinRed = false;
    if (stored?.refreshToken && pool && poolConfigured(pool)) {
      try {
        const r = await conTope(
          AuthSession.revokeAsync(
            {
              token: stored.refreshToken,
              clientId: pool.clientId,
              tokenTypeHint: AuthSession.TokenTypeHint.RefreshToken,
            },
            { revocationEndpoint: discoveryFor(pool).revocationEndpoint },
          ),
          REVOKE_TIMEOUT_MS,
        );
        sinRed = r === TIMEOUT;
        informe.refresh = r === TIMEOUT ? "error" : "sent";
      } catch (err) {
        if (err instanceof SyntaxError) {
          // Cognito contestó con cuerpo vacío y el cliente intentó leerlo como JSON.
          informe.refresh = "sent";
        } else {
          sinRed = esFalloDeRed(err);
          informe.refresh = "error";
        }
      }
    }

    // 3 · la cookie de la Hosted UI de ESE dominio.
    if (!sinRed && pool && poolConfigured(pool)) {
      informe.hostedUi = await cerrarHostedUi(
        pool.hostedUiDomain,
        pool.clientId,
        hostedUiTimeoutMs,
      );
    }
  } finally {
    // 4 · SIEMPRE: el almacén y el estado (cierra también el canal live).
    useSessionStore.getState().signOut("user");
  }
  return informe;
}

async function cerrarHostedUi(
  domain: string,
  clientId: string,
  timeoutMs: number,
): Promise<LogoutReport["hostedUi"]> {
  const url =
    `https://${domain}/logout?client_id=${encodeURIComponent(clientId)}` +
    `&logout_uri=${encodeURIComponent(LOGOUT_URI)}`;
  try {
    const r = await conTope(WebBrowser.openAuthSessionAsync(url, LOGOUT_URI), timeoutMs);
    if (r === TIMEOUT) {
      // Sin esto la sesión del navegador quedaría abierta y el siguiente login
      // fallaría con «WebBrowser is already open».
      try {
        WebBrowser.dismissAuthSession();
      } catch {
        // no había nada que descartar
      }
      return "timeout";
    }
    return r.type === "success" ? "closed" : "dismissed";
  } catch {
    return "error";
  }
}
