import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";

import {
  createTenantTenantsPost,
  listGatewayConfigStatesFleetConfigStateGet,
  listGatewaysFleetGatewaysGet,
  listRuleSetsRuleSetsGet,
  listSitesSitesGet,
  listTenantsTenantsGet,
  updateTenantTenantsTenantIdPatch,
} from "@takab/sdk";
import type {
  GatewayConfigStateOut,
  GatewayOut,
  RuleSetOut,
  SiteOut,
  TenantCreate,
  TenantOut,
  TenantUpdate,
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

async function fetchConfigStates(): Promise<GatewayConfigStateOut[]> {
  const { data, response } = await listGatewayConfigStatesFleetConfigStateGet();
  if (data === undefined) {
    throw new TenantsRequestError("/fleet/config-state", response.status);
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
 *
 * [T-2.51] **Una sola consulta, no una por gabinete.** Esto abría un `useQuery` por
 * gateway con `refetchInterval` de 10 s: 500 gabinetes = ~50 peticiones por segundo
 * desde UN navegador, contra una API que además corre co-locada con la base. El
 * endpoint en lote `GET /fleet/config-state` (T-2.37) devuelve el mismo SQL sin el
 * `WHERE`, y comparte la clave de consulta con `useFleetSyncStates` — la Flota y el
 * Multi-Tenant se sirven de la MISMA respuesta cacheada.
 *
 * La semántica honesta se conserva intacta: si en la respuesta falta el estado de
 * alguno de los gabinetes pedidos, `states` es `undefined` (= "no se sabe"), jamás
 * una lista parcial que el pie interpretaría como SINCRONIZADO (regla de oro 7).
 */
export function useTenantSync(gatewayIds: string[]): TenantSyncData {
  const query = useQuery({
    queryKey: ["fleet", "config-state"],
    queryFn: fetchConfigStates,
    refetchInterval: SYNC_POLL_MS,
    enabled: gatewayIds.length > 0,
  });

  const states = useMemo(() => {
    if (query.data === undefined) {
      return undefined;
    }
    const byId = new Map(query.data.map((s) => [s.gateway_id, s]));
    const picked = gatewayIds
      .map((id) => byId.get(id))
      .filter((s): s is GatewayConfigStateOut => s !== undefined);
    // Falta alguno ⇒ undefined. Un gabinete ausente del lote no está "al día":
    // simplemente no se sabe nada de él, y eso no autoriza ningún veredicto.
    return picked.length === gatewayIds.length ? picked : undefined;
  }, [query.data, gatewayIds]);

  if (gatewayIds.length === 0) {
    return { states: [], loading: false, error: null };
  }
  return {
    states,
    // `enabled:false` dejaría la query en `isPending` para siempre; aquí ya se
    // devolvió antes en ese caso, así que isPending significa "en vuelo".
    loading: query.isPending,
    error: query.error ? query.error.message : null,
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

/** Un 409 aquí NO es "algo salió mal": otro admin guardó y hay que releer. */
export function tenantPatchMessage(status: number): string {
  switch (status) {
    case 409:
      return "CONFLICTO · otro administrador guardó este cliente mientras editabas. Recarga y reintenta.";
    case 403:
      return "SIN PERMISO · solo TAKAB edita la ficha de un cliente.";
    case 404:
      return "NO ENCONTRADO · el cliente no existe o no es visible para tu rol.";
    case 422:
      return "DATOS INVÁLIDOS · revisa el nombre, el plan y el estado.";
    default:
      return `PATCH /tenants falló (${status})`;
  }
}

export interface UpdateTenantState {
  update: (args: { tenantId: string; body: TenantUpdate }, onDone?: () => void) => void;
  pending: boolean;
  error: string | null;
  reset: () => void;
}

/**
 * [T-2.51] Edición de la ficha del cliente. Solo `takab_superadmin` (la acción
 * `manage_tenants` gatea el control y la RLS `tenants_admin` lo exige igual).
 *
 * Manda `base_row_version` SIEMPRE: `visibility` decide si Protección Civil puede
 * leer los datos de este cliente y `status` si el servicio sigue vivo. Que una
 * pestaña vieja revierta cualquiera de las dos en silencio sería un cambio de
 * superficie de seguridad que nadie ordenó — por eso el servidor responde 409.
 */
export function useUpdateTenant(): UpdateTenantState {
  const qc = useQueryClient();
  const mutation = useMutation({
    mutationFn: async ({ tenantId, body }: { tenantId: string; body: TenantUpdate }) => {
      const { data, response } = await updateTenantTenantsTenantIdPatch({
        path: { tenant_id: tenantId },
        body,
      });
      if (data === undefined) {
        throw new Error(tenantPatchMessage(response.status));
      }
      return data;
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["tenants"] });
    },
  });
  return {
    update: (args, onDone) => mutation.mutate(args, { onSuccess: () => onDone?.() }),
    pending: mutation.isPending,
    error: mutation.error ? mutation.error.message : null,
    reset: mutation.reset,
  };
}
