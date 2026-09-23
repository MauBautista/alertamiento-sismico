// Ayuda SOLO de pruebas: un JWT con la forma de Cognito (cabecera.payload.firma
// en base64url) y los claims que se le pidan. La firma es basura a propósito:
// el teléfono NUNCA verifica firmas —eso lo hace la API—, sólo lee `exp` y
// `auth_time` para decidir cuándo renovar.
//
// No lo importa ningún módulo de la app: vive aquí para que lo compartan los
// tests de `auth/` y `services/` sin que cada uno se invente su codificador.

function base64url(json: string): string {
  const bytes = new TextEncoder().encode(json);
  let bin = "";
  for (const b of bytes) {
    bin += String.fromCharCode(b);
  }
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function fakeJwt(claims: Record<string, unknown>): string {
  return [
    base64url(JSON.stringify({ alg: "RS256", kid: "test" })),
    base64url(JSON.stringify(claims)),
    "firma-de-prueba",
  ].join(".");
}

/** Epoch en SEGUNDOS (la unidad de `exp`/`auth_time`). */
export const nowS = (): number => Math.floor(Date.now() / 1000);
