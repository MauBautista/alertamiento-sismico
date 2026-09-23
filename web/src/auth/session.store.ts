import { create } from "zustand";

import { getEnv } from "../app/env";
import { hardRedirect } from "../app/navigation";
import {
  clearDevSession,
  readDevSession,
  renewDevToken,
  requestDevToken,
  saveDevSession,
  type DevSession,
  type DevTokenRequest,
} from "./devToken";
import { getMe, MeRequestError, type MeResponse } from "./me";
import {
  authTimeOf,
  effectiveDeadline,
  forgetSessionWindow,
  MAX_TIMER_MS,
  parseInstant,
  readSessionWindow,
  recordLogin,
  recordMaxAge,
} from "./sessionLimit";
import { buildLogoutUrl, cognitoConfigured, getUserManager } from "./userManager";

/**
 * Por qué terminó una sesión que el operador no cerró:
 * - `expired`: el servidor dejó de reconocer el token y renovarlo no funcionó
 *   (expiró o fue revocado; desde aquí no se distinguen).
 * - `max_age`: [T-8.03 · D-38] la sesión cumplió la edad máxima de su rol
 *   (24 h / 30 días desde el login). Renovar no sirve: hay que volver a entrar.
 */
export type SessionEndReason = "expired" | "max_age";

/**
 * `degraded` [T-2.123]: hay token, pero `GET /me` no contesta por algo que no es
 * un 401 (5xx, red). Desde que `T-2.114` ató `/me` a la base, ese "no contesta"
 * es sobre todo *Postgres caído*, y no puede tratarse ni como sesión válida ni
 * como sesión cerrada: es **alcance desconocido**. La consola arranca igual y lo
 * declara, sin pintar dato de tenant alguno — el porqué completo está en
 * `app/DegradedSessionScreen.tsx`.
 */
/*
 * [T-2.134] `"error"` SE RETIRÓ DE ESTE UNION, con `pages/StatusScreens.tsx::
 * ErrorScreen` y la rama de `LoginPage` que lo miraba.
 *
 * `T-2.123` lo dejó sin productor —convirtió el único fallo de `/me` que existía
 * en `degraded`— y con un aviso escrito en vez de retirarlo, por no invadir
 * ficheros ajenos. Medido ahora: cero escrituras en producción, dos lectores
 * (`RequireSession` y `LoginPage`) y una pantalla entera (`ErrorScreen`) que
 * ningún camino podía alcanzar.
 *
 * Un estado muerto no es inocuo: se lee como una rama viva, así que quien
 * mantenga esto creerá que existe un modo de fallo con su propia pantalla, y
 * quien añada un fallo nuevo lo enchufará ahí «porque ya está» — sin decidir qué
 * declara esa pantalla, que es exactamente la decisión que `T-2.123` tomó con
 * razones. El fallo de `/me` tiene UNA conducta acordada y una sola pantalla que
 * la explica: `DegradedSessionScreen`.
 *
 * La guardia que impide que vuelva un estado sin escritor es el censo de
 * `session.store.test.ts`: todo miembro de este union tiene que tener productor
 * en el código de producción.
 */
export type SessionStatus =
  | "booting"
  | "anonymous"
  | "authenticating"
  | "authenticated"
  | "degraded";

export interface SessionState {
  status: SessionStatus;
  origin: "cognito" | "dev" | null;
  /**
   * [T-6.07] POR QUÉ terminó la sesión anterior, para que la landing lo diga.
   *
   * La sesión expiraba EN SILENCIO: `signinSilent` falla, `handleUnauthorized`
   * limpia, y el operador aparece en un login idéntico al de un arranque en
   * frío, sin una palabra. Vuelve a entrar sin saber que le habían echado.
   *
   * Es un CAMPO y no un miembro de `SessionStatus` a propósito: el estado
   * sigue siendo `anonymous` —eso es lo que es— y el censo de
   * `session.store.test.ts` exige productor real para cada miembro del union.
   * Un estado nuevo por cada causa haría crecer la máquina sin necesidad.
   */
  endedReason: SessionEndReason | null;
  /** ID token vigente (la API exige token_use="id"); cache síncrono del interceptor. */
  idToken: string | null;
  me: MeResponse | null;
  error: string | null;
  /** [T-8.03] `session_expires_at` de `/me` (epoch ms); `null` si no lo dijo. */
  sessionExpiresAt: number | null;
  /**
   * [T-8.03] `session_max_age_s` de `/me`. SOBREVIVE al fin por tope (`max_age`):
   * la landing lo necesita para decir «SU SESIÓN DE 24 H TERMINÓ» cuando `me` ya
   * no existe.
   */
  sessionMaxAgeS: number | null;
  /** [T-8.03] Hora del login (epoch ms): la base del cinturón del cliente. */
  loginAt: number | null;
  bootstrap: () => Promise<void>;
  loginCognito: (returnTo?: string) => Promise<void>;
  completeCognitoCallback: () => Promise<{ returnTo?: string }>;
  loginDev: (req: DevTokenRequest) => Promise<void>;
  refreshMe: () => Promise<void>;
  logout: () => Promise<void>;
  /**
   * [T-8.03] Renueva el ID token (Cognito: refresh; dev: re-emisión con los
   * mismos parámetros) y lo deja en el store. De VUELO ÚNICO: el 4401 del canal
   * live y los 401 simultáneos del REST comparten una sola renovación. `null` si
   * no se pudo — o si la sesión ya cumplió su tope, que no se renueva.
   */
  renewToken: () => Promise<string | null>;
  /**
   * [T-8.03] Un 401 que NO es el tope: UN intento de renovar por token. `true`
   * si hay (o ya había) un token nuevo con el que seguir; `false` si la sesión
   * terminó (y entonces ya quedó cerrada con su causa).
   */
  recoverFromUnauthorized: (failedToken: string | null) => Promise<boolean>;
  handleUnauthorized: (reason?: SessionEndReason) => void;
}

/**
 * [T-8.03] Plazo efectivo de la sesión (epoch ms): el menor entre lo que dijo
 * `/me` y la marca del login + la edad máxima. `null` sin datos — no se inventa.
 */
export function selectSessionDeadline(
  s: Pick<SessionState, "sessionExpiresAt" | "loginAt" | "sessionMaxAgeS">,
): number | null {
  return effectiveDeadline({
    expiresAt: s.sessionExpiresAt,
    loginAt: s.loginAt,
    maxAgeS: s.sessionMaxAgeS,
  });
}

// Latches a nivel módulo: StrictMode monta dos veces y el callback OIDC es one-shot.
let bootstrapOnce: Promise<void> | null = null;
let callbackOnce: Promise<{ returnTo?: string }> | null = null;
let eventsWired = false;
/** [T-8.03] Renovación en vuelo: todos los que la piden a la vez la comparten. */
let renewing: Promise<string | null> | null = null;
/** [T-8.03] Último token obtenido POR un 401: si él también da 401, no hay bucle. */
let lastRecoveredToken: string | null = null;
/** [T-8.03] Temporizador del cinturón (fin por tope aunque el servidor calle). */
let deadlineTimer: ReturnType<typeof setTimeout> | null = null;

/**
 * [T-8.03] Cuánto se espera a que Cognito confirme la revocación antes de seguir
 * cerrando. SALIR no puede quedarse colgado de una red que no contesta: la
 * revocación es higiene (el refresh ya se borra del navegador de todos modos).
 */
const REVOKE_TIMEOUT_MS = 3_000;

const CLEARED = {
  status: "anonymous" as const,
  origin: null,
  idToken: null,
  me: null,
  error: null,
  // Por defecto NINGUNA causa: un `logout` deliberado no es una expiración, y
  // decirle «su sesión expiró» a quien acaba de pulsar SALIR es ruido.
  endedReason: null,
  sessionExpiresAt: null,
  sessionMaxAgeS: null,
  loginAt: null,
};

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  return Promise.race([
    promise,
    new Promise<T>((_, reject) => {
      timer = setTimeout(() => reject(new Error("tiempo agotado")), ms);
    }),
  ]).finally(() => clearTimeout(timer));
}

/**
 * [T-8.03] Suelta el usuario OIDC: revoca el refresh en Cognito y lo borra del
 * navegador, EN ESE ORDEN (borrado primero, ya no habría qué revocar).
 *
 * La revocación se hace aquí, a mano, porque `revokeTokensOnSignout` de
 * oidc-client-ts solo actúa dentro de `signoutRedirect`/`signoutPopup`, y el
 * SALIR de esta consola no pasa por ahí (Cognito no publica `end_session_endpoint`:
 * se sale por el /logout del Hosted UI). Sin esto, el refresh de 30 días de un
 * `localStorage` seguiría valiendo en Cognito después de cerrar sesión.
 */
async function dropCognitoUser(): Promise<void> {
  const um = getUserManager();
  try {
    await withTimeout(um.revokeTokens(["refresh_token"]), REVOKE_TIMEOUT_MS);
  } catch {
    // Mejor esfuerzo: sin red, el refresh igualmente deja de estar en el navegador.
  }
  try {
    await um.removeUser();
  } catch {
    // El redirect al Hosted UI cierra la sesión igual.
  }
}

export const useSessionStore = create<SessionState>()((set, get) => {
  function disarmDeadline(): void {
    if (deadlineTimer !== null) {
      clearTimeout(deadlineTimer);
      deadlineTimer = null;
    }
  }

  function deadlinePassed(): boolean {
    const deadline = selectSessionDeadline(get());
    return deadline !== null && deadline <= Date.now();
  }

  /**
   * [T-8.03] EL CINTURÓN: al cumplirse el plazo efectivo, fin por tope aunque
   * el servidor todavía no lo haya dicho (si Cognito moviera `auth_time` al
   * refrescar, el servidor no lo diría nunca). Se arma a TROZOS de como mucho
   * `MAX_TIMER_MS`: una sesión de 30 días armada de un golpe desbordaría el
   * entero de `setTimeout` y se cerraría en el acto.
   */
  function armDeadline(): void {
    disarmDeadline();
    const tick = (): void => {
      deadlineTimer = null;
      const deadline = selectSessionDeadline(get());
      if (deadline === null || get().idToken === null) {
        return;
      }
      const left = deadline - Date.now();
      if (left <= 0) {
        get().handleUnauthorized("max_age");
        return;
      }
      deadlineTimer = setTimeout(tick, Math.min(left, MAX_TIMER_MS));
    };
    tick();
  }

  function clearSession(): void {
    clearDevSession();
    disarmDeadline();
    lastRecoveredToken = null;
    set(CLEARED);
  }

  async function fetchMe(retried = false): Promise<void> {
    const sent = get().idToken;
    try {
      const me = await getMe();
      if (sent !== null && get().idToken === null) {
        // La sesión terminó mientras `/me` viajaba (un 401 del tope en paralelo,
        // el cinturón): no se resucita con una respuesta que ya llegó tarde.
        return;
      }
      const maxAgeS = me.session_max_age_s ?? null;
      if (get().origin === "cognito") {
        recordMaxAge(maxAgeS);
      }
      // Entrar otra vez cierra el episodio: la causa no puede sobrevivir a la
      // sesión siguiente y volver a aparecer meses después.
      set({
        status: "authenticated",
        me,
        error: null,
        endedReason: null,
        sessionExpiresAt: parseInstant(me.session_expires_at),
        sessionMaxAgeS: maxAgeS,
      });
      armDeadline();
    } catch (err) {
      if (err instanceof MeRequestError && err.status === 401) {
        // [T-8.03] El tope NO se renueva; el token vencido sí, UNA vez.
        if (err.sessionExpired) {
          get().handleUnauthorized("max_age");
          return;
        }
        const recovered = await get().recoverFromUnauthorized(sent);
        if (!recovered) {
          return; // ya quedó cerrada, con su causa
        }
        if (retried) {
          get().handleUnauthorized("expired");
          return;
        }
        await fetchMe(true);
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
      // [T-8.03] Solo mientras la sesión sea de Cognito: revocar el refresh al
      // salir EMITE un userLoaded, y sin esta guarda resucitaba el token de una
      // sesión que acababa de cerrarse (y el canal live volvía a abrirse).
      if (user.id_token && get().origin === "cognito") {
        set({ idToken: user.id_token });
      }
    });
    um.events.addAccessTokenExpired(() => {
      if (get().origin !== "cognito") {
        return;
      }
      void get()
        .renewToken()
        .then((token) => {
          if (token === null && get().idToken !== null) {
            get().handleUnauthorized("expired");
          }
        });
    });
    // [T-8.03] `addSilentRenewError` ya no cierra la sesión: el fallo de la
    // renovación AUTOMÁTICA llega un minuto antes del `exp`, con el token aún
    // válido, y cerrar ahí revocaba el refresh por un parpadeo de red. El token
    // vencido lo recogen el `accessTokenExpired` de arriba, el 401 del REST y el
    // 4401 del canal live, cada uno con UN reintento antes de cerrar.
  }

  /** [T-8.03] Sesión dev: la guardada, re-emitida si su token venció. */
  async function resumeDevSession(): Promise<DevSession | null> {
    const stored = readDevSession();
    if (stored === null) {
      return null;
    }
    if (stored.expiresAt > Date.now()) {
      return stored;
    }
    try {
      const fresh = await renewDevToken(stored);
      saveDevSession(fresh);
      return fresh;
    } catch {
      clearDevSession();
      return null;
    }
  }

  async function runBootstrap(): Promise<void> {
    if (getEnv().devTokenEnabled) {
      const dev = await resumeDevSession();
      if (dev) {
        set({ origin: "dev", idToken: dev.idToken, loginAt: dev.authTimeMs ?? null });
        await fetchMe();
        return;
      }
    }
    if (cognitoConfigured()) {
      try {
        let user = await getUserManager().getUser();
        if (user && user.id_token) {
          const stored = readSessionWindow();
          set({ loginAt: stored.loginAt, sessionMaxAgeS: stored.maxAgeS });
          // [T-8.03] El cinturón ANTES que nada: una sesión que ya cumplió su
          // tope no se renueva (Cognito lo haría y la API rechazaría en bucle).
          if (deadlinePassed()) {
            set({ origin: "cognito" });
            get().handleUnauthorized("max_age");
            return;
          }
          if (user.expired) {
            // [T-8.03 · A-033] Con la sesión en localStorage, reabrir el navegador
            // más de 60 min después encuentra el ID token vencido y el refresh
            // vivo: se renueva antes de declararse anónimo.
            if (!user.refresh_token) {
              clearSession();
              return;
            }
            user = await getUserManager()
              .signinSilent()
              .catch(() => null);
            if (!user?.id_token) {
              set({ origin: "cognito" });
              get().handleUnauthorized("expired");
              return;
            }
          }
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
    // [T-8.03] LA HORA DEL LOGIN, que el refresco no puede mover: la del token
    // (`auth_time`) si la trae, la de la vuelta si no. Es el cinturón por si
    // Cognito renovara `auth_time` al refrescar (A-006, sin medir).
    const loginAt = authTimeOf(user.id_token) ?? Date.now();
    recordLogin(loginAt);
    wireCognitoEvents();
    set({
      status: "authenticating",
      origin: "cognito",
      idToken: user.id_token,
      loginAt,
      sessionExpiresAt: null,
      sessionMaxAgeS: null,
    });
    await fetchMe();
    const state = user.state as { returnTo?: string } | undefined;
    return { returnTo: state?.returnTo };
  }

  /** [T-8.03] Una renovación de verdad (la de vuelo único la envuelve). */
  async function doRenew(): Promise<string | null> {
    const { origin } = get();
    if (origin === null) {
      return null;
    }
    if (deadlinePassed()) {
      get().handleUnauthorized("max_age");
      return null;
    }
    try {
      if (origin === "cognito") {
        const user = await getUserManager().signinSilent();
        const token = user?.id_token ?? null;
        if (token === null || get().origin !== "cognito") {
          return null;
        }
        set({ idToken: token });
        return token;
      }
      const stored = readDevSession();
      if (stored === null) {
        return null;
      }
      const fresh = await renewDevToken(stored);
      if (get().origin !== "dev") {
        return null; // la sesión terminó mientras se renovaba
      }
      saveDevSession(fresh);
      set({ idToken: fresh.idToken });
      return fresh.idToken;
    } catch {
      return null;
    }
  }

  return {
    status: "booting",
    origin: null,
    idToken: null,
    me: null,
    error: null,
    endedReason: null,
    sessionExpiresAt: null,
    sessionMaxAgeS: null,
    loginAt: null,

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
      set({ origin: "dev", idToken: session.idToken, loginAt: session.authTimeMs ?? null });
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
      forgetSessionWindow();
      if (origin === "cognito") {
        await dropCognitoUser();
        hardRedirect(buildLogoutUrl());
      }
    },

    renewToken: () => {
      renewing ??= doRenew().finally(() => {
        renewing = null;
      });
      return renewing;
    },

    recoverFromUnauthorized: async (failedToken) => {
      const { idToken } = get();
      if (idToken === null) {
        return false; // no hay sesión que recuperar: ya terminó (o nunca hubo)
      }
      if (deadlinePassed()) {
        get().handleUnauthorized("max_age");
        return false;
      }
      if (failedToken === null || failedToken !== idToken) {
        return true; // esa petición salió con un token que ya se reemplazó
      }
      if (failedToken === lastRecoveredToken) {
        // El token que YA se obtuvo renovando también da 401: renovar otra vez
        // sería un bucle. Se cierra.
        get().handleUnauthorized("expired");
        return false;
      }
      const fresh = await get().renewToken();
      if (fresh === null) {
        if (get().idToken !== null) {
          get().handleUnauthorized("expired");
        }
        return false;
      }
      lastRecoveredToken = fresh;
      return true;
    },

    handleUnauthorized: (reason = "expired") => {
      const { origin, idToken, endedReason, sessionMaxAgeS } = get();
      // [T-8.03] Un «expirada» que llega DESPUÉS del tope (el canal live que cae
      // tras el 401 del REST) no puede rebajar la causa: el operador tiene que
      // leer que la sesión cumplió su tope, no que «se cerró».
      if (reason === "expired" && idToken === null && endedReason === "max_age") {
        return;
      }
      const maxAgeS =
        reason === "max_age"
          ? (sessionMaxAgeS ?? (origin === "cognito" ? readSessionWindow().maxAgeS : null))
          : null;
      clearSession();
      forgetSessionWindow();
      // DESPUÉS de limpiar: `clearSession` deja la causa en null como debe, y
      // esta es la única que la enciende. La landing solo la LEE; quien la
      // apaga es el `/me` de la sesión siguiente, en `fetchMe`.
      set({ endedReason: reason, sessionMaxAgeS: maxAgeS });
      if (origin === "cognito") {
        void dropCognitoUser();
      }
    },
  };
});

/** Solo tests: resetea estado y latches de módulo entre casos. */
export function resetSessionStoreForTests(): void {
  bootstrapOnce = null;
  callbackOnce = null;
  eventsWired = false;
  renewing = null;
  lastRecoveredToken = null;
  if (deadlineTimer !== null) {
    clearTimeout(deadlineTimer);
    deadlineTimer = null;
  }
  useSessionStore.setState({ ...CLEARED, status: "booting" });
}
