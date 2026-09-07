// [T-6.02] Qué puede afirmar la consola sobre CÓMO se autenticó esta sesión.
//
// Hasta esta ficha, junto al botón de acuse había un literal heredado del mockup:
// «AUTH · MFA», en verde, en TODA sesión — incluida la de `POST /dev/token`, que
// jamás pasó un reto (U-05). Una consola de alertamiento afirmando un hecho de
// seguridad que no puede conocer.
//
// Lo que SÍ se puede conocer lo escribió `api/src/takab_api/auth/mfa.py` (RO-8.c),
// verificado contra la documentación de AWS: el ID token de Cognito NO lleva
// `amr` ni `acr` —ni un Lambda propio puede fabricarlos— así que **el token no
// certifica que esta sesión presentó el segundo factor**. Lo que certifica, firmado,
// es el POOL (`iss`), y el pool es quien porta la política de MFA: el principal
// (el de la consola) tiene `mfa_configuration = "ON"`, anclado por
// `infra/terraform/modules/identity/tests/mfa.tftest.hcl`.
//
// Por eso el distintivo dice exactamente eso y nada más: de qué pool viene la
// sesión y qué exige ese pool. Y el `title` recuerda la grieta que AWS documenta
// (el PRIMER inicio de una cuenta nueva emite tokens sin TOTP): la afirmación es
// sobre la política, no sobre el factor de esta sesión.
//
// Función PURA sobre `origin`, `idToken` y la autoridad configurada; el gancho
// que la alimenta desde el almacén de sesión vive en `useAuthEvidence.ts`.

export type AuthEvidenceKind = "none" | "dev" | "pool-mfa" | "cognito-unknown-pool";

export interface AuthBadge {
  label: string;
  title: string;
}

export interface AuthEvidence {
  kind: AuthEvidenceKind;
  /** Qué se pinta junto al operador; `null` = nada (una sesión dev no pinta nada). */
  badge: AuthBadge | null;
}

/** `iss` del payload de un JWT, SIN verificar la firma (eso lo hace la API). */
export function jwtIssuer(idToken: string | null): string | null {
  if (idToken === null) return null;
  const parts = idToken.split(".");
  if (parts.length < 2) return null;
  try {
    const b64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = b64 + "=".repeat((4 - (b64.length % 4)) % 4);
    const payload: unknown = JSON.parse(atob(padded));
    if (typeof payload !== "object" || payload === null) return null;
    const iss = (payload as { iss?: unknown }).iss;
    return typeof iss === "string" && iss !== "" ? iss : null;
  } catch {
    return null;
  }
}

export function authEvidence(input: {
  origin: "cognito" | "dev" | null;
  idToken: string | null;
  /** `getEnv().cognito.authority`: el issuer del pool principal. */
  authority: string;
}): AuthEvidence {
  if (input.origin === null) return { kind: "none", badge: null };
  // Una sesión de desarrollo no afirma nada: no hay pool ni reto detrás.
  if (input.origin === "dev") return { kind: "dev", badge: null };

  const iss = jwtIssuer(input.idToken);
  if (input.authority !== "" && iss === input.authority) {
    return {
      kind: "pool-mfa",
      badge: {
        label: "AUTH · POOL PRINCIPAL · MFA OBLIGATORIO",
        title:
          "Sesión del pool principal de Cognito, que exige TOTP (mfa_configuration = ON). " +
          "El token certifica el pool, no el factor de esta sesión: el primer inicio de una " +
          "cuenta nueva sale sin TOTP (RO-8.c).",
      },
    };
  }
  // Cognito, pero de un pool que no es el configurado (o un token ilegible):
  // se dice de dónde viene y NO se afirma MFA.
  return {
    kind: "cognito-unknown-pool",
    badge: {
      label: "AUTH · COGNITO",
      title: "Sesión de Cognito de un pool que no es el principal configurado: no se afirma MFA.",
    },
  };
}
