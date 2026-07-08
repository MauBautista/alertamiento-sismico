import type { MeResponse } from "../auth/me";

/** Primera ruta web del rol EN ORDEN DEL SERVER, saltando /building (paramétrica,
 * no puede ser landing). `null` ⇒ rol sin superficie web (mobile-only). */
export function landingPath(me: MeResponse): string | null {
  return me.allowed_routes.find((route) => route !== "/building") ?? null;
}
