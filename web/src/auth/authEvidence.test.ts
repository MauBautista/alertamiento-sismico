// [T-6.02] Ninguna sesión sin constancia real pinta «MFA»; una sesión dev no pinta nada.
import { describe, expect, it } from "vitest";

import { authEvidence, jwtIssuer } from "./authEvidence";

const AUTHORITY = "https://cognito-idp.us-east-2.amazonaws.com/us-east-2_PRINCIPAL";
const OTRO_POOL = "https://cognito-idp.us-east-2.amazonaws.com/us-east-2_OCUPANTES";

/** Un JWT sin firmar válida: sólo importa el payload. */
function jwt(payload: Record<string, unknown>): string {
  const b64 = (s: string) => btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  return `${b64('{"alg":"RS256","kid":"k"}')}.${b64(JSON.stringify(payload))}.firma`;
}

describe("jwtIssuer", () => {
  it("lee el `iss` del payload sin verificar la firma (eso es de la API)", () => {
    expect(jwtIssuer(jwt({ iss: AUTHORITY, sub: "u" }))).toBe(AUTHORITY);
  });

  it("con un token ilegible o sin `iss` devuelve null, no una cadena inventada", () => {
    expect(jwtIssuer(null)).toBeNull();
    expect(jwtIssuer("no-es-un-jwt")).toBeNull();
    expect(jwtIssuer("a.!!!.c")).toBeNull();
    expect(jwtIssuer(jwt({ sub: "u" }))).toBeNull();
    expect(jwtIssuer(jwt({ iss: 42 }))).toBeNull();
  });
});

describe("authEvidence", () => {
  it("[U-05] una sesión de /dev/token NO pinta nada: no hay pool ni reto detrás", () => {
    const e = authEvidence({ origin: "dev", idToken: jwt({ iss: "dev" }), authority: AUTHORITY });
    expect(e.kind).toBe("dev");
    expect(e.badge).toBeNull();
  });

  it("sin sesión tampoco", () => {
    expect(authEvidence({ origin: null, idToken: null, authority: AUTHORITY }).badge).toBeNull();
  });

  it("del pool principal afirma la POLÍTICA del pool, y lo dice tal cual", () => {
    const e = authEvidence({
      origin: "cognito",
      idToken: jwt({ iss: AUTHORITY }),
      authority: AUTHORITY,
    });
    expect(e.kind).toBe("pool-mfa");
    expect(e.badge?.label).toBe("AUTH · POOL PRINCIPAL · MFA OBLIGATORIO");
    // La grieta que AWS documenta va en el title: no se afirma el factor de
    // ESTA sesión, se afirma lo que el pool exige.
    expect(e.badge?.title).toMatch(/certifica el pool, no el factor/);
    expect(e.badge?.title).toMatch(/RO-8\.c/);
  });

  it("de otro pool (o con un token ilegible) dice COGNITO y NO afirma MFA", () => {
    for (const idToken of [jwt({ iss: OTRO_POOL }), "roto", null]) {
      const e = authEvidence({ origin: "cognito", idToken, authority: AUTHORITY });
      expect(e.kind).toBe("cognito-unknown-pool");
      expect(e.badge?.label).toBe("AUTH · COGNITO");
      expect(e.badge?.label).not.toMatch(/MFA/);
    }
  });

  it("sin autoridad configurada nadie es «pool principal», aunque el iss diga algo", () => {
    const e = authEvidence({ origin: "cognito", idToken: jwt({ iss: "" }), authority: "" });
    expect(e.kind).toBe("cognito-unknown-pool");
  });
});
