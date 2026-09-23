// Login Cognito Hosted UI + código + PKCE (patrón de la consola, llevado a
// expo-auth-session) contra el pool que corresponda al perfil (decisión #7):
// occupant → pool simple (MFA opcional) · tactical → pool principal (MFA ON).
// La push/el WS jamás son fuente de verdad de sesión: /me manda (default-deny).
import { meMeGet, type MeResponse } from "@takab/sdk";
import * as AuthSession from "expo-auth-session";
import * as WebBrowser from "expo-web-browser";
import { useEffect, useState } from "react";

import { discoveryFor, POOLS, poolConfigured, REDIRECT_URI } from "./config";
import { clearPendingAuth, setPendingAuth } from "./pendingAuth";
import { gateFor, type ProfileGroup } from "./profileGate";
import {
  pastMaxAge,
  refreshSession,
  RENEW_MARGIN_S,
  secondsLeft,
  signOutDead,
} from "./refresh";
import { clearSession, loadSession, numericClaim, saveSession } from "./secureTokens";
import { useSessionStore } from "./session.store";

/** Cuánto espera el ARRANQUE a Cognito antes de seguir con el token guardado:
 * más que esto, con la red a medias, sería dejar a alguien mirando un spinner en
 * plena alerta. El intento sigue en segundo plano y se guarda si llega. */
const BOOT_REFRESH_TIMEOUT_MS = 6_000;

/** [D-38] El tope de sesión del rol según /me (s), o `null` si no lo dice (API
 * anterior a T-8.02): sin tope conocido no hay cinturón en el cliente. */
function maxAgeFromMe(me: MeResponse): number | null {
  const v = me.session_max_age_s;
  return typeof v === "number" && Number.isFinite(v) && v > 0 ? v : null;
}

WebBrowser.maybeCompleteAuthSession();

// Un authorization code es de un solo uso. En Android el hook (WebBrowser) y la
// ruta /auth/callback (deep link) podrían intentar canjearlo ambos: registramos
// los codes ya consumidos para que el segundo camino sea un no-op idempotente.
const consumedCodes = new Set<string>();

/** Canjea el authorization code por tokens (PKCE) y resuelve la sesión vía /me.
 * Compartido por el hook (iOS: el WebBrowser intercepta el redirect) y por la
 * ruta /auth/callback (Android: el redirect llega como deep link a expo-router). */
export async function exchangeAndResolve(
  profile: ProfileGroup,
  code: string,
  codeVerifier: string,
): Promise<void> {
  if (consumedCodes.has(code)) {
    return; // ya canjeado por el otro camino
  }
  consumedCodes.add(code);
  const pool = POOLS[profile];
  const tokens = await AuthSession.exchangeCodeAsync(
    {
      clientId: pool.clientId,
      code,
      redirectUri: REDIRECT_URI,
      extraParams: { code_verifier: codeVerifier },
    },
    discoveryFor(pool),
  );
  if (!tokens.idToken) {
    throw new Error("el intercambio no devolvió id_token");
  }
  await resolveSessionFromMe(tokens.idToken, tokens.refreshToken);
}

/** Consulta /me con el token dado, aplica el gate default-deny y fija el
 * estado de sesión (+persistencia segura). Lanza si /me no responde. */
async function resolveSessionFromMe(idToken: string, refreshToken?: string): Promise<void> {
  const store = useSessionStore.getState();
  // El interceptor del SDK lee el token del store: fijarlo ANTES de /me.
  useSessionStore.setState({ idToken });
  const res = await meMeGet();
  if (!res.data) {
    // Superficie honesta del fallo: status + motivo del backend (`{detail}`),
    // no un mensaje genérico. Un 401 aquí suele ser el token rechazado por la
    // API (p.ej. audience del cliente móvil no aceptada); un 5xx/redde caída.
    const status = res.response?.status;
    const detail =
      res.error && typeof res.error === "object" && "detail" in res.error
        ? String((res.error as { detail?: unknown }).detail)
        : null;
    const suffix = [status ? `HTTP ${status}` : null, detail].filter(Boolean).join(" · ");
    throw new Error(`no se pudo verificar la sesión (/me${suffix ? ` — ${suffix}` : ""})`);
  }
  const gate = gateFor(res.data);
  if (!gate.allowed) {
    await clearSession();
    store.setDenied(gate.reason);
    return;
  }
  const now = Date.now();
  // [T-8.04 · D-38] El login REAL: `auth_time` del token (lo que la API usa para
  // su tope). Se fija AQUÍ y ningún refresh lo toca. Sin claim, la hora local.
  const authTime = numericClaim(idToken, "auth_time");
  const authAt = authTime !== null ? authTime * 1000 : now;
  const maxAgeS = maxAgeFromMe(res.data);
  await saveSession({
    profile: gate.group,
    idToken,
    refreshToken,
    issuedAt: now,
    idTokenExp: numericClaim(idToken, "exp") ?? 0,
    authAt,
    maxAgeS,
  });
  store.setAuthenticated({ profile: gate.group, idToken, me: res.data, authAt, maxAgeS });
}

/** Arranque de la app: reconstruye la sesión desde el almacén seguro y la
 * re-verifica contra /me. Sin red, la sesión cacheada se conserva con
 * `me = null` (los datos se marcan como retenidos; el refinamiento offline
 * de crisis llega con T-2.05 vía mobile-state).
 *
 * [T-8.04] Antes de /me: el cinturón del tope (D-38) y, si al token guardado le
 * quedan menos de 5 min, la renovación. Sin esto, abrir la app por la mañana
 * mandaba a /me el token de anoche, la API contestaba 401 y la sesión moría con
 * el refresh token todavía vivo. */
export async function bootstrapSession(): Promise<void> {
  const store = useSessionStore.getState();
  const stored = await loadSession();
  if (!stored) {
    store.setAnonymous();
    return;
  }
  useSessionStore.setState({
    idToken: stored.idToken,
    authAt: stored.authAt,
    maxAgeS: stored.maxAgeS,
  });
  if (pastMaxAge()) {
    store.signOut("max_age");
    return;
  }
  if (secondsLeft(stored.idToken) < RENEW_MARGIN_S) {
    const outcome = await refreshSession({ timeoutMs: BOOT_REFRESH_TIMEOUT_MS });
    if (outcome === "dead") {
      signOutDead();
      return;
    }
    // `offline`: se sigue con el token guardado; /me dirá (sin red ⇒ retenida).
  }
  /** El token vigente AHORA: el interceptor pudo renovarlo durante /me. */
  const tokenActual = (): string => useSessionStore.getState().idToken ?? stored.idToken;
  try {
    const res = await meMeGet();
    if (res.data) {
      const gate = gateFor(res.data);
      if (gate.allowed) {
        const maxAgeS = maxAgeFromMe(res.data) ?? stored.maxAgeS;
        if (maxAgeS !== stored.maxAgeS) {
          await rememberMaxAge(maxAgeS);
        }
        store.setAuthenticated({
          profile: gate.group,
          idToken: tokenActual(),
          me: res.data,
          authAt: stored.authAt,
          maxAgeS,
        });
      } else {
        await clearSession();
        store.setDenied(gate.reason);
      }
      return;
    }
    // res.error sin data: si fue un 401 sin arreglo, el interceptor ya cerró la
    // sesión; si no (sin red para renovar), queda retenida.
    if (useSessionStore.getState().status !== "anonymous") {
      store.setAuthenticated({ profile: stored.profile, idToken: tokenActual(), me: null });
    }
  } catch {
    // Sin red: sesión cacheada, honesta (me = null ⇒ la UI declara datos retenidos).
    if (useSessionStore.getState().status !== "anonymous") {
      store.setAuthenticated({ profile: stored.profile, idToken: tokenActual(), me: null });
    }
  }
}

/** Guarda el tope que dijo /me sin tocar el resto de la sesión guardada. */
async function rememberMaxAge(maxAgeS: number | null): Promise<void> {
  const current = await loadSession();
  if (current) {
    await saveSession({ ...current, maxAgeS });
  }
}

export interface LoginController {
  /** false mientras no haya config del pool o el request PKCE no esté listo. */
  ready: boolean;
  /** true si faltan EXPO_PUBLIC_* del pool — la UI lo declara, no lo esconde. */
  configured: boolean;
  error: string | null;
  /** Abre el Hosted UI del pool del perfil. */
  promptAsync: () => void;
}

/** Controlador de login por perfil (un hook por botón de la pantalla 0.1). */
export function useLogin(profile: "occupant" | "tactical"): LoginController {
  const pool = POOLS[profile];
  const configured = poolConfigured(pool);
  const discovery = discoveryFor(pool);

  const [request, response, promptAsync] = AuthSession.useAuthRequest(
    {
      clientId: pool.clientId,
      redirectUri: REDIRECT_URI,
      responseType: AuthSession.ResponseType.Code,
      scopes: ["openid", "email", "profile"],
      usePKCE: true,
    },
    discovery,
  );

  // El rechazo del proveedor es estado DERIVADO de `response` (nada de
  // setState síncrono en el effect); solo el intercambio asíncrono setea.
  const [exchangeError, setExchangeError] = useState<string | null>(null);
  const providerError =
    response?.type === "error"
      ? (response.error?.message ?? "el proveedor de identidad rechazó el login")
      : null;

  useEffect(() => {
    if (!request || response?.type !== "success") {
      return; // error se deriva arriba; dismiss/cancel no cambia estado
    }
    void (async () => {
      try {
        // iOS intercepta el redirect aquí ⇒ la ruta /auth/callback no correrá.
        clearPendingAuth();
        await exchangeAndResolve(profile, response.params.code, request.codeVerifier ?? "");
      } catch (err) {
        setExchangeError(err instanceof Error ? err.message : String(err));
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- el flujo se dispara solo al cambiar `response`
  }, [response]);

  return {
    ready: configured && request != null,
    configured,
    error: exchangeError ?? providerError,
    promptAsync: () => {
      setExchangeError(null);
      // Android: el redirect llega como deep link a /auth/callback, que necesita
      // el verifier + state para canjear el code (el hook no los verá).
      if (request?.codeVerifier) {
        setPendingAuth({ profile, codeVerifier: request.codeVerifier, state: request.state });
      }
      void promptAsync();
    },
  };
}
