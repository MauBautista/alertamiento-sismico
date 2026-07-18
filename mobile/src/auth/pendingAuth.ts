// Contexto PKCE pendiente entre abrir el Hosted UI y recibir el deep link de
// retorno. En iOS el WebBrowser intercepta el redirect y el hook completa el
// intercambio; en ANDROID el redirect `takab://auth/callback` NO se intercepta:
// llega a expo-router como deep link, y la ruta /auth/callback debe COMPLETAR el
// intercambio. Para eso necesita el `code_verifier` (jamás cruza la red) y el
// `state` (anti-CSRF) generados al abrir el navegador.
//
// Vive SOLO en memoria: el Custom Tab mantiene vivo el proceso durante el login,
// así que el verifier no toca disco (es un secreto de un solo uso y corta vida).
import type { ProfileGroup } from "./profileGate";

export interface PendingAuth {
  profile: ProfileGroup;
  codeVerifier: string;
  state: string;
}

let pending: PendingAuth | null = null;

/** Guarda el contexto justo antes de abrir el Hosted UI. */
export function setPendingAuth(next: PendingAuth): void {
  pending = next;
}

/** Devuelve el contexto y lo consume (un solo uso — evita reusar un verifier). */
export function takePendingAuth(): PendingAuth | null {
  const current = pending;
  pending = null;
  return current;
}

/** Descarta el contexto (p.ej. el hook de iOS ya intercambió). */
export function clearPendingAuth(): void {
  pending = null;
}
