// Decisión PURA del retorno del Hosted UI (sin red ni router, para poder
// testearla). expo-router entrega los query params como string | string[]
// (repetidos ⇒ array); nos quedamos con el primero.
import type { PendingAuth } from "./pendingAuth";

export type CallbackParams = {
  code?: string | string[];
  state?: string | string[];
  error?: string | string[];
  error_description?: string | string[];
};

export type CallbackPlan =
  | { kind: "provider_error"; message: string } // Cognito rechazó (?error=…)
  | { kind: "expired" } // sin code, o sin contexto PKCE (acceso perdido)
  | { kind: "state_mismatch" } // anti-CSRF: el state no coincide
  | { kind: "exchange"; profile: PendingAuth["profile"]; code: string; codeVerifier: string };

const first = (value: string | string[] | undefined): string | null =>
  Array.isArray(value) ? (value[0] ?? null) : (value ?? null);

/** Qué hacer con `takab://auth/callback?…` dado el contexto PKCE pendiente. */
export function planCallback(params: CallbackParams, pending: PendingAuth | null): CallbackPlan {
  const error = first(params.error);
  if (error) {
    return { kind: "provider_error", message: first(params.error_description) ?? error };
  }
  const code = first(params.code);
  if (!code || !pending) {
    return { kind: "expired" };
  }
  if (pending.state !== first(params.state)) {
    return { kind: "state_mismatch" };
  }
  return { kind: "exchange", profile: pending.profile, code, codeVerifier: pending.codeVerifier };
}
