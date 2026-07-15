import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";

import {
  createTenantTenantsPost,
  getGatewayConfigStateFleetGatewaysGatewayIdConfigStateGet,
  listGatewaysFleetGatewaysGet,
  listRuleSetsRuleSetsGet,
  listSitesSitesGet,
  listTenantsTenantsGet,
} from "@takab/sdk";
import type {
  GatewayConfigStateOut,
  GatewayOut,
  RuleSetOut,
  SiteOut,
  TenantCreate,
  TenantOut,
} from "@takab/sdk";

/** El config-state cambia cuando el worker de sync publica: ≤60 s por contrato. */
export const SYNC_POLL_MS = 10_000;

/** Sin dato nuevo tras este umbral el panel pasa a DATOS RETENIDOS. */
export const TENANTS_STALE_MS = 120_000;

class TenantsRequestError extends Error {
  constructor(resource: string, status: number) {
    super(`GET ${resource} falló (${status})`);
    this.name = "TenantsRequestError";
  }
}

async function fetchTenants(): Promise<TenantOut[]> {
  const { data, response } = await listTenantsTenantsGet();
  if (data === undefined) {
    throw new TenantsRequestError("/tenants", response.status);
  }
  return data;
}

async function fetchRuleSets(): Promise<RuleSetOut[]> {
  const { data, response } = await listRuleSetsRuleSetsGet();
  if (data === undefined) {
    throw new TenantsRequestError("/rule-sets", response.status);
  }
  return data.items;
}

async function fetchSites(): Promise<SiteOut[]> {
  const { data, response } = await listSitesSitesGet();
  if (data === undefined) {
    throw new TenantsRequestError("/sites", response.status);
  }
  return data;
}

async function fetchGateways(): Promise<GatewayOut[]> {
  const { data, response } = await listGatewaysFleetGatewaysGet();
  if (data === undefined) {
    throw new TenantsRequestError("/fleet/gateways", response.status);
  }
  return data;
}

async function fetchConfigState(gatewayId: string): Promise<GatewayConfigStateOut> {
  const { data, response } = await getGatewayConfigStateFleetGatewaysGatewayIdConfigStateGet({
    path: { gateway_id: gatewayId },
  });
  if (data === undefined) {
    throw new TenantsRequestError(`/fleet/gateways/${gatewayId}/config-state`, response.status);
  }
  return data;
}

export interface TenantsData {
  tenants: TenantOut[];
  ruleSets: RuleSetOut[] | undefined;
  sites: SiteOut[] | undefined;
  loading: boolean;
  error: string | null;
  dataUpdatedAt: number;
  refetch: () => void;
  /** true si /rule-sets falló: sin él no se pueden leer ni editar umbrales. */
  ruleSetsError: string | null;
}

/**
 * Catálogo multi-tenant. RLS decide las filas: superadmin/support ven todos los
 * tenants; tenant_admin ve SÓLO el suyo (`routers/tenants`). La UI no filtra nada.
 *
 * `/sites` degrada sin tumbar la página (se pierde la cuenta de sitios, no el
 * catálogo). `/rule-sets` sí es esencial: sin él no hay umbrales que mostrar.
 */
export function useTenants(): TenantsData {
  const tenants = useQuery({
    queryKey: ["tenants"],
    queryFn: fetchTenants,
    staleTime: TENANTS_STALE_MS,
  });
  const ruleSets = useQuery({ queryKey: ["rule-sets"], queryFn: fetchRuleSets, staleTime: 30_000 });
  const sites = useQuery({ queryKey: ["sites"], queryFn: fetchSites, staleTime: 300_000 });

  return {
    tenants: tenants.data ?? [],
    ruleSets: ruleSets.data,
    sites: sites.data,
    loading: tenants.isPending,
    error: tenants.data === undefined && tenants.error ? tenants.error.message : null,
    dataUpdatedAt: tenants.dataUpdatedAt,
    refetch: () => {
      void tenants.refetch();
      void ruleSets.refetch();
    },
    ruleSetsError: ruleSets.error ? ruleSets.error.message : null,
  };
}

export interface TenantSyncData {
  /** undefined mientras no se sepa (regla de oro 7: ni sincronizado ni pendiente). */
  states: GatewayConfigStateOut[] | undefined;
  loading: boolean;
  error: string | null;
}

/**
 * Estado REAL del sync firmado de los gabinetes del tenant. `publish` sólo registra
 * la intención (202 `pending_sync`); quien firma y entrega es el worker de T-1.23.
 * Este poll sobre `config-state` es lo único que autoriza a decir "SINCRONIZADO".
 *
 * Los gateways llegan de `/fleet/gateways`, ya filtrado por RLS al tenant en sesión.
 * Un superadmin mirando OTRO tenant no verá gabinetes aquí: se le dice, no se finge.
 */
export function useTenantSync(gatewayIds: string[]): TenantSyncData {
  const results = useQueries({
    queries: gatewayIds.map((id) => ({
      queryKey: ["config-state", id],
      queryFn: () => fetchConfigState(id),
      refetchInterval: SYNC_POLL_MS,
    })),
  });

  if (gatewayIds.length === 0) {
    return { states: [], loading: false, error: null };
  }
  const loading = results.some((r) => r.isPending);
  const firstError = results.find((r) => r.error)?.error;
  const data = results.map((r) => r.data).filter((d): d is GatewayConfigStateOut => !!d);
  return {
    // Parcial ⇒ undefined: con un gabinete sin responder no se afirma nada del sync.
    states: data.length === gatewayIds.length ? data : undefined,
    loading,
    error: firstError ? firstError.message : null,
  };
}

/** Gateways del tenant seleccionado (de `/fleet/gateways`, RLS ya filtró). */
export function useTenantGateways(tenantId: string | null): {
  gatewayIds: string[];
  loading: boolean;
  error: string | null;
} {
  const gateways = useQuery({
    queryKey: ["fleet", "gateways"],
    queryFn: fetchGateways,
    staleTime: 30_000,
  });
  const sites = useQuery({ queryKey: ["sites"], queryFn: fetchSites, staleTime: 300_000 });

  const gatewayIds = useMemo(() => {
    if (!gateways.data || !sites.data || tenantId === null) {
      return [];
    }
    const tenantSites = new Set(
      sites.data.filter((s) => s.tenant_id === tenantId).map((s) => s.site_id),
    );
    return gateways.data.filter((g) => tenantSites.has(g.site_id)).map((g) => g.gateway_id);
  }, [gateways.data, sites.data, tenantId]);

  return {
    gatewayIds,
    loading: gateways.isPending || sites.isPending,
    error: gateways.error ? gateways.error.message : null,
  };
}

export interface CreateTenantState {
  /** Dispara el alta; el resultado se observa por `createdId`/`error`. */
  create: (body: TenantCreate) => void;
  pending: boolean;
  error: string | null;
  /** `tenant_id` del cliente recién creado (para seleccionarlo), o null. */
  createdId: string | null;
  reset: () => void;
}

/**
 * Alta de un cliente (T-1.72). Solo el superadmin llega aquí (el botón se gatea con
 * `manage_tenants`); el servidor la restringe igual. Al crear, invalida `["tenants"]`
 * para que el catálogo se refresque sin recargar la página.
 */
export function useCreateTenant(): CreateTenantState {
  const qc = useQueryClient();
  const mutation = useMutation({
    mutationFn: async (body: TenantCreate): Promise<TenantOut> => {
      const { data, response } = await createTenantTenantsPost({ body });
      if (data === undefined) {
        throw new TenantsRequestError("/tenants", response.status);
      }
      return data;
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["tenants"] });
    },
  });
  return {
    create: (body) => mutation.mutate(body),
    pending: mutation.isPending,
    error: mutation.error ? mutation.error.message : null,
    createdId: mutation.data?.tenant_id ?? null,
    reset: mutation.reset,
  };
}
