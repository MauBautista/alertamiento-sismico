import { getEnv } from "../app/env";

/** Cuerpo de POST /dev/token (la API solo lo monta con JWKS inline — nunca prod). */
export interface DevTokenRequest {
  role: string;
  tenant_id: string;
  site_scope?: string;
  surface?: string;
}

interface DevTokenResponse {
  id_token: string;
  token_use: string;
  expires_in: number;
}

export interface DevSession {
  idToken: string;
  expiresAt: number;
}

const STORAGE_KEY = "takab.dev.session";

export async function requestDevToken(req: DevTokenRequest): Promise<DevSession> {
  const resp = await fetch(`${getEnv().apiBaseUrl}/dev/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!resp.ok) {
    throw new Error(`POST /dev/token falló (${resp.status})`);
  }
  const body = (await resp.json()) as DevTokenResponse;
  return { idToken: body.id_token, expiresAt: Date.now() + body.expires_in * 1000 };
}

export function saveDevSession(session: DevSession): void {
  window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

export function loadDevSession(): DevSession | null {
  const raw = window.sessionStorage.getItem(STORAGE_KEY);
  if (!raw) {
    return null;
  }
  try {
    const session = JSON.parse(raw) as DevSession;
    if (
      typeof session.idToken !== "string" ||
      typeof session.expiresAt !== "number" ||
      session.expiresAt <= Date.now()
    ) {
      clearDevSession();
      return null;
    }
    return session;
  } catch {
    clearDevSession();
    return null;
  }
}

export function clearDevSession(): void {
  window.sessionStorage.removeItem(STORAGE_KEY);
}
