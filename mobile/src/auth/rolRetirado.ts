// [F2 · T-9.81 · D-42] EL ROL RETIRADO, visto desde la app.
//
// Desde la baja de los alias (T-9.81, sin fecha que la reabra), la API responde a
// un token que aún trae un rol viejo con 401 `rol_retirado` (cabecera `WWW-Authenticate …
// error_description="rol_retirado"` y cuerpo `{"detail": "rol_retirado"}`), y el
// canal live cierra con 4401 y ese motivo. Es FIN de sesión, NO un token vencido:
// renovar con Cognito devolvería el mismo rol y la API rechazaría en bucle.

export const ROL_RETIRADO = "rol_retirado";

/** Lo que lee la persona en el login cuando su rol fue retirado. */
export const MENSAJE_ROL_RETIRADO =
  "Tu rol fue retirado. Pide a tu administrador que te asigne uno de los roles vigentes.";

/** ¿Este 401 es el del rol retirado? El cuerpo se lee de un CLON: el original lo
 * sigue parseando el SDK. */
export async function esRolRetirado(response: Response): Promise<boolean> {
  const www = response.headers.get("WWW-Authenticate") ?? "";
  if (/error_description="?rol_retirado"?/.test(www)) {
    return true;
  }
  try {
    const body: unknown = await response.clone().json();
    return (
      typeof body === "object" &&
      body !== null &&
      (body as { detail?: unknown }).detail === ROL_RETIRADO
    );
  } catch {
    return false;
  }
}
