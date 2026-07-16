// Login Cognito Hosted UI + código + PKCE (patrón de la consola, llevado a
// expo-auth-session) contra el pool que corresponda al perfil (decisión #7):
// occupant → pool simple (MFA opcional) · tactical → pool principal (MFA ON).
// La push/el WS jamás son fuente de verdad de sesión: /me manda (default-deny).
import { meMeGet } from "@takab/sdk";
import * as AuthSession from "expo-auth-session";
import * as WebBrowser from "expo-web-browser";
import { useEffect, useState } from "react";

import { discoveryFor, POOLS, poolConfigured, REDIRECT_URI } from "./config";
import { gateFor } from "./profileGate";
import { clearSession, loadSession, saveSession } from "./secureTokens";
import { useSessionStore } from "./session.store";

WebBrowser.maybeCompleteAuthSession();

/** Consulta /me con el token dado, aplica el gate default-deny y fija el
 * estado de sesión (+persistencia segura). Lanza si /me no responde. */
async function resolveSessionFromMe(idToken: string, refreshToken?: string): Promise<void> {
  const store = useSessionStore.getState();
  // El interceptor del SDK lee el token del store: fijarlo ANTES de /me.
  useSessionStore.setState({ idToken });
  const res = await meMeGet();
  if (!res.data) {
    throw new Error("no se pudo verificar la sesión (/me)");
  }
  const gate = gateFor(res.data);
  if (!gate.allowed) {
    await clearSession();
    store.setDenied(gate.reason);
    return;
  }
  await saveSession({
    profile: gate.group,
    idToken,
    refreshToken,
    issuedAt: Date.now(),
  });
  store.setAuthenticated({ profile: gate.group, idToken, me: res.data });
}

/** Arranque de la app: reconstruye la sesión desde el almacén seguro y la
 * re-verifica contra /me. Sin red, la sesión cacheada se conserva con
 * `me = null` (los datos se marcan como retenidos; el refinamiento offline
 * de crisis llega con T-2.05 vía mobile-state). */
export async function bootstrapSession(): Promise<void> {
  const store = useSessionStore.getState();
  const stored = await loadSession();
  if (!stored) {
    store.setAnonymous();
    return;
  }
  useSessionStore.setState({ idToken: stored.idToken });
  try {
    const res = await meMeGet();
    if (res.data) {
      const gate = gateFor(res.data);
      if (gate.allowed) {
        store.setAuthenticated({ profile: gate.group, idToken: stored.idToken, me: res.data });
      } else {
        await clearSession();
        store.setDenied(gate.reason);
      }
      return;
    }
    // res.error sin data: si fue 401, el interceptor ya cerró la sesión.
    if (useSessionStore.getState().status !== "anonymous") {
      store.setAuthenticated({ profile: stored.profile, idToken: stored.idToken, me: null });
    }
  } catch {
    // Sin red: sesión cacheada, honesta (me = null ⇒ la UI declara datos retenidos).
    store.setAuthenticated({ profile: stored.profile, idToken: stored.idToken, me: null });
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
        const tokens = await AuthSession.exchangeCodeAsync(
          {
            clientId: pool.clientId,
            code: response.params.code,
            redirectUri: REDIRECT_URI,
            extraParams: { code_verifier: request.codeVerifier ?? "" },
          },
          discovery,
        );
        if (!tokens.idToken) {
          throw new Error("el intercambio no devolvió id_token");
        }
        await resolveSessionFromMe(tokens.idToken, tokens.refreshToken);
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
      void promptAsync();
    },
  };
}
