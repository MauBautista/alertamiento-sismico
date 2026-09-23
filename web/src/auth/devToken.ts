import { getEnv } from "../app/env";
import { authTimeOf, jwtPayload } from "./sessionLimit";

/** Cuerpo de POST /dev/token (la API solo lo monta con JWKS inline — nunca prod). */
export interface DevTokenRequest {
  role: string;
  tenant_id: string;
  site_scope?: string;
  surface?: string;
  /**
   * [T-8.03] Identidad FIJA. Sin ella `/dev/token` inventa un `sub` nuevo en cada
   * llamada, y una renovación cambiaría de usuario a mitad de sesión.
   */
  sub?: string;
  /** Vigencia del token en segundos (la API: 1…86400, 3600 por defecto). */
  expires_in?: number;
  /**
   * [T-8.02] Edad de la sesión que el token declara: `auth_time = ahora − esto`.
   * Es lo que permite probar en local el tope de D-38 sin esperar 24 h.
   */
  auth_age_s?: number;
}

interface DevTokenResponse {
  id_token: string;
  token_use: string;
  expires_in: number;
}

export interface DevSession {
  idToken: string;
  expiresAt: number;
  /**
   * [T-8.03] Lo que hace falta para RE-EMITIR el token cuando vence: rol,
   * tenant, alcance y el `sub` que el primero trajo. Opcional porque una sesión
   * guardada antes de esta ficha no lo tiene (y entonces no se renueva).
   */
  request?: DevTokenRequest;
  /** Hora del «login» que el token declara (`auth_time`), epoch ms. */
  authTimeMs?: number;
}

/** Tope de `auth_age_s` que acepta la API (0 ≤ x ≤ 100 días). */
export const DEV_MAX_AUTH_AGE_S = 100 * 86_400;

const STORAGE_KEY = "takab.dev.session";

export async function requestDevToken(req: DevTokenRequest): Promise<DevSession> {
  const sentAt = Date.now();
  const resp = await fetch(`${getEnv().apiBaseUrl}/dev/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!resp.ok) {
    throw new Error(`POST /dev/token falló (${resp.status})`);
  }
  const body = (await resp.json()) as DevTokenResponse;
  const claims = jwtPayload(body.id_token);
  const sub = typeof claims?.sub === "string" ? claims.sub : req.sub;
  // La edad NO se guarda como parámetro: al renovar se RECALCULA desde el
  // `auth_time`, que es lo que no debe moverse.
  const { auth_age_s: edad, ...rest } = req;
  return {
    idToken: body.id_token,
    expiresAt: Date.now() + body.expires_in * 1000,
    request: sub === undefined ? rest : { ...rest, sub },
    authTimeMs: authTimeOf(body.id_token) ?? sentAt - (edad ?? 0) * 1000,
  };
}

/**
 * [T-8.03] Re-emite el token de una sesión dev CON LOS MISMOS parámetros, como
 * haría el refresco de Cognito: mismo portador y mismo `auth_time`. La edad que
 * se pide es la transcurrida desde el login, así que una sesión que ya cumplió
 * su tope sigue cumplida después de renovar — la API lo rechazará con
 * `sesion_expirada`, que es justo lo que se quiere poder probar.
 */
export async function renewDevToken(session: DevSession): Promise<DevSession> {
  if (session.request === undefined) {
    throw new Error("La sesión dev guardada no trae con qué renovarla: vuelva a entrar");
  }
  const authTimeMs = session.authTimeMs ?? Date.now();
  const age = Math.min(
    DEV_MAX_AUTH_AGE_S,
    Math.max(0, Math.round((Date.now() - authTimeMs) / 1000)),
  );
  const fresh = await requestDevToken({ ...session.request, auth_age_s: age });
  // El ancla es la de la sesión, no la del token nuevo: el redondeo a segundos
  // de cada renovación la haría derivar.
  return { ...fresh, authTimeMs };
}

/*
 * [T-8.03] La sesión DEV sigue en `sessionStorage` (por pestaña) aunque la de
 * Cognito pasó a `localStorage`: es sólo del entorno local, no hay «un día sin
 * volver a entrar» que cumplir, y `app/degraded-session.test.tsx` asserta esta
 * clave aquí — moverla dejaría esas afirmaciones pasando en vacío.
 */
export function saveDevSession(session: DevSession): void {
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  } catch {
    // Sin almacenamiento la sesión vive solo en memoria: se pierde al recargar.
  }
}

/** La sesión dev guardada, VENCIDA O NO (para poder renovarla); `null` si no hay. */
export function readDevSession(): DevSession | null {
  let raw: string | null;
  try {
    raw = window.sessionStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
  if (!raw) {
    return null;
  }
  try {
    const session = JSON.parse(raw) as DevSession;
    if (typeof session.idToken !== "string" || typeof session.expiresAt !== "number") {
      clearDevSession();
      return null;
    }
    return session;
  } catch {
    clearDevSession();
    return null;
  }
}

/** La sesión dev guardada SOLO si su token sigue vigente (la vencida se borra). */
export function loadDevSession(): DevSession | null {
  const session = readDevSession();
  if (session === null) {
    return null;
  }
  if (session.expiresAt <= Date.now()) {
    clearDevSession();
    return null;
  }
  return session;
}

export function clearDevSession(): void {
  try {
    window.sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // Nada que borrar si no hay dónde.
  }
}
