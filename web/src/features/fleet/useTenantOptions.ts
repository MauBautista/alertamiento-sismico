// [T-6.03] Los clientes en los que un alta de estación puede escribir.
//
// El defecto que cierra (U-06): el formulario de estación no tenía campo de cliente
// y `FleetAdmin` armaba el cuerpo sin `tenant_id`. Para un rol de cliente eso es
// correcto (el servidor escribe en el suyo, elija lo que elija); para un rol interno
// TAKAB la API responde 400 «tenant_id es obligatorio para roles internos» — y la
// consola lo traducía con el mensaje del retiro («NO COINCIDE · el identificador…»).
// Medido en vivo el 2026-09-07 contra `make soc-local`: el superadmin no podía crear
// un sitio desde la consola, y nada le decía por qué.
//
// La MISMA clave de consulta que `features/tenants/useTenants` a propósito: la caché
// es una, `useCreateTenant` la invalida al dar de alta un cliente, y así el cliente
// recién creado aparece en el selector sin recargar.
import { useQuery } from "@tanstack/react-query";

import { listTenantsTenantsGet } from "@takab/sdk";
import type { TenantOut } from "@takab/sdk";

/** Espejo de `TENANTS_STALE_MS`: el catálogo de clientes cambia por acto humano. */
export const TENANT_OPTIONS_STALE_MS = 120_000;

export interface TenantOptions {
  tenants: TenantOut[];
  loading: boolean;
  /** Solo si NO hay dato: con lista en caché, un refetch fallido no la borra. */
  error: string | null;
  refetch: () => void;
}

export function useTenantOptions(): TenantOptions {
  const query = useQuery({
    queryKey: ["tenants"],
    queryFn: async () => {
      const { data, response } = await listTenantsTenantsGet();
      if (data === undefined) throw new Error(`GET /tenants falló (${response.status})`);
      return data;
    },
    staleTime: TENANT_OPTIONS_STALE_MS,
  });
  return {
    tenants: query.data ?? [],
    loading: query.isPending,
    error: query.data === undefined && query.error ? query.error.message : null,
    refetch: () => {
      void query.refetch();
    },
  };
}
