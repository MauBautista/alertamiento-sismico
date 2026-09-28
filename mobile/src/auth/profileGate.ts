// Gate de perfil SERVER-DRIVEN (spec móvil §8, decisión D4d).
// El grupo de rutas se deriva de la respuesta de /me (role + surface) con
// default-deny; el backend re-valida cada acción vía la matriz (jamás se
// confía en la UI). El gating FINO por allowed_actions llega con T-2.03,
// cuando los roles móviles dejen de tener acciones vacías en matrix.py.
/** Grupos de rutas de la app (expo-router). */
export type ProfileGroup = "occupant" | "tactical";

export type GateDenyReason = "no_session" | "wrong_surface" | "role_not_mobile";

export type GateResult =
  | { allowed: true; group: ProfileGroup }
  | { allowed: false; reason: GateDenyReason };

/** Roles con superficie móvil táctica (RBAC-TAKAB.md §3; D4d: el inspector
 * reutiliza el perfil táctico). [T-9.11 · D-42] el administrador del tenant
 * (`tenant_admin`) usa también la app táctica completa: recibe el aviso de
 * movimiento y tiene las acciones de campo del brigadista. Las pestañas siguen
 * gobernadas por sus `allowed_actions` (`pestanasTacticas`).
 * [T-9.81 · D-42] roles de 10 a 7 y baja de los alias: `security_guard` y
 * `building_admin` ya no llegan (su token es 401 `rol_retirado`); si llegaran,
 * no se traducen a su heredero y caen en el default-deny. */
export const TACTICAL_ROLES: ReadonlySet<string> = new Set([
  "brigadista",
  "inspector",
  "tenant_admin",
]);

/** Deriva el grupo de rutas de lo que respondió /me. Default-deny. */
export function gateFor(
  me: { role: string; surface: string } | null | undefined,
): GateResult {
  if (!me) {
    return { allowed: false, reason: "no_session" };
  }
  if (me.surface !== "mobile" && me.surface !== "both") {
    return { allowed: false, reason: "wrong_surface" };
  }
  const role = me.role;
  if (role === "occupant") {
    return { allowed: true, group: "occupant" };
  }
  if (TACTICAL_ROLES.has(role)) {
    return { allowed: true, group: "tactical" };
  }
  return { allowed: false, reason: "role_not_mobile" };
}
