// [T-9.20 · D-42] Roles de la app: los SIETE canónicos y la ventana de alias.
//
// ESPEJO de `api/src/takab_api/auth/roles.py` (CANONICAL_ROLES, ETIQUETA,
// ALIAS_HEREDADOS, ROL_HISTORICO). Es el ÚNICO mapa de roles de la app: el gate,
// el alcance y el directorio lo leen de aquí. `roles.test.ts` lee el fuente de la
// API y exige que el alias sea idéntico.
//
// El servidor ya canoniza (`/me` no devuelve roles viejos). Si aun así llegara
// uno, la app lo trata con EL MISMO alias que la nube — nunca con una lista
// propia. Los alias se retiran en T-9.81.

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

/** Rol viejo → canónico (ventana de D-42). */
export const ALIAS_HEREDADOS: Readonly<Record<string, string>> = {
  soc_operator: "tenant_admin",
  security_guard: "brigadista",
  building_admin: "brigadista",
};

const ETIQUETA: Readonly<Record<string, string>> = {
  takab_superadmin: "SUPERADMIN TAKAB",
  takab_support: "SOPORTE TAKAB",
  tenant_admin: "ADMINISTRADOR",
  gov_operator: "GOBIERNO",
  inspector: "INSPECTOR",
  brigadista: "BRIGADISTA",
  occupant: "OCUPANTE",
};

/** Rótulos de los roles viejos para filas HISTÓRICAS (p.ej. un roster que aún no
 *  migró): la historia no se reescribe, la fila dice el rol que tenía. */
const ROL_HISTORICO: Readonly<Record<string, string>> = {
  soc_operator: "OPERACIÓN SOC",
  building_admin: "ADMINISTRACIÓN DEL INMUEBLE",
  security_guard: "SEGURIDAD",
};

/** Canoniza un rol viejo; un canónico o desconocido sale tal cual (default-deny
 *  lo decide quien lo consume). */
export function canonizarRol(role: string): string {
  return ALIAS_HEREDADOS[role] ?? role;
}

/** Rótulo para mostrar: canónico, histórico, o el id en mayúsculas si no se conoce. */
export function etiquetaRol(role: string): string {
  return ETIQUETA[role] ?? ROL_HISTORICO[role] ?? role.toUpperCase();
}
