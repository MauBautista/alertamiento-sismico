/**
 * [T-9.20 · D-42] Rótulos de los roles — el ÚNICO sitio de la web que los escribe.
 *
 * D-42 bajó los roles de 10 a 7 (`shared/fixtures/rbac-matrix.json`). Los tres
 * viejos (`soc_operator`, `building_admin`, `security_guard`) ya no se asignan,
 * pero siguen apareciendo en lo HISTÓRICO: la bitácora, las acciones firmadas y
 * los usuarios que el script de T-9.21 todavía no migró. Esa historia no se
 * reescribe (tampoco en pantalla): un rol viejo se pinta con SU rótulo, marcado
 * como retirado, nunca con el de su heredero.
 *
 * Espejo de `api/src/takab_api/auth/roles.py` (`ETIQUETA`, `ROL_HISTORICO`,
 * `ALIAS_HEREDADOS`); `rolesHistoricos.test.ts` lo ata celda a celda. Para ASIGNAR
 * un rol, la web no usa esta tabla: pide `GET /users/assignable-roles`.
 */

/** Rótulo de cada rol canónico (`roles.ETIQUETA`). */
export const ETIQUETA_ROL: Readonly<Record<string, string>> = {
  takab_superadmin: "SUPERADMIN TAKAB",
  takab_support: "SOPORTE TAKAB",
  tenant_admin: "ADMINISTRADOR",
  gov_operator: "GOBIERNO",
  inspector: "INSPECTOR",
  brigadista: "BRIGADISTA",
  occupant: "OCUPANTE",
};

/** Rótulo de cada rol retirado por D-42 (`roles.ROL_HISTORICO`). */
export const ROL_HISTORICO: Readonly<Record<string, string>> = {
  soc_operator: "OPERACIÓN SOC",
  building_admin: "ADMINISTRACIÓN DEL INMUEBLE",
  security_guard: "SEGURIDAD",
};

/** Los ids retirados (claves de `roles.ALIAS_HEREDADOS`). */
export const ROLES_HEREDADOS: readonly string[] = Object.keys(ROL_HISTORICO);

export function esRolHeredado(role: string): boolean {
  return Object.prototype.hasOwnProperty.call(ROL_HISTORICO, role);
}

/**
 * Rótulo para listados y bitácoras. Un rol retirado lleva su rótulo de entonces
 * y la marca «(ROL RETIRADO)»; uno desconocido se pinta crudo (inventarle un
 * rótulo escondería el dato raro).
 */
export function etiquetaDeRol(role: string): string {
  if (Object.prototype.hasOwnProperty.call(ETIQUETA_ROL, role)) return ETIQUETA_ROL[role];
  if (esRolHeredado(role)) return `${ROL_HISTORICO[role]} (ROL RETIRADO)`;
  return role;
}
