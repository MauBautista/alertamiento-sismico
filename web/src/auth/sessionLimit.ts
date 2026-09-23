// [T-8.03 · D-38] EL TOPE DE LA SESIÓN, visto desde la consola.
//
// La API impone la edad máxima de la sesión por rol contando desde `auth_time`
// (la hora del login con contraseña y código, que el refresco NO renueva): 24 h
// para los roles de mesa, 30 días para brigadista e inspector. Cuando se cumple
// responde 401 con `sesion_expirada` y el canal live cierra con 4440.
//
// Aquí vive lo que la consola necesita para NO pelearse con ese tope:
//
//   · reconocer el 401 del tope y distinguirlo de un token vencido. Son dos
//     cosas distintas y se tratan al revés: el token vencido se RENUEVA; el tope
//     NO, porque Cognito seguiría refrescando y la API rechazaría en bucle.
//   · la marca del login en `localStorage`, que es el CINTURÓN: si Cognito
//     renovara `auth_time` al refrescar (A-006, sin medir), `session_expires_at`
//     de `/me` avanzaría con cada refresco y el tope no llegaría nunca. La hora
//     del primer login no se mueve.
//   · el plazo efectivo = el MENOR de los dos. Ninguno de los dos se inventa: sin
//     dato, no hay plazo (y no se pinta aviso).
//
// Todo acceso a `localStorage` va envuelto: en una ventana privada o con el
// almacenamiento bloqueado lanza, y una consola que muere al leer una marca
// auxiliar es peor que una que simplemente no tiene cinturón.

/** Lo que la API escribe en el 401 del tope (cuerpo `detail` y `error_description`). */
export const SESION_EXPIRADA = "sesion_expirada";

const WINDOW_KEY = "takab.session.window";

/**
 * `setTimeout` guarda el retraso en un entero de 32 bits: por encima de
 * 2^31-1 ms (24.8 días) DESBORDA y dispara al instante. Una sesión de 30 días
 * armada de un golpe se cerraría en el acto; por eso el temporizador se arma a
 * trozos de como mucho esto.
 */
export const MAX_TIMER_MS = 2 ** 31 - 1;

/** ¿La cabecera `WWW-Authenticate` es la del tope de sesión? */
export function isSessionExpiredHeader(value: string | null): boolean {
  if (value === null) {
    return false;
  }
  return /error_description\s*=\s*"?sesion_expirada"?/i.test(value);
}

/** ¿El cuerpo del 401 es el del tope (`{"detail": "sesion_expirada"}`)? */
export function isSessionExpiredBody(body: unknown): boolean {
  return (
    typeof body === "object" &&
    body !== null &&
    (body as { detail?: unknown }).detail === SESION_EXPIRADA
  );
}

/**
 * ¿Esta respuesta es el 401 del tope? Mira la cabecera primero (el contrato la
 * trae siempre) y el cuerpo solo si falta, sobre un CLON: el cuerpo original lo
 * sigue necesitando quien hizo la petición.
 */
export async function isSessionExpiredResponse(response: Response): Promise<boolean> {
  if (response.status !== 401) {
    return false;
  }
  if (isSessionExpiredHeader(response.headers.get("WWW-Authenticate"))) {
    return true;
  }
  try {
    return isSessionExpiredBody(await response.clone().json());
  } catch {
    return false;
  }
}

/** Claims de un JWT SIN verificar: solo para leer datos del propio portador. */
export function jwtPayload(token: string): Record<string, unknown> | null {
  const part = token.split(".")[1];
  if (part === undefined || part === "") {
    return null;
  }
  try {
    const b64 = part.replace(/-/g, "+").replace(/_/g, "/");
    const padded = b64 + "=".repeat((4 - (b64.length % 4)) % 4);
    const json = new TextDecoder().decode(Uint8Array.from(atob(padded), (c) => c.charCodeAt(0)));
    const payload: unknown = JSON.parse(json);
    return typeof payload === "object" && payload !== null
      ? (payload as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}

/** `auth_time` del token en epoch ms, o `null` si no lo declara. */
export function authTimeOf(token: string): number | null {
  const value = jwtPayload(token)?.auth_time;
  return typeof value === "number" && Number.isFinite(value) ? value * 1000 : null;
}

/** ISO-8601 → epoch ms; `null` si falta o no se deja leer (no se inventa). */
export function parseInstant(value: string | null | undefined): number | null {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const ms = Date.parse(value);
  return Number.isFinite(ms) ? ms : null;
}

export interface SessionWindow {
  /** Hora del login (epoch ms). */
  loginAt: number | null;
  /** Edad máxima del rol en segundos, la última que dijo `/me`. */
  maxAgeS: number | null;
}

const EMPTY: SessionWindow = { loginAt: null, maxAgeS: null };

function finiteOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function readSessionWindow(): SessionWindow {
  try {
    const raw = window.localStorage.getItem(WINDOW_KEY);
    if (raw === null) {
      return EMPTY;
    }
    const parsed = JSON.parse(raw) as Partial<SessionWindow>;
    return { loginAt: finiteOrNull(parsed.loginAt), maxAgeS: finiteOrNull(parsed.maxAgeS) };
  } catch {
    return EMPTY;
  }
}

function writeSessionWindow(value: SessionWindow): void {
  try {
    window.localStorage.setItem(WINDOW_KEY, JSON.stringify(value));
  } catch {
    // Sin almacenamiento no hay cinturón; el tope lo sigue imponiendo la API.
  }
}

/** Al VOLVER del login: la hora que el refresco no puede mover. */
export function recordLogin(loginAt: number): void {
  writeSessionWindow({ loginAt, maxAgeS: null });
}

/** Lo que dijo `/me`: se guarda para que sobreviva a una recarga y al propio fin. */
export function recordMaxAge(maxAgeS: number | null): void {
  const current = readSessionWindow();
  if (current.loginAt === null) {
    return;
  }
  writeSessionWindow({ ...current, maxAgeS });
}

export function forgetSessionWindow(): void {
  try {
    window.localStorage.removeItem(WINDOW_KEY);
  } catch {
    // Nada que olvidar si no hay dónde.
  }
}

/**
 * Plazo efectivo (epoch ms): el MENOR entre lo que dice el servidor y la marca
 * del login + la edad máxima. `null` si no hay ni un dato: la consola no puede
 * inventar cuándo termina una sesión.
 */
export function effectiveDeadline(input: {
  expiresAt: number | null;
  loginAt: number | null;
  maxAgeS: number | null;
}): number | null {
  const candidates: number[] = [];
  if (input.expiresAt !== null) {
    candidates.push(input.expiresAt);
  }
  if (input.loginAt !== null && input.maxAgeS !== null) {
    candidates.push(input.loginAt + input.maxAgeS * 1000);
  }
  return candidates.length === 0 ? null : Math.min(...candidates);
}

/**
 * «24 H», «30 DÍAS», «90 DÍAS»… a partir de la edad máxima; `null` si no se
 * sabe o no es un número redondo (entonces el aviso es el genérico, no uno
 * inventado).
 */
export function maxAgeLabel(maxAgeS: number | null): string | null {
  if (maxAgeS === null || maxAgeS <= 0) {
    return null;
  }
  const DAY = 86_400;
  if (maxAgeS >= 2 * DAY && maxAgeS % DAY === 0) {
    return `${maxAgeS / DAY} DÍAS`;
  }
  if (maxAgeS % 3600 === 0) {
    return `${maxAgeS / 3600} H`;
  }
  return null;
}
