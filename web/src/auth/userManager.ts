import { UserManager, WebStorageStateStore } from "oidc-client-ts";

import { getEnv } from "../app/env";

let manager: UserManager | null = null;

/** ¿Hay configuración Cognito? (sin ella solo existe el login dev-token). */
export function cognitoConfigured(): boolean {
  const { cognito } = getEnv();
  return Boolean(cognito.authority && cognito.clientId);
}

/** UserManager único (PKCE S256 implícito en el flow `code`; sesión por pestaña). */
export function getUserManager(): UserManager {
  if (!manager) {
    const { cognito } = getEnv();
    manager = new UserManager({
      authority: cognito.authority,
      client_id: cognito.clientId,
      redirect_uri: cognito.redirectUri,
      post_logout_redirect_uri: cognito.postLogoutUri,
      response_type: "code",
      scope: cognito.scopes,
      userStore: new WebStorageStateStore({ store: window.sessionStorage }),
      // Renueva con el refresh token (8 h en el pool) antes de que expire el ID token.
      automaticSilentRenew: true,
    });
  }
  return manager;
}

/** Cognito no publica end_session_endpoint estándar: logout = /logout del Hosted UI. */
export function buildLogoutUrl(): string {
  const { cognito } = getEnv();
  const params = new URLSearchParams({
    client_id: cognito.clientId,
    logout_uri: cognito.postLogoutUri,
  });
  return `${cognito.domain}/logout?${params.toString()}`;
}
