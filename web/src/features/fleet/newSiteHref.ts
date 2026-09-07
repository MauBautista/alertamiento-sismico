// [T-6.03] Cómo la ficha de un cliente manda al alta de estación YA apuntada a él.
//
// Vive aparte de `FleetAdmin` para que `TenantsPage` pueda enlazar sin importar el
// panel entero (con sus consultas y mutaciones) en su árbol de módulos.

/** Parámetros de `/fleet` que abren el alta con el cliente preseleccionado. */
export const FLEET_NEW_SITE_PARAMS = { tenant: "tenant", nueva: "nueva" } as const;

/** Enlace desde la ficha de un cliente a «nueva estación en este cliente». */
export function newSiteHref(tenantId: string): string {
  const q = new URLSearchParams({
    [FLEET_NEW_SITE_PARAMS.tenant]: tenantId,
    [FLEET_NEW_SITE_PARAMS.nueva]: "1",
  });
  return `/fleet?${q.toString()}`;
}
