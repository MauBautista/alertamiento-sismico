// [T-9.20 · T-9.81 · D-42] Roles de la app: los SIETE canónicos y los tres retirados.
//
// ESPEJO de `api/src/takab_api/auth/roles.py` (CANONICAL_ROLES, ETIQUETA,
// ROLES_RETIRADOS, ROL_HISTORICO). Es el ÚNICO mapa de roles de la app: el gate,
// el alcance y el directorio lo leen de aquí. `roles.test.ts` lee el fuente de la
// API y exige que los retirados sean idénticos.
//
// T-9.81 dio de baja los alias: un token con rol viejo es 401 `rol_retirado`
// (fin de sesión, `rolRetirado.ts`) y `/me` nunca devuelve uno. La app ya no
// traduce un rol viejo a su heredero: solo conserva su RÓTULO para lo histórico.

/** Los siete roles de D-42. */
export const CANONICAL_ROLES: readonly string[] = [
  "takab_superadmin",
  "takab_support",
  "tenant_admin",
  "gov_operator",
  "inspector",
  "brigadista",
  "occupant",
];

/** Los tres roles dados de baja por D-42 (T-9.81). */
export const ROLES_RETIRADOS: readonly string[] = [
  "soc_operator",
  "security_guard",
  "building_admin",
];

const ETIQUETA: Readonly<Record<string, string>> = {
  takab_superadmin: "SUPERADMIN TAKAB",
  takab_support: "SOPORTE TAKAB",
  tenant_admin: "ADMINISTRADOR",
  gov_operator: "GOBIERNO",
  inspector: "INSPECTOR",
  brigadista: "BRIGADISTA",
  occupant: "OCUPANTE",
};

/** Rótulos de los roles retirados para filas HISTÓRICAS: la historia no se
 *  reescribe, la fila dice el rol que tenía. */
const ROL_HISTORICO: Readonly<Record<string, string>> = {
  soc_operator: "OPERACIÓN SOC",
  building_admin: "ADMINISTRACIÓN DEL INMUEBLE",
  security_guard: "SEGURIDAD",
};

/** Rótulo para mostrar: canónico, histórico, o el id en mayúsculas si no se conoce. */
export function etiquetaRol(role: string): string {
  return ETIQUETA[role] ?? ROL_HISTORICO[role] ?? role.toUpperCase();
}
