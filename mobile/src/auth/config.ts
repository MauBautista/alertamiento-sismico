// Config de autenticación — DOS pools de Cognito (decisión #7, T-2.00):
//   · occupant  → pool takab-*-occupants (mfa=OPTIONAL): login simple, MFA opt-in.
//   · tactical  → pool principal (mfa=ON, no negociable — RBAC §4.3).
// Los valores llegan por EXPO_PUBLIC_* (inlineados por Expo en build); las
// LECTURAS deben ser expresiones estáticas process.env.EXPO_PUBLIC_X — el
// acceso dinámico process.env[k] NO se inlinea. Cero secretos: pool/client id
// y dominio son identificadores públicos (specs/cognito-pool-v1.md §1).

export type PoolConfig = {
  issuer: string;
  clientId: string;
  /** Dominio del Hosted UI, sin esquema (p.ej. takab-dev-….amazoncognito.com). */
  hostedUiDomain: string;
};

export type Pools = { occupant: PoolConfig; tactical: PoolConfig };

/** Deep link de retorno del Hosted UI. DEBE coincidir con el `scheme` de
 * app.json y con `mobile_callback_urls` del módulo Terraform `identity`. */
export const REDIRECT_URI = "takab://auth/callback";

export const LOGOUT_URI = "takab://auth/logout";

/** Puro y testeable: env → pools (los faltantes quedan como cadena vacía). */
export function buildPools(env: Record<string, string | undefined>): Pools {
  return {
    occupant: {
      issuer: env.EXPO_PUBLIC_COGNITO_OCCUPANTS_ISSUER ?? "",
      clientId: env.EXPO_PUBLIC_COGNITO_OCCUPANTS_CLIENT_ID ?? "",
      hostedUiDomain: env.EXPO_PUBLIC_COGNITO_OCCUPANTS_DOMAIN ?? "",
    },
    tactical: {
      issuer: env.EXPO_PUBLIC_COGNITO_TACTICAL_ISSUER ?? "",
      clientId: env.EXPO_PUBLIC_COGNITO_TACTICAL_CLIENT_ID ?? "",
      hostedUiDomain: env.EXPO_PUBLIC_COGNITO_TACTICAL_DOMAIN ?? "",
    },
  };
}

export const poolConfigured = (pool: PoolConfig): boolean =>
  pool.issuer !== "" && pool.clientId !== "" && pool.hostedUiDomain !== "";

/** Endpoints OAuth2 del Hosted UI de Cognito (no publica end_session estándar;
 * el logout es /logout del dominio — mismo apunte que la consola). */
export function discoveryFor(pool: PoolConfig): {
  authorizationEndpoint: string;
  tokenEndpoint: string;
  revocationEndpoint: string;
  endSessionEndpoint: string;
} {
  const base = `https://${pool.hostedUiDomain}`;
  return {
    authorizationEndpoint: `${base}/oauth2/authorize`,
    tokenEndpoint: `${base}/oauth2/token`,
    revocationEndpoint: `${base}/oauth2/revoke`,
    endSessionEndpoint: `${base}/logout`,
  };
}

// --- Valores del build (lecturas ESTÁTICAS, ver nota de arriba) --------------

export const API_BASE_URL = process.env.EXPO_PUBLIC_API_BASE_URL ?? "";

export const POOLS: Pools = buildPools({
  EXPO_PUBLIC_COGNITO_OCCUPANTS_ISSUER: process.env.EXPO_PUBLIC_COGNITO_OCCUPANTS_ISSUER,
  EXPO_PUBLIC_COGNITO_OCCUPANTS_CLIENT_ID: process.env.EXPO_PUBLIC_COGNITO_OCCUPANTS_CLIENT_ID,
  EXPO_PUBLIC_COGNITO_OCCUPANTS_DOMAIN: process.env.EXPO_PUBLIC_COGNITO_OCCUPANTS_DOMAIN,
  EXPO_PUBLIC_COGNITO_TACTICAL_ISSUER: process.env.EXPO_PUBLIC_COGNITO_TACTICAL_ISSUER,
  EXPO_PUBLIC_COGNITO_TACTICAL_CLIENT_ID: process.env.EXPO_PUBLIC_COGNITO_TACTICAL_CLIENT_ID,
  EXPO_PUBLIC_COGNITO_TACTICAL_DOMAIN: process.env.EXPO_PUBLIC_COGNITO_TACTICAL_DOMAIN,
});
