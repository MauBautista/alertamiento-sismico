// [T-8.04 · A-001/A-002/A-005/A-007/A-009] Renovación de la sesión móvil.
//
// Medido antes de esta ficha: `useAuth.ts` guardaba el refresh token de Cognito
// y NINGÚN código lo usaba. El ID token vive 60 min; al vencer, el primer 401
// (REST) o el 4401 (WS) cerraban la sesión y la app volvía a pedir contraseña —y
// TOTP a los tácticos— cada hora, aunque el refresh token siguiera vivo 30 días.
//
// Aquí vive la ÚNICA forma de renovar:
//   · `refreshSession()` — vuelo único (llamadas concurrentes comparten la misma
//     promesa: con rotación, dos canjes paralelos del mismo refresh token pueden
//     matar la sesión) y TRES salidas, de las que sólo una expulsa:
//       `ok`      token nuevo guardado en el almacén seguro y en el store;
//       `dead`    Cognito rechazó el grant (RFC 6749 §5.2), no hay refresh token,
//                 o la sesión pasó el tope de su rol (D-38): hay que volver a entrar;
//       `offline` no se pudo preguntar (red, timeout, error del servidor): la
//                 sesión SE CONSERVA — la app ya sabe mostrar datos retenidos.
//   · `ensureFreshToken()` — barato: compara `exp` y sólo renueva si hace falta.
//   · el CINTURÓN del cliente (D-38): pasado `authAt + maxAgeS` la sesión está
//     muerta aunque el servidor no lo haya dicho todavía. Es independiente del
//     tope de la API a propósito: si Cognito renovara `auth_time` en cada refresh
//     (A-006, NO MEDIDO), el tope del servidor no saltaría nunca; éste sí, porque
//     `authAt` se fija en el login y ningún refresh lo toca.
//
// Quién decide expulsar NO es este módulo: devuelve `dead` y el que llama hace
// `signOutDead()` (así el 401 del aviso de privacidad puede seguir sin expulsar).
import * as AuthSession from "expo-auth-session";

import { discoveryFor, POOLS, poolConfigured } from "./config";
import { loadSession, numericClaim, saveSession } from "./secureTokens";
import { useSessionStore } from "./session.store";

export type RefreshOutcome = "ok" | "dead" | "offline";

/** Se renueva cuando al ID token le quedan menos de 5 min (A-002 §2). */
export const RENEW_MARGIN_S = 300;
/** Cuánto espera por Cognito quien NO puede seguir sin token (arranque,
 * interceptor con el token ya vencido). El intento sigue vivo después. */
export const REFRESH_TIMEOUT_MS = 12_000;
/** Tras un fallo de red, ensureFreshToken no vuelve a preguntar durante esto:
 * sin él, cada sondeo de 30 s sin cobertura sería otro intento contra Cognito. */
const OFFLINE_COOLDOWN_MS = 15_000;
/** Tras un éxito, ensureFreshToken no vuelve a renovar durante esto: un reloj
 * del teléfono muy adelantado vería vencido cada token nuevo (tormenta de refresh). */
const RECENT_SUCCESS_MS = 60_000;

/** Errores del token endpoint que prueban que ESTE refresh no va a funcionar
 * nunca (RFC 6749 §5.2). Cualquier otra cosa se trata como transitoria. */
const GRANT_REJECTED: ReadonlySet<string> = new Set([
  "invalid_grant",
  "invalid_client",
  "unauthorized_client",
  "unsupported_grant_type",
  "invalid_request",
  "invalid_scope",
]);

let attempt: Promise<RefreshOutcome> | null = null;
let lastOfflineAt = 0;
let lastOkAt = 0;

/** Reset SOLO para tests. */
export function resetRefreshForTests(): void {
  attempt = null;
  lastOfflineAt = 0;
  lastOkAt = 0;
}

/** Segundos de vida que le quedan a un ID token según su `exp` (reloj del
 * teléfono). Ilegible o ausente ⇒ `-Infinity`: cuenta como vencido. */
export function secondsLeft(idToken: string | null, nowMs: number = Date.now()): number {
  if (!idToken) {
    return -Infinity;
  }
  const exp = numericClaim(idToken, "exp");
  return exp === null ? -Infinity : exp - nowMs / 1000;
}

function pastMaxAgeOf(authAt: number | null, maxAgeS: number | null, nowMs: number): boolean {
  if (authAt === null || maxAgeS === null || authAt <= 0 || maxAgeS <= 0) {
    return false; // tope desconocido: sin cinturón (nadie fuera por actualizar)
  }
  return nowMs - authAt > maxAgeS * 1000;
}

/** [D-38] ¿La sesión en curso pasó la edad máxima de su rol? */
export function pastMaxAge(nowMs: number = Date.now()): boolean {
  const { authAt, maxAgeS } = useSessionStore.getState();
  return pastMaxAgeOf(authAt, maxAgeS, nowMs);
}

/** Cierra la sesión muerta con el motivo correcto: `max_age` si fue el tope, si
 * no `expired`. Es lo que hace quien recibe `dead`. */
export function signOutDead(): void {
  useSessionStore.getState().signOut(pastMaxAge() ? "max_age" : "expired");
}

function isRejectedGrant(err: unknown): boolean {
  if (typeof err !== "object" || err === null) {
    return false;
  }
  const e = err as { code?: unknown; params?: { error?: unknown } };
  const code = typeof e.code === "string" ? e.code : e.params?.error;
  return typeof code === "string" && GRANT_REJECTED.has(code);
}

/** Una sesión cerrada (o reemplazada) durante el vuelo no se resucita. */
function sessionGone(): boolean {
  const { status } = useSessionStore.getState();
  return status === "anonymous" || status === "denied";
}

async function performRefresh(): Promise<RefreshOutcome> {
  const stored = await loadSession();
  if (!stored || !stored.refreshToken) {
    return "dead";
  }
  if (pastMaxAgeOf(stored.authAt, stored.maxAgeS, Date.now())) {
    return "dead"; // ni se pregunta a Cognito: renovar no alarga el tope
  }
  const pool = POOLS[stored.profile];
  if (!poolConfigured(pool)) {
    return "dead";
  }
  let tokens: AuthSession.TokenResponse;
  try {
    tokens = await AuthSession.refreshAsync(
      { clientId: pool.clientId, refreshToken: stored.refreshToken },
      discoveryFor(pool),
    );
  } catch (err) {
    if (isRejectedGrant(err)) {
      return "dead";
    }
    lastOfflineAt = Date.now();
    return "offline";
  }
  if (!tokens.idToken) {
    // Respuesta anómala (p.ej. un 5xx con cuerpo raro): no prueba que la sesión
    // murió, así que no se expulsa a nadie por ella.
    lastOfflineAt = Date.now();
    return "offline";
  }
  if (sessionGone()) {
    return "dead";
  }
  const current = await loadSession();
  if (!current || current.refreshToken !== stored.refreshToken || sessionGone()) {
    return sessionGone() ? "dead" : "ok"; // otra sesión ocupó su lugar: no se pisa
  }
  const idToken = tokens.idToken;
  useSessionStore.setState({ idToken });
  lastOkAt = Date.now();
  lastOfflineAt = 0;
  try {
    await saveSession({
      profile: current.profile,
      idToken,
      // Con rotación llega uno nuevo; sin ella, el de siempre sigue valiendo.
      refreshToken: tokens.refreshToken ?? current.refreshToken,
      issuedAt: current.issuedAt,
      idTokenExp:
        numericClaim(idToken, "exp") ?? Math.floor(Date.now() / 1000) + (tokens.expiresIn ?? 3600),
      authAt: current.authAt, // el tope cuenta desde el login REAL
      maxAgeS: current.maxAgeS,
    });
  } catch (err) {
    // La memoria ya tiene el token: esta sesión funciona. El próximo arranque
    // renovará con lo que haya en el almacén.
    console.warn("auth: no se pudo persistir el token renovado", err);
  }
  return "ok";
}

function withTimeout(p: Promise<RefreshOutcome>, ms: number): Promise<RefreshOutcome> {
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      lastOfflineAt = Date.now();
      resolve("offline");
    }, ms);
    void p.then(
      (v) => {
        clearTimeout(timer);
        resolve(v);
      },
      () => {
        clearTimeout(timer);
        resolve("offline");
      },
    );
  });
}

/**
 * Renueva el ID token con el refresh token de Cognito. Vuelo único: mientras un
 * intento está en marcha, cualquier otra llamada se suma a él.
 *
 * `timeoutMs` acota cuánto espera ESTE llamante (⇒ `offline`), no el intento: si
 * Cognito contesta tarde, el token se guarda igual — con rotación, tirar esa
 * respuesta perdería el refresh token nuevo y el viejo moriría tras la gracia.
 */
export function refreshSession(opts: { timeoutMs?: number } = {}): Promise<RefreshOutcome> {
  if (attempt === null) {
    const current = performRefresh().catch((): RefreshOutcome => {
      lastOfflineAt = Date.now();
      return "offline";
    });
    attempt = current;
    void current.finally(() => {
      if (attempt === current) {
        attempt = null;
      }
    });
  }
  return withTimeout(attempt, opts.timeoutMs ?? REFRESH_TIMEOUT_MS);
}

/**
 * Renueva SÓLO si al token le quedan menos de `minValidityS`. Sin sesión ⇒
 * `dead` (no hay nada que renovar); pasado el tope ⇒ `dead`.
 */
export function ensureFreshToken(
  minValidityS: number = RENEW_MARGIN_S,
  opts: { timeoutMs?: number } = {},
): Promise<RefreshOutcome> {
  const { idToken } = useSessionStore.getState();
  if (!idToken || pastMaxAge()) {
    return Promise.resolve("dead");
  }
  if (secondsLeft(idToken) >= minValidityS) {
    return Promise.resolve("ok");
  }
  const now = Date.now();
  if (attempt === null && now - lastOkAt < RECENT_SUCCESS_MS) {
    return Promise.resolve("ok");
  }
  if (attempt === null && now - lastOfflineAt < OFFLINE_COOLDOWN_MS) {
    return Promise.resolve("offline");
  }
  return refreshSession(opts);
}

/** Traer la app al frente: cinturón primero, luego renovar si hace falta. Sin
 * red la sesión se queda; sólo `dead` la cierra. */
export async function onAppForeground(): Promise<void> {
  const s = useSessionStore.getState();
  if (s.status !== "authenticated") {
    return;
  }
  if (pastMaxAge()) {
    s.signOut("max_age");
    return;
  }
  const outcome = await ensureFreshToken(RENEW_MARGIN_S);
  if (outcome === "dead") {
    signOutDead();
  }
}

/** Lo que este módulo necesita de `AppState` de React Native. */
export interface ForegroundSource {
  addEventListener(tipo: "change", cb: (estado: string) => void): { remove(): void };
}

/** Ata `onAppForeground` a la vuelta a primer plano (`active`). Devuelve la
 * función para soltarlo. `inactive` (centro de control, llamada) no cuenta. */
export function wireSessionToForeground(appState: ForegroundSource): () => void {
  let prev: string | null = null;
  const sub = appState.addEventListener("change", (estado) => {
    if (estado === "inactive") {
      return;
    }
    if (estado === "active" && prev !== "active") {
      void onAppForeground();
    }
    prev = estado;
  });
  return () => sub.remove();
}
