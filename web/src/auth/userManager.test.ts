// [T-8.03] Configuración del UserManager: dónde vive la sesión, qué se revoca y
// adónde apunta el /logout del Hosted UI.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  buildLogoutUrl,
  cognitoDomainOrigin,
  getUserManager,
  resetUserManagerForTests,
} from "./userManager";

const AUTHORITY = "https://cognito-idp.us-east-2.amazonaws.com/us-east-2_TEST";

describe("userManager", () => {
  beforeEach(() => {
    resetUserManagerForTests();
    window.localStorage.clear();
    window.sessionStorage.clear();
    vi.stubEnv("VITE_COGNITO_AUTHORITY", AUTHORITY);
    vi.stubEnv("VITE_COGNITO_CLIENT_ID", "client-abc");
    vi.stubEnv("VITE_COGNITO_POST_LOGOUT_URI", "https://consola.test/");
  });

  afterEach(() => {
    resetUserManagerForTests();
    vi.unstubAllEnvs();
  });

  it("la sesión vive en localStorage: sobrevive a cerrar la pestaña (D-38, «un día»)", async () => {
    vi.stubEnv("VITE_COGNITO_DOMAIN", "https://takab-test.auth.us-east-2.amazoncognito.com");
    const um = getUserManager();

    await um.settings.userStore.set("prueba", "valor");

    expect(window.localStorage.getItem("oidc.prueba")).toBe("valor");
    expect(window.sessionStorage.getItem("oidc.prueba")).toBeNull();
  });

  it("sigue renovando sola y declara la revocación al cerrar sesión", () => {
    vi.stubEnv("VITE_COGNITO_DOMAIN", "https://takab-test.auth.us-east-2.amazoncognito.com");
    const { settings } = getUserManager();

    expect(settings.automaticSilentRenew).toBe(true);
    expect(settings.revokeTokensOnSignout).toBe(true);
    // Solo el refresh: el access token de Cognito no se revoca por separado y el
    // refresh es lo que vale 30 días en un localStorage.
    expect(settings.revokeTokenTypes).toEqual(["refresh_token"]);
  });

  it("Cognito no publica `revocation_endpoint` en su discovery: se siembra /oauth2/revoke", () => {
    vi.stubEnv("VITE_COGNITO_DOMAIN", "https://takab-test.auth.us-east-2.amazoncognito.com");
    const { settings } = getUserManager();

    expect(settings.metadataSeed).toEqual({
      revocation_endpoint: "https://takab-test.auth.us-east-2.amazoncognito.com/oauth2/revoke",
    });
  });

  // MEDIDO en la consola desplegada (bundle servido el 2026-09-22): el build
  // recibe `VITE_COGNITO_DOMAIN` de `terraform output hosted_ui_domain`, que es
  // un host SIN esquema. `${domain}/logout` era entonces una ruta RELATIVA: SALIR
  // navegaba a `https://<consola>/takab-dev-….amazoncognito.com/logout`, el SPA
  // lo servía como una ruta más y la cookie del Hosted UI nunca se borraba.
  it("un dominio SIN esquema (el que da terraform) se lee como https", () => {
    vi.stubEnv("VITE_COGNITO_DOMAIN", "takab-dev-1.auth.us-east-2.amazoncognito.com");

    expect(cognitoDomainOrigin()).toBe("https://takab-dev-1.auth.us-east-2.amazoncognito.com");
    expect(buildLogoutUrl()).toBe(
      "https://takab-dev-1.auth.us-east-2.amazoncognito.com/logout" +
        "?client_id=client-abc&logout_uri=https%3A%2F%2Fconsola.test%2F",
    );
    expect(getUserManager().settings.metadataSeed?.revocation_endpoint).toBe(
      "https://takab-dev-1.auth.us-east-2.amazoncognito.com/oauth2/revoke",
    );
  });

  it("un dominio con esquema o con barra final no se duplica", () => {
    vi.stubEnv("VITE_COGNITO_DOMAIN", "https://takab-test.auth.us-east-2.amazoncognito.com/");
    expect(cognitoDomainOrigin()).toBe("https://takab-test.auth.us-east-2.amazoncognito.com");
  });

  it("sin dominio no se inventa un endpoint de revocación", () => {
    vi.stubEnv("VITE_COGNITO_DOMAIN", "");
    expect(cognitoDomainOrigin()).toBe("");
    expect(getUserManager().settings.metadataSeed).toEqual({});
  });
});
