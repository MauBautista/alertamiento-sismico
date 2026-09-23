import { UserManager, WebStorageStateStore } from "oidc-client-ts";

import { getEnv } from "../app/env";

let manager: UserManager | null = null;

/** ¿Hay configuración Cognito? (sin ella solo existe el login dev-token). */
export function cognitoConfigured(): boolean {
  const { cognito } = getEnv();
  return Boolean(cognito.authority && cognito.clientId);
}

/**
 * Origen del Hosted UI (`https://<dominio>`), SIN barra final.
 *
 * [T-8.03] MEDIDO en la consola desplegada: el build recibe `VITE_COGNITO_DOMAIN`
 * de `terraform output hosted_ui_domain`, que es un host SIN esquema
 * (`takab-dev-….auth.us-east-2.amazoncognito.com`). Concatenado a pelo,
 * `${domain}/logout` era una ruta RELATIVA a la consola: SALIR navegaba dentro
 * del propio SPA y la cookie del Hosted UI nunca se borraba. Se normaliza aquí,
 * que es el único sitio que construye URLs del dominio.
 */
export function cognitoDomainOrigin(): string {
  const raw = getEnv().cognito.domain.trim().replace(/\/+$/, "");
  if (raw === "") {
    return "";
  }
  return /^https?:\/\//i.test(raw) ? raw : `https://${raw}`;
}

/**
 * UserManager único (PKCE S256 implícito en el flow `code`).
 *
 * [T-8.03 · D-38] La sesión vive en `localStorage`: con `sessionStorage` cerrar
 * la pestaña la perdía y la sesión de 24 h / 30 días era, en la práctica, «hasta
 * que se cierre la pestaña». El precio —un refresh token de larga vida legible por
 * cualquier XSS de una consola pública— se paga con tres cosas: la CSP de
 * `deploy/cloud/Caddyfile`, la revocación del refresh al salir (`logout` la hace
 * explícita: nuestro SALIR no pasa por `signoutRedirect`, que es lo único que mira
 * `revokeTokensOnSignout`) y el tope por rol que impone la API.
 */
export function getUserManager(): UserManager {
  if (!manager) {
    const { cognito } = getEnv();
    const domain = cognitoDomainOrigin();
    manager = new UserManager({
      authority: cognito.authority,
      client_id: cognito.clientId,
      redirect_uri: cognito.redirectUri,
      post_logout_redirect_uri: cognito.postLogoutUri,
      response_type: "code",
      scope: cognito.scopes,
      userStore: new WebStorageStateStore({ store: window.localStorage }),
      // Renueva con el refresh token antes de que expire el ID token (60 min). El
      // refresh vale lo que diga el app client (30 días en web); el tope de la
      // SESIÓN por rol (24 h / 30 días, D-38) lo impone la API por `auth_time`.
      automaticSilentRenew: true,
      revokeTokensOnSignout: true,
      revokeTokenTypes: ["refresh_token"],
      // El discovery de Cognito no anuncia `revocation_endpoint`; sin sembrarlo,
      // `revokeTokens` no tiene adónde ir.
      metadataSeed: domain === "" ? {} : { revocation_endpoint: `${domain}/oauth2/revoke` },
    });
  }
  return manager;
}

/** Solo tests: el UserManager se construye una vez por proceso. */
export function resetUserManagerForTests(): void {
  manager = null;
}

/** Cognito no publica end_session_endpoint estándar: logout = /logout del Hosted UI. */
export function buildLogoutUrl(): string {
  const { cognito } = getEnv();
  const params = new URLSearchParams({
    client_id: cognito.clientId,
    logout_uri: cognito.postLogoutUri,
  });
  return `${cognitoDomainOrigin()}/logout?${params.toString()}`;
}
