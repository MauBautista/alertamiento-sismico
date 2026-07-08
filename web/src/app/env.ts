/** Lectura tipada de la configuración VITE_* (valores reales: terraform output). */

export interface AppEnv {
  apiBaseUrl: string;
  cognito: {
    authority: string;
    clientId: string;
    domain: string;
    redirectUri: string;
    postLogoutUri: string;
    scopes: string;
  };
  devTokenEnabled: boolean;
  /** CCTV ONVIF de la consola (T-1.27 criterio #2): placeholder tras flag, off en MVP. */
  featureCctv: boolean;
}

function read(name: keyof ImportMetaEnv, fallback = ""): string {
  const value = import.meta.env[name];
  return typeof value === "string" && value !== "" ? value : fallback;
}

// Lectura perezosa (no módulo-level) para que los tests puedan vi.stubEnv.
export function getEnv(): AppEnv {
  return {
    apiBaseUrl: read("VITE_API_BASE_URL", "/api"),
    cognito: {
      authority: read("VITE_COGNITO_AUTHORITY"),
      clientId: read("VITE_COGNITO_CLIENT_ID"),
      domain: read("VITE_COGNITO_DOMAIN"),
      redirectUri: read("VITE_COGNITO_REDIRECT_URI", `${window.location.origin}/auth/callback`),
      postLogoutUri: read("VITE_COGNITO_POST_LOGOUT_URI", `${window.location.origin}/`),
      scopes: read("VITE_COGNITO_SCOPES", "openid email profile"),
    },
    devTokenEnabled: read("VITE_DEV_TOKEN_ENABLED") === "true",
    featureCctv: read("VITE_FEATURE_CCTV") === "true",
  };
}
