import { create } from "zustand";

import { getEnv } from "../app/env";
import { hardRedirect } from "../app/navigation";
import {
  clearDevSession,
  loadDevSession,
  requestDevToken,
  saveDevSession,
  type DevTokenRequest,
} from "./devToken";
import { getMe, MeRequestError, type MeResponse } from "./me";
import { buildLogoutUrl, cognitoConfigured, getUserManager } from "./userManager";

/**
 * `degraded` [T-2.123]: hay token, pero `GET /me` no contesta por algo que no es
 * un 401 (5xx, red). Desde que `T-2.114` ató `/me` a la base, ese "no contesta"
 * es sobre todo *Postgres caído*, y no puede tratarse ni como sesión válida ni
 * como sesión cerrada: es **alcance desconocido**. La consola arranca igual y lo
 * declara, sin pintar dato de tenant alguno — el porqué completo está en
 * `app/DegradedSessionScreen.tsx`.
 */
export type SessionStatus =
  | "booting"
  | "anonymous"
  | "authenticating"
  | "authenticated"
  | "degraded"
  /** Sin productor desde `T-2.123`: el único fallo de `/me` que existía ahora es
   * `degraded`. Sobrevive porque `RequireSession`/`LoginPage` aún ramifican por
   * él; se retira junto con `pages/StatusScreens.tsx::ErrorScreen`. NO usar para
   * fallos nuevos sin decidir antes qué declara la pantalla. */
  | "error";

export interface SessionState {
  status: SessionStatus;
  origin: "cognito" | "dev" | null;
  /** ID token vigente (la API exige token_use="id"); cache síncrono del interceptor. */
  idToken: string | null;
  me: MeResponse | null;
  error: string | null;
  bootstrap: () => Promise<void>;
  loginCognito: (returnTo?: string) => Promise<void>;
  completeCognitoCallback: () => Promise<{ returnTo?: string }>;
  loginDev: (req: DevTokenRequest) => Promise<void>;
  refreshMe: () => Promise<void>;
  logout: () => Promise<void>;
  handleUnauthorized: () => void;
}

// Latches a nivel módulo: StrictMode monta dos veces y el callback OIDC es one-shot.
let bootstrapOnce: Promise<void> | null = null;
let callbackOnce: Promise<{ returnTo?: string }> | null = null;
let eventsWired = false;

const CLEARED = {
  status: "anonymous" as const,
  origin: null,
  idToken: null,
  me: null,
  error: null,
};

export const useSessionStore = create<SessionState>()((set, get) => {
  function clearSession(): void {
    clearDevSession();
    set(CLEARED);
  }

  async function fetchMe(): Promise<void> {
    try {
      const me = await getMe();
      set({ status: "authenticated", me, error: null });
    } catch (err) {
      if (err instanceof MeRequestError && err.status === 401) {
        get().handleUnauthorized();
        return;
      }
      // [T-2.123] Alcance desconocido, NO sesión cerrada. `me: null` es la mitad
      // que hace segura a la otra: si un `/me` viejo sobreviviera al fallo, los
      // guards seguirían abriendo rutas con un alcance que ya nadie puede
      // reverificar — adivinarlo es la brecha multi-tenant (regla de oro 5).
      set({
        status: "degraded",
        me: null,
        error: err instanceof Error ? err.message : String(err),
      });
    }
  }

  function wireCognitoEvents(): void {
    if (eventsWired) {
      return;
    }
    eventsWired = true;
    const um = getUserManager();
    um.events.addUserLoaded((user) => {
      if (user.id_token) {
        set({ idToken: user.id_token });
      }
    });
    um.events.addAccessTokenExpired(() => {
      um.signinSilent().catch(() => get().handleUnauthorized());
    });
    um.events.addSilentRenewError(() => get().handleUnauthorized());
  }

  async function runBootstrap(): Promise<void> {
    if (getEnv().devTokenEnabled) {
      const dev = loadDevSession();
      if (dev) {
        set({ origin: "dev", idToken: dev.idToken });
        await fetchMe();
        return;
      }
    }
    if (cognitoConfigured()) {
      try {
        const user = await getUserManager().getUser();
        if (user && !user.expired && user.id_token) {
          wireCognitoEvents();
          set({ origin: "cognito", idToken: user.id_token });
          await fetchMe();
          return;
        }
      } catch {
        // Sesión OIDC irrecuperable ⇒ anónimo.
      }
    }
    clearSession();
  }

  async function runCallback(): Promise<{ returnTo?: string }> {
    const user = await getUserManager().signinRedirectCallback();
    if (!user.id_token) {
      throw new Error("El callback OIDC no trajo id_token");
    }
    wireCognitoEvents();
    set({ status: "authenticating", origin: "cognito", idToken: user.id_token });
    await fetchMe();
    const state = user.state as { returnTo?: string } | undefined;
    return { returnTo: state?.returnTo };
  }

  return {
    status: "booting",
    origin: null,
    idToken: null,
    me: null,
    error: null,

    bootstrap: () => {
      bootstrapOnce ??= runBootstrap();
      return bootstrapOnce;
    },

    loginCognito: async (returnTo) => {
      if (!cognitoConfigured()) {
        throw new Error("Cognito no está configurado (VITE_COGNITO_*)");
      }
      set({ status: "authenticating", error: null });
      await getUserManager().signinRedirect(returnTo ? { state: { returnTo } } : undefined);
    },

    completeCognitoCallback: () => {
      callbackOnce ??= runCallback().catch((err: unknown) => {
        clearSession();
        throw err;
      });
      return callbackOnce;
    },

    loginDev: async (req) => {
      set({ status: "authenticating", error: null });
      const session = await requestDevToken(req).catch((err: unknown) => {
        clearSession();
        throw err;
      });
      saveDevSession(session);
      set({ origin: "dev", idToken: session.idToken });
      await fetchMe();
    },

    refreshMe: async () => {
      // [T-2.123] Desde el degradado NO se pasa por "booting": eso desmontaría la
      // pantalla que está declarando el problema y remontaría el router entero en
      // cada reintento. El botón lleva su propio indicador.
      if (get().status !== "degraded") {
        set({ status: "booting", error: null });
      }
      await fetchMe();
    },

    logout: async () => {
      const { origin } = get();
      clearSession();
      if (origin === "cognito") {
        try {
          await getUserManager().removeUser();
        } catch {
          // El redirect al Hosted UI cierra la sesión igual.
        }
        hardRedirect(buildLogoutUrl());
      }
    },

    handleUnauthorized: () => {
      const { origin } = get();
      clearSession();
      if (origin === "cognito") {
        void getUserManager()
          .removeUser()
          .catch(() => undefined);
      }
    },
  };
});

/** Solo tests: resetea estado y latches de módulo entre casos. */
export function resetSessionStoreForTests(): void {
  bootstrapOnce = null;
  callbackOnce = null;
  eventsWired = false;
  useSessionStore.setState({ ...CLEARED, status: "booting" });
}
