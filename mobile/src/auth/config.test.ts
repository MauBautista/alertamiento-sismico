// T-2.02 — config de los DOS pools (decisión #7): occupant (login simple,
// MFA opcional) y táctico (pool principal, MFA ON). Sin valores horneados:
// todo llega por EXPO_PUBLIC_* y un pool incompleto se declara no-configurado
// (la UI lo dice en vez de fingir que el login funciona).
import { buildPools, discoveryFor, poolConfigured, REDIRECT_URI } from "./config";

const FULL_ENV = {
  EXPO_PUBLIC_COGNITO_OCCUPANTS_ISSUER: "https://cognito-idp.us-east-2.amazonaws.com/us-east-2_AAA",
  EXPO_PUBLIC_COGNITO_OCCUPANTS_CLIENT_ID: "occ-client",
  EXPO_PUBLIC_COGNITO_OCCUPANTS_DOMAIN: "takab-dev-occupants-1.auth.us-east-2.amazoncognito.com",
  EXPO_PUBLIC_COGNITO_TACTICAL_ISSUER: "https://cognito-idp.us-east-2.amazonaws.com/us-east-2_BBB",
  EXPO_PUBLIC_COGNITO_TACTICAL_CLIENT_ID: "tac-client",
  EXPO_PUBLIC_COGNITO_TACTICAL_DOMAIN: "takab-dev-1.auth.us-east-2.amazoncognito.com",
};

describe("buildPools / poolConfigured", () => {
  it("mapea el env a los dos pools", () => {
    const pools = buildPools(FULL_ENV);
    expect(pools.occupant.clientId).toBe("occ-client");
    expect(pools.tactical.clientId).toBe("tac-client");
    expect(poolConfigured(pools.occupant)).toBe(true);
    expect(poolConfigured(pools.tactical)).toBe(true);
  });

  it("un pool con cualquier campo faltante queda NO configurado (default-deny)", () => {
    const sinDominio = buildPools({ ...FULL_ENV, EXPO_PUBLIC_COGNITO_OCCUPANTS_DOMAIN: "" });
    expect(poolConfigured(sinDominio.occupant)).toBe(false);
    expect(poolConfigured(sinDominio.tactical)).toBe(true);

    const vacio = buildPools({});
    expect(poolConfigured(vacio.occupant)).toBe(false);
    expect(poolConfigured(vacio.tactical)).toBe(false);
  });
});

describe("discoveryFor", () => {
  it("arma los endpoints del Hosted UI a partir del dominio", () => {
    const pools = buildPools(FULL_ENV);
    const d = discoveryFor(pools.occupant);
    const base = "https://takab-dev-occupants-1.auth.us-east-2.amazoncognito.com";
    expect(d.authorizationEndpoint).toBe(`${base}/oauth2/authorize`);
    expect(d.tokenEndpoint).toBe(`${base}/oauth2/token`);
    expect(d.revocationEndpoint).toBe(`${base}/oauth2/revoke`);
    expect(d.endSessionEndpoint).toBe(`${base}/logout`);
  });
});

describe("REDIRECT_URI", () => {
  it("es el deep link registrado en Terraform (identity: mobile_callback_urls)", () => {
    expect(REDIRECT_URI).toBe("takab://auth/callback");
  });
});
